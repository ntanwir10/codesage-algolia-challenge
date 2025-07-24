from typing import List, Optional
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from sqlalchemy.orm import Session
import structlog

from app.core.database import get_db
from app.models.repository import Repository
from app.schemas.repository import (
    RepositoryCreate,
    RepositoryResponse,
)
from app.services.repository_service import RepositoryService
from app.services.security_service import rate_limit_default

logger = structlog.get_logger()
router = APIRouter()


@router.get(
    "/",
    response_model=List[RepositoryResponse],
    summary="List Repositories",
    description="List all repositories with optional filtering",
)
async def list_repositories(
    skip: int = Query(default=0, ge=0, description="Number of repositories to skip"),
    limit: int = Query(
        default=100, le=500, description="Maximum number of repositories to return"
    ),
    language: Optional[str] = Query(None, description="Filter by programming language"),
    status: Optional[str] = Query(None, description="Filter by processing status"),
    db: Session = Depends(get_db),
):
    """List all repositories with optional filtering"""
    try:
        query = db.query(Repository)

        # Apply filters
        if language:
            query = query.filter(Repository.language == language)
        if status:
            query = query.filter(Repository.status == status)

        repositories = query.offset(skip).limit(limit).all()

        logger.info(
            "Repositories listed",
            count=len(repositories),
            language=language,
            status=status,
        )

        return repositories
    except Exception as e:
        logger.error("Failed to list repositories", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to list repositories: {str(e)}"
        )


@router.post(
    "/",
    response_model=RepositoryResponse,
    status_code=201,
    summary="Create Repository",
    description="Create a new repository for processing",
)
@rate_limit_default
async def create_repository(
    repository: RepositoryCreate, db: Session = Depends(get_db)
):
    """Create a new repository"""
    try:
        # Validate repository data
        if not repository.name or not repository.name.strip():
            raise HTTPException(status_code=400, detail="Repository name is required")

        if not repository.url or not repository.url.strip():
            raise HTTPException(status_code=400, detail="Repository URL is required")

        # Check for duplicate repository
        existing = db.query(Repository).filter(Repository.url == repository.url).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Repository with URL {repository.url} already exists (ID: {existing.id})",
            )

        service = RepositoryService(db)
        new_repository = await service.create_repository(repository)

        logger.info("Repository created", repository_id=new_repository.id)
        return new_repository

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create repository", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to create repository: {str(e)}"
        )


@router.get(
    "/{repository_id}",
    response_model=RepositoryResponse,
    summary="Get Repository",
    description="Get a specific repository by ID",
)
async def get_repository(repository_id: int, db: Session = Depends(get_db)):
    """Get a specific repository by ID"""
    try:
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(
                status_code=404, detail=f"Repository {repository_id} not found"
            )

        logger.info("Repository retrieved", repository_id=repository_id)
        return repository

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get repository", repository_id=repository_id, error=str(e)
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get repository: {str(e)}"
        )


@router.delete(
    "/{repository_id}",
    summary="Delete Repository",
    description="Delete a repository and all its associated data",
)
async def delete_repository(repository_id: int, db: Session = Depends(get_db)):
    """Delete a repository and all its associated data"""
    try:
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(
                status_code=404, detail=f"Repository {repository_id} not found"
            )

        service = RepositoryService(db)
        await service.delete_repository(repository_id)

        logger.info("Repository deleted", repository_id=repository_id)
        return {"message": f"Repository {repository_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to delete repository", repository_id=repository_id, error=str(e)
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to delete repository: {str(e)}"
        )
