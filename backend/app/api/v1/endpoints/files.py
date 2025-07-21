from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
import structlog
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.models.code_file import CodeFile
from app.models.code_entity import CodeEntity
from app.schemas.file import FileResponse, FileContentResponse, EntityResponse
from app.services.file_service import FileService

logger = structlog.get_logger()
router = APIRouter()


# Enhanced request models
class FileAnalysisRequest(BaseModel):
    force_reanalysis: bool = Field(
        default=False, description="Force reanalysis if already completed"
    )
    include_entities: bool = Field(
        default=True, description="Include entity extraction"
    )
    include_content: bool = Field(default=True, description="Include full file content")


class BulkAnalysisRequest(BaseModel):
    file_ids: List[int] = Field(..., description="List of file IDs to analyze")
    force_reanalysis: bool = Field(default=False, description="Force reanalysis")
    parallel_processing: bool = Field(
        default=True, description="Enable parallel processing"
    )


@router.get(
    "/repositories/{repository_id}",
    response_model=List[FileResponse],
    summary="List Repository Files",
    description="List files in a repository with filtering options",
)
async def list_repository_files(
    repository_id: int,
    path: Optional[str] = Query(None, description="Filter by file path prefix"),
    language: Optional[str] = Query(None, description="Filter by programming language"),
    analyzed_only: Optional[bool] = Query(None, description="Show only analyzed files"),
    skip: int = Query(default=0, ge=0, description="Number of files to skip"),
    limit: int = Query(
        default=100, ge=1, le=500, description="Maximum number of files"
    ),
    db: Session = Depends(get_db),
):
    """List files in a repository with optional filtering"""
    try:
        # Validate repository exists
        from app.models.repository import Repository

        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(
                status_code=404, detail=f"Repository {repository_id} not found"
            )

        query = db.query(CodeFile).filter(CodeFile.repository_id == repository_id)

        # Apply filters
        if path:
            query = query.filter(CodeFile.file_path.like(f"{path}%"))
        if language:
            query = query.filter(CodeFile.language == language)
        if analyzed_only is not None:
            query = query.filter(CodeFile.is_analyzed == analyzed_only)

        files = query.offset(skip).limit(limit).all()

        logger.info(
            "Repository files listed",
            repository_id=repository_id,
            count=len(files),
            filters={
                "path": path,
                "language": language,
                "analyzed_only": analyzed_only,
            },
        )
        return files

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to list repository files", repository_id=repository_id, error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@router.get(
    "/{file_id}",
    response_model=FileContentResponse,
    summary="Get File Content",
    description="Get detailed file content with optional entities",
)
async def get_file_content(
    file_id: int,
    include_entities: bool = Query(default=True, description="Include code entities"),
    include_raw_content: bool = Query(
        default=True, description="Include raw file content"
    ),
    entity_types: Optional[str] = Query(
        None, description="Filter entities by types (comma-separated)"
    ),
    db: Session = Depends(get_db),
):
    """Get file content with optional code entities"""
    try:
        file_obj = db.query(CodeFile).filter(CodeFile.id == file_id).first()
        if not file_obj:
            raise HTTPException(status_code=404, detail=f"File {file_id} not found")

        response = FileContentResponse(
            id=file_obj.id,
            file_path=file_obj.file_path,
            file_name=file_obj.file_name,
            language=file_obj.language,
            content=file_obj.content if include_raw_content else None,
            line_count=file_obj.line_count,
            entities=[],
            analysis_status=file_obj.is_analyzed,
            repository_id=file_obj.repository_id,
        )

        if include_entities:
            entity_query = db.query(CodeEntity).filter(
                CodeEntity.code_file_id == file_id
            )

            # Filter by entity types if specified
            if entity_types:
                types_list = [t.strip() for t in entity_types.split(",")]
                entity_query = entity_query.filter(
                    CodeEntity.entity_type.in_(types_list)
                )

            response.entities = entity_query.all()

        logger.info(
            "File content retrieved",
            file_id=file_id,
            entities_count=len(response.entities),
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get file content", file_id=file_id, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get file content: {str(e)}"
        )


@router.get(
    "/{file_id}/raw",
    response_class=PlainTextResponse,
    summary="Get Raw File Content",
    description="Get raw file content as plain text",
)
async def get_raw_file_content(file_id: int, db: Session = Depends(get_db)):
    """Get raw file content as plain text"""
    try:
        file_obj = db.query(CodeFile).filter(CodeFile.id == file_id).first()
        if not file_obj:
            raise HTTPException(status_code=404, detail=f"File {file_id} not found")

        if not file_obj.content:
            raise HTTPException(status_code=404, detail="File content not available")

        logger.info("Raw file content retrieved", file_id=file_id)
        return PlainTextResponse(content=file_obj.content, media_type="text/plain")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get raw file content", file_id=file_id, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get raw content: {str(e)}"
        )


