from sqlalchemy.orm import Session
from typing import List
import structlog
import asyncio
import time

from app.models.repository import Repository
from app.schemas.repository import RepositoryCreate

logger = structlog.get_logger()


class RepositoryService:
    """Service for repository management and processing with real-time updates"""

    def __init__(self, db: Session):
        self.db = db

    async def create_repository(self, repository_data: RepositoryCreate) -> Repository:
        """Create a new repository"""
        db_repo = Repository(
            name=repository_data.name,
            description=repository_data.description,
            url=repository_data.url,
            branch=repository_data.branch or "main",
            language=repository_data.language,
            status="pending",
            total_files=0,
            processed_files=0,
            total_lines=0,
        )
        self.db.add(db_repo)
        self.db.commit()
        self.db.refresh(db_repo)

        # Broadcast repository creation
        # await self._broadcast_status_update(
        #     db_repo.id, "pending", "Repository created and queued for processing"
        # )

        logger.info("Repository created", repository_id=db_repo.id, name=db_repo.name)
        return db_repo

    async def upload_files(self, repository: Repository, files: List) -> Repository:
        """Upload files to repository and save them to database"""
        from app.models.code_file import CodeFile
        import os

        uploaded_count = 0
        total_files = len(files)

        # Update repository with total file count and broadcast
        repository.total_files = total_files
        repository.status = "processing"
        self.db.commit()

        # await self._broadcast_status_update(
        #     repository.id,
        #     "processing",
        #     f"Starting file upload: {total_files} files to process",
        #     total_files=total_files,
        #     processed_files=0,
        # )

        for i, file in enumerate(files):
            try:
                # Read file content
                content = await file.read()
                content_str = content.decode("utf-8")

                # Create CodeFile record
                code_file = CodeFile(
                    repository_id=repository.id,
                    file_path=file.filename or "unknown",
                    file_name=(
                        os.path.basename(file.filename) if file.filename else "unknown"
                    ),
                    content=content_str,
                    language=self._detect_language(file.filename),
                    size_bytes=len(content),
                    line_count=len(content_str.splitlines()),
                    is_analyzed=False,
                )

                self.db.add(code_file)
                uploaded_count += 1

                # Update processed files count
                repository.processed_files = uploaded_count
                self.db.commit()

                # Broadcast progress every 10 files or on last file
                if uploaded_count % 10 == 0 or uploaded_count == total_files:
                    progress_percentage = (uploaded_count / total_files) * 100
                    # await self._broadcast_status_update(
                    #     repository.id,
                    #     "processing",
                    #     f"Uploaded {uploaded_count}/{total_files} files ({progress_percentage:.1f}%)",
                    #     processing_progress=progress_percentage,
                    #     processed_files=uploaded_count,
                    #     total_files=total_files,
                    # )

                logger.debug(
                    f"File uploaded: {file.filename} ({uploaded_count}/{total_files})"
                )

            except Exception as e:
                logger.error(f"Failed to upload file {file.filename}: {str(e)}")
                continue

        repository.total_files = total_files
        repository.processed_files = uploaded_count
        repository.total_lines = sum([cf.line_count for cf in repository.code_files])
        repository.status = "uploaded" if uploaded_count > 0 else "failed"

        self.db.commit()

        # if uploaded_count > 0:
        #     await self._broadcast_status_update(
        #         repository.id,
        #         "uploaded",
        #         f"File upload complete: {uploaded_count} files uploaded successfully",
        #         processing_progress=100.0,
        #         processed_files=uploaded_count,
        #         total_files=total_files,
        #     )
        # else:
        #     await self._broadcast_processing_failed(
        #         repository.id,
        #         "No files could be uploaded successfully",
        #         repository.name,
        #     )

        logger.info(f"Uploaded {uploaded_count} files to repository {repository.id}")
        return repository

    async def process_repository(
        self, repository: Repository, force_reprocess: bool = False
    ):
        """Process repository with AI analysis and real-time status updates"""
        try:
            if repository.status == "completed" and not force_reprocess:
                # await self._broadcast_status_update(
                #     repository.id,
                #     "completed",
                #     "Repository already processed (use force_reprocess=true to reprocess)",
                #     algolia_indexed=True,
                #     mcp_ready=True,
                # )
                return repository

            # Start processing
            repository.status = "processing"
            self.db.commit()

            # await self._broadcast_status_update(
            #     repository.id,
            #     "processing",
            #     "Starting repository analysis...",
            #     processing_progress=0.0,
            #     algolia_indexed=False,
            #     mcp_ready=False,
            # )

            # Process repository files
            try:
                await self.process_repository_files(repository)
                repository.status = "completed"
                
                logger.info(
                    "Repository processing completed",
                    repository_id=repository.id,
                    total_files=repository.total_files,
                    processed_files=repository.processed_files,
                )

            except Exception as e:
                repository.status = "failed"
                logger.error(
                    "Repository processing failed",
                    repository_id=repository.id,
                    error=str(e),
                )
                
            self.db.commit()

        except Exception as e:
            logger.error(
                "Repository processing failed",
                repository_id=repository.id,
                error=str(e),
            )
            repository.status = "failed"
            self.db.commit()

            # await self._broadcast_processing_failed(
            #     repository.id, f"Processing failed: {str(e)}", repository.name
            # )

            raise e

    async def get_repository_statistics(self, repository: Repository) -> dict:
        """Get repository statistics (stub implementation)"""
        return {
            "repository_id": repository.id,
            "total_files": repository.total_files,
            "processed_files": repository.processed_files,
            "total_lines": repository.total_lines,
            "languages": [repository.language] if repository.language else [],
            "security_score": repository.security_score,
            "vulnerability_count": repository.vulnerability_count,
        }

    def _detect_language(self, filename: str) -> str:
        """Detect programming language from file extension"""
        if not filename:
            return "text"

        ext = filename.lower().split(".")[-1]
        language_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "jsx": "javascript",
            "tsx": "typescript",
            "java": "java",
            "go": "go",
            "rs": "rust",
            "cpp": "cpp",
            "c": "c",
            "cs": "csharp",
            "php": "php",
            "rb": "ruby",
            "html": "html",
            "css": "css",
            "scss": "scss",
            "sql": "sql",
            "json": "json",
            "yaml": "yaml",
            "yml": "yaml",
            "xml": "xml",
            "md": "markdown",
        }
        return language_map.get(ext, "text")

    # Remove websocket broadcast methods since websockets are deleted for MCP-first architecture
    # MCP tools can query repository status directly when needed

    async def process_repository_files(self, repository: Repository):
        """Process all files in repository for Algolia indexing"""
        try:
            # This would implement actual repository processing
            # For now, it's a placeholder that sets status to completed
            
            logger.info(
                "Processing repository files",
                repository_id=repository.id,
                url=repository.url
            )
            
            # TODO: Implement actual GitHub API integration and file processing
            # - Clone/download repository files
            # - Parse code files and extract entities
            # - Index content in Algolia
            # - Update file counts and status
            
            # Simulate processing
            repository.total_files = 50  # Placeholder
            repository.processed_files = 50  # Placeholder
            
        except Exception as e:
            logger.error(
                "File processing failed",
                repository_id=repository.id,
                error=str(e)
            )
            raise
