from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
import structlog
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.models.repository import Repository
from app.schemas.repository import (
    RepositoryCreate,
    RepositoryResponse,
    RepositoryUpdate,
)
from app.services.repository_service import RepositoryService
from app.services.security_service import rate_limit_default, rate_limit_upload

logger = structlog.get_logger()
router = APIRouter()


# Enhanced request/response models
class RepositoryStatusResponse(BaseModel):
    repository_id: int
    status: str
    message: str
    processing_progress: Optional[float] = Field(
        None, description="Processing progress (0-100)"
    )
    algolia_indexed: Optional[bool] = Field(
        None, description="Whether repository is indexed in Algolia"
    )
    mcp_ready: Optional[bool] = Field(
        None, description="Whether repository is ready for MCP tools"
    )


@router.get(
    "/",
    response_model=List[RepositoryResponse],
    summary="List Repositories",
    description="List all repositories with optional filtering for MCP server",
)
async def list_repositories(
    skip: int = Query(default=0, ge=0, description="Number of repositories to skip"),
    limit: int = Query(
        default=100, le=500, description="Maximum number of repositories to return"
    ),
    language: Optional[str] = Query(None, description="Filter by programming language"),
    status: Optional[str] = Query(None, description="Filter by processing status"),
    mcp_ready: Optional[bool] = Query(None, description="Filter by MCP readiness"),
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
        if mcp_ready is not None:
            # Filter repositories that are indexed and ready for MCP tools
            query = query.filter(Repository.status == "completed")

        repositories = query.offset(skip).limit(limit).all()

        logger.info(
            "Repositories listed",
            count=len(repositories),
            language=language,
            status=status,
            mcp_ready=mcp_ready,
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
    description="Create a new repository for processing and MCP server integration",
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

        # Check for duplicate names
        existing = (
            db.query(Repository).filter(Repository.name == repository.name).first()
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Repository with name '{repository.name}' already exists",
            )

        service = RepositoryService(db)
        new_repository = await service.create_repository(repository)

        logger.info(
            "Repository created",
            repository_id=new_repository.id,
            name=new_repository.name,
        )
        return new_repository

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create repository", name=repository.name, error=str(e))
        raise HTTPException(
            status_code=400, detail=f"Failed to create repository: {str(e)}"
        )


@router.get(
    "/{repository_id}",
    response_model=RepositoryResponse,
    summary="Get Repository",
    description="Get details of a specific repository",
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


@router.put(
    "/{repository_id}",
    response_model=RepositoryResponse,
    summary="Update Repository",
    description="Update repository information",
)
async def update_repository(
    repository_id: int,
    repository_update: RepositoryUpdate,
    db: Session = Depends(get_db),
):
    """Update a repository"""
    try:
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(
                status_code=404, detail=f"Repository {repository_id} not found"
            )

        # Update fields
        for field, value in repository_update.dict(exclude_unset=True).items():
            setattr(repository, field, value)

        db.commit()
        db.refresh(repository)

        logger.info("Repository updated", repository_id=repository_id)
        return repository

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to update repository", repository_id=repository_id, error=str(e)
        )
        raise HTTPException(
            status_code=400, detail=f"Failed to update repository: {str(e)}"
        )


@router.delete(
    "/{repository_id}",
    summary="Delete Repository",
    description="Delete a repository and all associated data",
)
async def delete_repository(repository_id: int, db: Session = Depends(get_db)):
    """Delete a repository"""
    try:
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(
                status_code=404, detail=f"Repository {repository_id} not found"
            )

        db.delete(repository)
        db.commit()

        logger.info("Repository deleted", repository_id=repository_id)
        return {"message": f"Repository {repository_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to delete repository", repository_id=repository_id, error=str(e)
        )
        raise HTTPException(
            status_code=400, detail=f"Failed to delete repository: {str(e)}"
        )


@router.post(
    "/{repository_id}/upload",
    summary="Upload Repository Files",
    description="Upload files to a repository for processing",
)
@rate_limit_upload
async def upload_repository_files(
    repository_id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Upload files to a repository"""
    try:
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(
                status_code=404, detail=f"Repository {repository_id} not found"
            )

        if repository.status == "processing":
            raise HTTPException(
                status_code=400,
                detail="Cannot upload files while repository is being processed",
            )

        # Validate files
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")

        # Check file types and sizes
        max_file_size = 10 * 1024 * 1024  # 10MB
        allowed_extensions = {
            ".py",
            ".js",
            ".ts",
            ".java",
            ".go",
            ".rs",
            ".cpp",
            ".c",
            ".h",
        }

        for file in files:
            if file.size and file.size > max_file_size:
                raise HTTPException(
                    status_code=400,
                    detail=f"File {file.filename} exceeds maximum size of 10MB",
                )

            if file.filename:
                ext = "." + file.filename.split(".")[-1].lower()
                if ext not in allowed_extensions:
                    logger.warning(f"Skipping unsupported file type: {file.filename}")

        service = RepositoryService(db)
        updated_repository = await service.upload_files(repository, files)

        logger.info(
            "Files uploaded to repository",
            repository_id=repository_id,
            file_count=len(files),
        )

        return {
            "message": f"Uploaded {len(files)} files to repository {repository_id}",
            "repository": updated_repository,
            "next_step": "Call /process endpoint to start analysis and indexing",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to upload files", repository_id=repository_id, error=str(e)
        )
        raise HTTPException(status_code=400, detail=f"File upload failed: {str(e)}")


@router.post(
    "/{repository_id}/process",
    response_model=RepositoryStatusResponse,
    summary="Process Repository",
    description="Start processing repository for MCP server integration",
)
async def process_repository(
    repository_id: int,
    force_reprocess: bool = Query(
        default=False, description="Force reprocessing if already completed"
    ),
    db: Session = Depends(get_db),
):
    """Trigger processing of repository files for MCP server"""
    try:
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(
                status_code=404, detail=f"Repository {repository_id} not found"
            )

        if repository.status == "processing":
            raise HTTPException(
                status_code=400, detail="Repository is already being processed"
            )

        if repository.status == "completed" and not force_reprocess:
            return RepositoryStatusResponse(
                repository_id=repository_id,
                status="completed",
                message="Repository is already processed and ready for MCP tools",
                processing_progress=100.0,
                algolia_indexed=True,
                mcp_ready=True,
            )

        service = RepositoryService(db)
        await service.process_repository(repository)

        logger.info("Repository processing started", repository_id=repository_id)

        return RepositoryStatusResponse(
            repository_id=repository_id,
            status="processing",
            message="Repository processing started - files will be analyzed and indexed for MCP tools",
            processing_progress=0.0,
            algolia_indexed=False,
            mcp_ready=False,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to start processing", repository_id=repository_id, error=str(e)
        )
        raise HTTPException(status_code=400, detail=f"Processing failed: {str(e)}")


@router.get(
    "/{repository_id}/status",
    response_model=RepositoryStatusResponse,
    summary="Get Repository Status",
    description="Get detailed processing status of a repository",
)
async def get_repository_status(repository_id: int, db: Session = Depends(get_db)):
    """Get detailed status of repository processing"""
    try:
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(
                status_code=404, detail=f"Repository {repository_id} not found"
            )

        # Calculate processing progress
        progress = 0.0
        if repository.status == "completed":
            progress = 100.0
        elif repository.status == "processing":
            # This would be calculated based on actual progress
            progress = 50.0  # Placeholder

        # Determine MCP readiness
        mcp_ready = (
            repository.status == "completed"
            and repository.total_files > 0
            and repository.processed_files == repository.total_files
        )

        return RepositoryStatusResponse(
            repository_id=repository_id,
            status=repository.status,
            message=f"Repository is {repository.status}",
            processing_progress=progress,
            algolia_indexed=mcp_ready,
            mcp_ready=mcp_ready,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get repository status", repository_id=repository_id, error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")


@router.get(
    "/{repository_id}/stats",
    summary="Get Repository Statistics",
    description="Get detailed statistics about a repository",
)
async def get_repository_statistics(repository_id: int, db: Session = Depends(get_db)):
    """Get repository statistics for MCP server insights"""
    try:
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(
                status_code=404, detail=f"Repository {repository_id} not found"
            )

        service = RepositoryService(db)
        stats = await service.get_repository_statistics(repository)

        logger.info("Repository statistics retrieved", repository_id=repository_id)
        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get repository stats", repository_id=repository_id, error=str(e)
        )
        raise HTTPException(
            status_code=500, detail=f"Statistics retrieval failed: {str(e)}"
        )
