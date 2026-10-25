import structlog
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import limiter, require_api_key
from app.models.repository import Repository
from app.schemas.repository import (
    RepositoryCreate,
    RepositoryResponse,
    RepositoryUpdate,
)
from app.services.repository_service import (
    RepositoryBusyError,
    RepositoryService,
    is_processing,
    start_processing,
)

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter()


@router.get(
    "/",
    response_model=list[RepositoryResponse],
    summary="List Repositories",
    description="List all repositories with optional filtering",
)
async def list_repositories(
    skip: int = Query(default=0, ge=0, description="Number of repositories to skip"),
    limit: int = Query(
        default=100, ge=1, le=500, description="Maximum number of repositories to return"
    ),
    language: str | None = Query(None, description="Filter by programming language"),
    status: str | None = Query(None, description="Filter by processing status"),
    db: Session = Depends(get_db),
):
    """List all repositories with optional filtering"""
    query = db.query(Repository)

    # Apply filters
    if language:
        query = query.filter(Repository.language == language)
    if status:
        query = query.filter(Repository.status == status)

    repositories = query.order_by(Repository.id).offset(skip).limit(limit).all()

    logger.info(
        "Repositories listed",
        count=len(repositories),
        language=language,
        status=status,
    )

    return repositories


@router.post(
    "/",
    response_model=RepositoryResponse,
    status_code=201,
    dependencies=[Depends(require_api_key)],
    summary="Create Repository",
    description="Create a new repository for processing",
)
@limiter.limit(lambda: settings.rate_limit_default)
async def create_repository(
    request: Request, repository: RepositoryCreate, db: Session = Depends(get_db)
):
    """Create a new repository"""
    # repository.url is already validated and normalised by the schema
    existing = db.query(Repository).filter(Repository.url == repository.url).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Repository with URL {repository.url} already exists (ID: {existing.id})",
        )

    service = RepositoryService(db)
    try:
        new_repository = await service.create_repository(repository)
    except IntegrityError as e:
        # Another request added the same URL between the check above and this insert
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f"Repository with URL {repository.url} already exists"
        ) from e

    logger.info("Repository created", repository_id=new_repository.id)
    return new_repository


@router.get(
    "/{repository_id}",
    response_model=RepositoryResponse,
    summary="Get Repository",
    description="Get a specific repository by ID",
)
async def get_repository(repository_id: int, db: Session = Depends(get_db)):
    """Get a specific repository by ID"""
    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        raise HTTPException(
            status_code=404, detail=f"Repository {repository_id} not found"
        )

    logger.info("Repository retrieved", repository_id=repository_id)
    return repository


@router.put(
    "/{repository_id}",
    response_model=RepositoryResponse,
    dependencies=[Depends(require_api_key)],
    summary="Update Repository",
    description="Update a repository's details",
)
async def update_repository(
    repository_id: int,
    repository_update: RepositoryUpdate,
    db: Session = Depends(get_db),
):
    """Update a repository's details"""
    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        raise HTTPException(
            status_code=404, detail=f"Repository {repository_id} not found"
        )

    update_data = repository_update.model_dump(exclude_unset=True)
    # A run (or a delete) holds the repository: a new branch mid-run would label the old
    # branch's index with it, and the run's own commits would race this one
    if is_processing(repository_id) and update_data.get("branch", repository.branch) != repository.branch:
        raise HTTPException(
            status_code=409,
            detail=f"Repository {repository_id} is being processed; change the branch when it finishes",
        )

    # Update repository fields
    for key, value in update_data.items():
        setattr(repository, key, value)

    db.commit()
    db.refresh(repository)

    logger.info("Repository updated", repository_id=repository_id)
    return repository


@router.delete(
    "/{repository_id}",
    dependencies=[Depends(require_api_key)],
    summary="Delete Repository",
    description="Delete a repository and all its associated data",
)
async def delete_repository(repository_id: int, db: Session = Depends(get_db)):
    """Delete a repository and all its associated data"""
    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        raise HTTPException(
            status_code=404, detail=f"Repository {repository_id} not found"
        )

    try:
        deleted = await RepositoryService(db).delete_repository(repository)
    except RepositoryBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not deleted:
        raise HTTPException(
            status_code=502,
            detail="Could not remove the repository's records from Algolia; nothing was deleted",
        )

    logger.info("Repository deleted", repository_id=repository_id)
    return {"message": f"Repository {repository_id} deleted successfully"}


@router.get(
    "/{repository_id}/status",
    summary="Get Repository Status",
    description="Get the current processing status of a repository",
)
async def get_repository_status(repository_id: int, db: Session = Depends(get_db)):
    """Get the status of a repository"""
    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        raise HTTPException(
            status_code=404, detail=f"Repository {repository_id} not found"
        )

    return {
        "repository_id": repository.id,
        "status": repository.status,
        "processed_files": repository.processed_files,
        "total_files": repository.total_files,
        "progress": repository.processing_progress,
    }


@router.get(
    "/{repository_id}/stats",
    summary="Get Repository Statistics",
    description="Get processing statistics for a repository",
)
async def get_repository_stats(repository_id: int, db: Session = Depends(get_db)):
    """Get statistics for a repository"""
    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        raise HTTPException(
            status_code=404, detail=f"Repository {repository_id} not found"
        )

    service = RepositoryService(db)
    stats = await service.get_repository_statistics(repository)

    return stats


@router.post(
    "/{repository_id}/process",
    status_code=202,
    dependencies=[Depends(require_api_key)],
    summary="Process Repository",
    description=(
        "Schedule processing that extracts code entities and indexes them in Algolia. "
        "Returns immediately; follow progress via /status or the WebSocket."
    ),
)
@limiter.limit(lambda: settings.rate_limit_default)
async def process_repository(
    request: Request,
    repository_id: int,
    force_reprocess: bool = False,
    db: Session = Depends(get_db),
):
    """Schedule a repository processing job"""
    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        raise HTTPException(
            status_code=404, detail=f"Repository {repository_id} not found"
        )
    if repository.status == "completed" and not force_reprocess:
        raise HTTPException(
            status_code=409,
            detail="Repository is already processed; pass force_reprocess=true to reprocess it",
        )

    try:
        start_processing(repository_id, force_reprocess=force_reprocess)
    except RepositoryBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    logger.info("Repository processing scheduled", repository_id=repository_id)
    return {
        "message": f"Processing started for repository {repository_id}",
        "repository_id": repository_id,
    }


