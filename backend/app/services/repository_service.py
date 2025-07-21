from sqlalchemy.orm import Session
from typing import List
import structlog

from app.models.repository import Repository
from app.schemas.repository import RepositoryCreate

logger = structlog.get_logger()


class RepositoryService:
    """Service for repository management and processing"""

    def __init__(self, db: Session):
        self.db = db

    async def create_repository(self, repository_data: RepositoryCreate) -> Repository:
        """Create a new repository"""
        db_repo = Repository(
            name=repository_data.name,
            description=repository_data.description,
            url=repository_data.url,
            language=repository_data.language,
            status="pending",
        )
        self.db.add(db_repo)
        self.db.commit()
        self.db.refresh(db_repo)
        return db_repo

    async def upload_files(self, repository: Repository, files: List) -> Repository:
        """Upload files to repository and save them to database"""
        from app.models.code_file import CodeFile
        import os

        uploaded_count = 0

        for file in files:
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

                logger.info(f"File uploaded: {file.filename}")

            except Exception as e:
                logger.error(f"Failed to upload file {file.filename}: {str(e)}")
                continue

        repository.total_files = (repository.total_files or 0) + uploaded_count
        repository.status = "uploaded" if uploaded_count > 0 else repository.status

        self.db.commit()

        logger.info(f"Uploaded {uploaded_count} files to repository {repository.id}")
        return repository

    async def process_repository(self, repository: Repository):
        """Process repository with AI analysis (stub implementation)"""
        # TODO: Implement repository processing
        repository.status = "processing"
        self.db.commit()
        return repository

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
            return "unknown"

        ext = filename.lower().split(".")[-1] if "." in filename else ""

        language_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "java": "java",
            "go": "go",
            "rs": "rust",
            "cpp": "cpp",
            "c": "c",
            "cs": "csharp",
            "php": "php",
            "rb": "ruby",
        }

        return language_map.get(ext, "unknown")