@router.get(
    "/{file_id}/entities",
    response_model=List[EntityResponse],
    summary="Get File Entities",
    description="Get code entities (functions, classes, etc.) in a file",
)
async def get_file_entities(
    file_id: int,
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    include_private: bool = Query(default=True, description="Include private entities"),
    sort_by: str = Query(
        default="line_start", description="Sort by: name, line_start, entity_type"
    ),
    db: Session = Depends(get_db),
):
    """Get code entities (functions, classes, etc.) in a file"""
    try:
        # Validate file exists
        file_obj = db.query(CodeFile).filter(CodeFile.id == file_id).first()
        if not file_obj:
            raise HTTPException(status_code=404, detail=f"File {file_id} not found")

        query = db.query(CodeEntity).filter(CodeEntity.code_file_id == file_id)

        # Apply filters
        if entity_type:
            query = query.filter(CodeEntity.entity_type == entity_type)
        if not include_private:
            # Assuming we have a way to identify private entities
            query = query.filter(~CodeEntity.name.like("_%"))  # Simple heuristic

        # Apply sorting
        if sort_by == "name":
            query = query.order_by(CodeEntity.name)
        elif sort_by == "entity_type":
            query = query.order_by(CodeEntity.entity_type, CodeEntity.name)
        else:  # default to line_start
            query = query.order_by(CodeEntity.line_start)

        entities = query.all()

        logger.info(
            "File entities retrieved",
            file_id=file_id,
            count=len(entities),
            entity_type=entity_type,
        )
        return entities

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get file entities", file_id=file_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get entities: {str(e)}")


@router.get(
    "/{file_id}/summary",
    summary="Get File Summary",
    description="Get AI-generated summary of file content and structure",
)
async def get_file_summary(
    file_id: int,
    include_entities: bool = Query(default=True, description="Include entity summary"),
    include_dependencies: bool = Query(
        default=True, description="Include dependency analysis"
    ),
    detail_level: str = Query(
        default="brief", description="Summary detail level (brief, detailed)"
    ),
    db: Session = Depends(get_db),
):
    """Get AI-generated file summary"""
    try:
        file_obj = db.query(CodeFile).filter(CodeFile.id == file_id).first()
        if not file_obj:
            raise HTTPException(status_code=404, detail=f"File {file_id} not found")

        file_service = FileService(db)
        summary = await file_service.generate_file_summary(
            file_obj, include_entities, include_dependencies, detail_level
        )

        logger.info(
            "File summary generated", file_id=file_id, detail_level=detail_level
        )
        return summary

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate file summary", file_id=file_id, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to generate summary: {str(e)}"
        )


@router.post(
    "/{file_id}/analyze",
    summary="Analyze File",
    description="Trigger AI analysis of a specific file",
)
async def analyze_file(
    file_id: int,
    request: FileAnalysisRequest = FileAnalysisRequest(),
    db: Session = Depends(get_db),
):
    """Trigger AI analysis of a specific file"""
    try:
        file_obj = db.query(CodeFile).filter(CodeFile.id == file_id).first()
        if not file_obj:
            raise HTTPException(status_code=404, detail=f"File {file_id} not found")

        if file_obj.is_analyzed and not request.force_reanalysis:
            return {
                "message": "File already analyzed",
                "status": "completed",
                "file_id": file_id,
                "entities_count": db.query(CodeEntity)
                .filter(CodeEntity.code_file_id == file_id)
                .count(),
            }

        file_service = FileService(db)
        result = await file_service.analyze_file(
            file_obj, request.include_entities, request.include_content
        )

        logger.info(
            "File analysis triggered",
            file_id=file_id,
            force_reanalysis=request.force_reanalysis,
        )
        return {
            "message": "File analysis completed",
            "status": "completed",
            "file_id": file_id,
            "result": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("File analysis failed", file_id=file_id, error=str(e))
        raise HTTPException(status_code=400, detail=f"File analysis failed: {str(e)}")


@router.post(
    "/analyze/bulk",
    summary="Bulk Analyze Files",
    description="Analyze multiple files in batch",
)
async def bulk_analyze_files(
    request: BulkAnalysisRequest,
    db: Session = Depends(get_db),
):
    """Bulk analyze multiple files"""
    try:
        if not request.file_ids:
            raise HTTPException(status_code=400, detail="No file IDs provided")

        if len(request.file_ids) > 100:
            raise HTTPException(
                status_code=400, detail="Too many files (max 100 per batch)"
            )

        # Validate all files exist
        files = db.query(CodeFile).filter(CodeFile.id.in_(request.file_ids)).all()
        found_ids = {f.id for f in files}
        missing_ids = set(request.file_ids) - found_ids

        if missing_ids:
            raise HTTPException(
                status_code=404, detail=f"Files not found: {list(missing_ids)}"
            )

        file_service = FileService(db)
        results = await file_service.bulk_analyze_files(
            files, request.force_reanalysis, request.parallel_processing
        )

        logger.info("Bulk file analysis completed", file_count=len(request.file_ids))
        return {
            "message": f"Bulk analysis completed for {len(request.file_ids)} files",
            "processed_files": len(request.file_ids),
            "results": results,
            "status": "completed",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Bulk file analysis failed", file_count=len(request.file_ids), error=str(e)
        )
        raise HTTPException(status_code=400, detail=f"Bulk analysis failed: {str(e)}")


@router.get(
    "/stats/repository/{repository_id}",
    summary="Get Repository File Statistics",
    description="Get detailed file statistics for a repository",
)
async def get_repository_file_stats(
    repository_id: int,
    include_language_breakdown: bool = Query(
        default=True, description="Include language breakdown"
    ),
    include_analysis_status: bool = Query(
        default=True, description="Include analysis status"
    ),
    db: Session = Depends(get_db),
):
    """Get file statistics for a repository"""
    try:
        # Validate repository exists
        from app.models.repository import Repository

        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(
                status_code=404, detail=f"Repository {repository_id} not found"
            )

        file_service = FileService(db)
        stats = await file_service.get_repository_file_stats(
            repository_id, include_language_breakdown, include_analysis_status
        )

        logger.info("Repository file stats retrieved", repository_id=repository_id)
        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get repository file stats",
            repository_id=repository_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get file stats: {str(e)}"
        )
