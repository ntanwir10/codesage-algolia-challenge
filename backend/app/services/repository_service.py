"""
CodeSage - MCP-First Code Discovery: Repository Service

This module handles repository management for CodeSage - the only code discovery
tool built entirely around the Model Context Protocol (MCP) for seamless AI integration.

The repository service processes GitHub repositories and prepares them for MCP-based
AI discovery through Claude Desktop and other MCP clients.

This represents our core innovation: MCP-first architecture for code discovery.
"""

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import structlog
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.schemas.repository import RepositoryCreate

logger = structlog.get_logger()

# Performance constants
BATCH_SIZE = 50  # Process files in batches
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB max file size
MAX_CONCURRENT_GITHUB_REQUESTS = 5  # Limit concurrent API calls
LARGE_REPO_THRESHOLD = 1000  # Files threshold for large repo optimizations


class IngestionError(Exception):
    """A processing run that would leave the repository with nothing searchable"""


class RepositoryService:
    """Service for repository management with performance optimizations"""

    def __init__(self, db: Session):
        self.db = db
        self.github_service = None  # Lazy loaded
        self.algolia_service = None  # Lazy loaded
        self.code_parser = None  # Lazy loaded
        self._executor = ThreadPoolExecutor(max_workers=4)  # For CPU-bound tasks

    def _lazy_load_services(self):
        """Lazy load heavy services only when needed"""
        if not self.github_service:
            from app.services.github_service import GitHubService

            self.github_service = GitHubService()

        if not self.algolia_service:
            from app.services.algolia_service import AlgoliaService

            self.algolia_service = AlgoliaService()

        if not self.code_parser:
            from app.services.code_parser import CodeParser

            self.code_parser = CodeParser()

    @asynccontextmanager
    async def _batch_processing_context(self, repository_id: int):
        """Context manager for optimized batch processing"""
        try:
            # Start timer
            start_time = time.time()

            # Set up batch processing
            logger.info(f"Starting optimized processing for repository {repository_id}")

            yield

        finally:
            # Cleanup and log performance
            elapsed = time.time() - start_time
            logger.info(
                f"Repository {repository_id} processing completed in {elapsed:.2f}s"
            )

    async def _process_files_batch(
        self, files_batch: list, repository: Repository
    ) -> int:
        """Process a batch of files with optimizations"""
        processed_count = 0

        # Use executor for CPU-bound parsing tasks
        parsing_tasks = []

        for file_data in files_batch:
            if file_data.size > MAX_FILE_SIZE:
                logger.warning(
                    f"Skipping large file {file_data.path} ({file_data.size} bytes)"
                )
                continue

            # Submit parsing task to thread pool
            task = asyncio.get_event_loop().run_in_executor(
                self._executor, self._parse_file_content, file_data
            )
            parsing_tasks.append((task, file_data))

        # Process parsing results
        for task, file_data in parsing_tasks:
            try:
                entities = await task

                # Create database entries in memory first
                from app.models.code_file import CodeFile

                code_file = CodeFile(
                    repository_id=repository.id,
                    path=file_data.path,
                    filename=os.path.basename(file_data.path),
                    content=(
                        file_data.content[:50000] if file_data.content else ""
                    ),  # Limit content size
                    language=file_data.language,
                    size_bytes=file_data.size,
                    line_count=(
                        len(file_data.content.splitlines()) if file_data.content else 0
                    ),
                    is_analyzed=True,
                )

                self.db.add(code_file)
                processed_count += 1

            except Exception as e:
                logger.error(f"Error processing file {file_data.path}: {str(e)}")
                continue

        # Commit batch to database
        try:
            self.db.commit()
            logger.debug(f"Committed batch of {processed_count} files")
        except Exception as e:
            logger.error(f"Failed to commit batch: {str(e)}")
            self.db.rollback()
            processed_count = 0

        return processed_count

    def _parse_file_content(self, file_data) -> list:
        """Parse file content - runs in thread pool for CPU-bound work"""
        try:
            if not self.code_parser:
                from app.services.code_parser import CodeParser

                self.code_parser = CodeParser()

            return asyncio.run(
                self.code_parser.extract_entities(
                    file_data.path, file_data.content or "", file_data.language
                )
            )
        except Exception as e:
            logger.error(f"Parsing failed for {file_data.path}: {str(e)}")
            return []

    async def _process_large_repository_optimized(
        self, repository: Repository, files: list
    ):
        """Optimized processing for large repositories"""
        total_files = len(files)
        processed_files = 0

        logger.info(
            f"Processing large repository with {total_files} files using optimizations"
        )

        async with self._batch_processing_context(repository.id):
            # Process files in batches
            for i in range(0, total_files, BATCH_SIZE):
                batch = files[i : i + BATCH_SIZE]

                try:
                    batch_processed = await self._process_files_batch(batch, repository)
                    processed_files += batch_processed

                    # Update progress
                    progress = (processed_files / total_files) * 100
                    repository.processed_files = processed_files

                    # Commit progress update
                    self.db.commit()

                    logger.info(
                        f"Processed batch {i//BATCH_SIZE + 1}/{(total_files-1)//BATCH_SIZE + 1} - {progress:.1f}% complete"
                    )

                    # Brief pause to prevent overwhelming the system
                    if i + BATCH_SIZE < total_files:
                        await asyncio.sleep(0.1)

                except Exception as e:
                    logger.error(
                        f"Failed to process batch starting at index {i}: {str(e)}"
                    )
                    continue

        return processed_files

    async def _estimate_processing_time(self, file_count: int) -> float:
        """Estimate processing time based on file count"""
        # Rough estimates based on file count
        if file_count < 100:
            return file_count * 0.1  # 0.1s per file for small repos
        elif file_count < 1000:
            return file_count * 0.05  # 0.05s per file for medium repos
        else:
            return file_count * 0.02  # 0.02s per file for large repos (batched)

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

        # Start processing in the background with proper task management
        import asyncio

        from app.core.database import get_db

        async def background_process():
            """Background processing with its own database session"""
            try:
                # Create a new database session for the background task
                db_session = next(get_db())
                service = RepositoryService(db_session)

                # Fetch the repository with the new session
                fresh_repo = (
                    db_session.query(Repository)
                    .filter(Repository.id == db_repo.id)
                    .first()
                )
                if fresh_repo:
                    await service.process_repository(fresh_repo)
                else:
                    logger.error(
                        "Repository not found for background processing",
                        repository_id=db_repo.id,
                    )

            except Exception as e:
                logger.error(
                    "Background repository processing failed",
                    repository_id=db_repo.id,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                # Update repository status to failed with new session
                try:
                    db_session = next(get_db())
                    failed_repo = (
                        db_session.query(Repository)
                        .filter(Repository.id == db_repo.id)
                        .first()
                    )
                    if failed_repo:
                        failed_repo.status = "failed"
                        failed_repo.error_message = f"{type(e).__name__}: {str(e)}"
                        db_session.commit()
                        logger.info(
                            "Updated repository status to failed",
                            repository_id=db_repo.id,
                            error_message=failed_repo.error_message,
                        )
                except Exception as db_error:
                    logger.error(
                        "Failed to update repository status", error=str(db_error)
                    )
            finally:
                if "db_session" in locals():
                    db_session.close()

        # Create and schedule the background task
        task = asyncio.create_task(background_process())

        # Don't await the task - let it run in background
        # But ensure it doesn't get garbage collected
        if not hasattr(self, "_background_tasks"):
            self._background_tasks = set()
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        logger.info(
            "Repository created and queued for processing",
            repository_id=db_repo.id,
            name=db_repo.name,
        )
        return db_repo

    async def upload_files(self, repository: Repository, files: list) -> Repository:
        """Upload files to repository and save them to database"""
        import os

        from app.models.code_file import CodeFile

        uploaded_count = 0
        total_files = len(files)

        # Update repository with total file count and broadcast
        repository.total_files = total_files
        repository.status = "processing"
        self.db.commit()
        await self._broadcast_repository_status(
            repository, message="Starting file upload"
        )

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
            logger.info(
                "Starting process_repository",
                repository_id=repository.id,
                url=repository.url,
            )

            if repository.status == "completed" and not force_reprocess:
                logger.info("Repository already completed", repository_id=repository.id)
                return repository

            # Start processing
            repository.status = "processing"
            repository.error_message = None
            self.db.commit()
            await self._broadcast_repository_status(repository)
            logger.info(
                "Set repository status to processing", repository_id=repository.id
            )

            # Process repository files
            try:
                logger.info(
                    "About to call process_repository_files",
                    repository_id=repository.id,
                )
                await self.process_repository_files(repository)
                repository.status = "completed"
                await self._broadcast_repository_status(
                    repository, message="Processing completed successfully"
                )
                logger.info(
                    "process_repository_files completed successfully",
                    repository_id=repository.id,
                )

                logger.info(
                    "Repository processing completed",
                    repository_id=repository.id,
                    total_files=repository.total_files,
                    processed_files=repository.processed_files,
                )

            except Exception as e:
                # Discard any half-written work so recording the failure can't fail too
                self.db.rollback()
                repository.status = "failed"
                repository.error_message = f"{type(e).__name__}: {str(e)}"
                await self._broadcast_repository_status(
                    repository, error=str(e), message="Processing failed"
                )
                logger.error(
                    "Repository processing failed",
                    repository_id=repository.id,
                    error=str(e),
                    error_type=type(e).__name__,
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

    async def _detect_framework(self, files) -> str:
        """Detect framework based on files and dependencies"""
        try:
            framework_indicators = {
                "react": [
                    "package.json",
                    "jsx",
                    "tsx",
                    "react",
                    "react-dom",
                    "next.config.js",
                    "gatsby-config.js",
                ],
                "vue": [
                    "vue.config.js",
                    "nuxt.config.js",
                    "vue",
                    ".vue",
                    "package.json",
                ],
                "angular": ["angular.json", "ng", "@angular/core", "package.json"],
                "svelte": ["svelte.config.js", ".svelte", "svelte", "package.json"],
                "django": ["django", "manage.py", "settings.py", "requirements.txt"],
                "flask": ["flask", "app.py", "requirements.txt"],
                "fastapi": ["fastapi", "main.py", "requirements.txt"],
                "express": ["express", "app.js", "server.js", "package.json"],
                "spring": ["pom.xml", "spring", "application.properties"],
                "laravel": ["composer.json", "artisan", "laravel"],
            }

            # Check for package.json and analyze dependencies
            package_json_file = None
            for file in files:
                if file.filename == "package.json":
                    package_json_file = file
                    break

            if package_json_file:
                import json

                try:
                    package_data = json.loads(package_json_file.content)
                    dependencies = {}
                    dependencies.update(package_data.get("dependencies", {}))
                    dependencies.update(package_data.get("devDependencies", {}))

                    # Check for React
                    if any(
                        dep in dependencies
                        for dep in ["react", "react-dom", "next", "gatsby"]
                    ):
                        if "next" in dependencies:
                            return "next.js"
                        elif "gatsby" in dependencies:
                            return "gatsby"
                        else:
                            return "react"

                    # Check for Vue
                    elif any(
                        dep in dependencies for dep in ["vue", "nuxt", "@vue/cli"]
                    ):
                        if "nuxt" in dependencies:
                            return "nuxt.js"
                        else:
                            return "vue"

                    # Check for Angular
                    elif any(dep.startswith("@angular") for dep in dependencies):
                        return "angular"

                    # Check for Svelte
                    elif "svelte" in dependencies:
                        return "svelte"

                    # Check for Express
                    elif "express" in dependencies:
                        return "express"

                except json.JSONDecodeError:
                    pass

            # Check file patterns for other frameworks
            file_names = [file.filename for file in files]
            file_paths = [file.path for file in files]

            # Python frameworks
            if any("manage.py" in name for name in file_names):
                return "django"
            elif any(
                "app.py" in name or "flask" in path.lower()
                for name, path in zip(file_names, file_paths)
            ):
                return "flask"
            elif any("main.py" in name for name in file_names) and any(
                "fastapi" in file.content.lower()
                for file in files
                if file.filename == "main.py"
            ):
                return "fastapi"

            # Java frameworks
            elif any("pom.xml" in name for name in file_names):
                return "spring"

            # PHP frameworks
            elif any("composer.json" in name for name in file_names):
                return "laravel"

            # Default return null if no framework detected
            return None

        except Exception as e:
            logger.error("Failed to detect framework", error=str(e))
            return None

    # WebSocket broadcast methods for real-time updates
    async def _broadcast_repository_status(self, repository: Repository, **kwargs):
        """Broadcast repository status update via WebSocket"""
        try:
            from app.services.websocket_service import websocket_manager

            await websocket_manager.send_repository_status(
                repository_id=repository.id,
                status=repository.status,
                name=repository.name,
                processed_files=repository.processed_files,
                total_files=repository.total_files,
                **kwargs,
            )
        except Exception as e:
            logger.warning(
                "Failed to broadcast repository status",
                repository_id=repository.id,
                error=str(e),
            )

    async def process_repository_files(self, repository: Repository):
        """
        Process all files in repository for Algolia indexing.
        Real implementation: GitHub API → Code Parsing → Algolia Indexing
        """
        try:
            import os

            from app.services.algolia_service import AlgoliaService
            from app.services.code_parser import CodeParser
            from app.services.github_service import GitHubService

            logger.info(
                "Starting repository processing",
                repository_id=repository.id,
                url=repository.url,
            )

            # Check required environment variables
            if not os.getenv("ALGOLIA_APP_ID") or not os.getenv(
                "ALGOLIA_ADMIN_API_KEY"
            ):
                error_msg = "Algolia credentials not configured. Set ALGOLIA_APP_ID and ALGOLIA_ADMIN_API_KEY environment variables."
                logger.error(error_msg, repository_id=repository.id)
                repository.status = "failed"
                repository.error_message = error_msg
                self.db.commit()
                raise Exception(error_msg)

            if not repository.url:
                error_msg = "Repository URL is required for processing"
                logger.error(error_msg, repository_id=repository.id)
                repository.status = "failed"
                repository.error_message = error_msg
                self.db.commit()
                raise Exception(error_msg)

            # 1. GitHub API: Download repository files
            github_service = GitHubService()
            logger.info("Fetching files from GitHub", repository_url=repository.url)
            files = await github_service.get_repository_files(repository.url)
            logger.info("GitHub files retrieved", file_count=len(files) if files else 0)

            if not files:
                raise IngestionError("No supported code files found in repository")

            # 2. Initialize services
            code_parser = CodeParser()
            algolia_service = AlgoliaService()

            # Setup Algolia index if needed
            await algolia_service.setup_index_settings()

            # Replace the previous run's data. This happens only after a successful
            # fetch, so a transient GitHub error doesn't wipe a working index.
            await self._clear_repository_data(repository.id, algolia_service)

            # 3. Process each file and extract entities
            total_entities = 0
            processed_files = 0
            failed_files = 0

            for file in files:
                try:
                    # Save file to database
                    import os

                    from app.models.code_file import CodeFile

                    code_file = CodeFile(
                        repository_id=repository.id,
                        file_path=file.path,
                        file_name=os.path.basename(file.path),
                        content=file.content,
                        language=file.language,
                        size_bytes=file.size,
                        line_count=len(file.content.splitlines()),
                        is_analyzed=False,
                    )

                    self.db.add(code_file)
                    self.db.commit()
                    self.db.refresh(code_file)

                    # Extract code entities from file
                    entities = await code_parser.extract_entities(
                        file.path, file.content, file.language
                    )

                    logger.info(
                        "Entity extraction result",
                        file_path=file.path,
                        language=file.language,
                        entities_found=len(entities),
                        file_size=len(file.content),
                    )

                    if entities:
                        logger.info(
                            "Saving entities to database",
                            file_path=file.path,
                            entities_count=len(entities),
                        )

                        # Save entities to database
                        from app.models.code_entity import CodeEntity as CodeEntityModel

                        for entity in entities:
                            logger.debug(
                                "Saving entity",
                                entity_type=entity.entity_type,
                                entity_name=entity.name,
                                file_path=file.path,
                            )

                            db_entity = CodeEntityModel(
                                file_id=code_file.id,
                                repository_id=repository.id,
                                entity_type=entity.entity_type,
                                entity_name=entity.name,
                                start_line=entity.line_start,
                                end_line=entity.line_end,
                                signature=entity.content,
                                docstring=entity.description,
                                entity_metadata={
                                    "parameters": entity.parameters,
                                    "return_type": entity.return_type,
                                },
                            )
                            self.db.add(db_entity)

                        self.db.commit()

                        logger.info(
                            "Entities saved to database",
                            file_path=file.path,
                            entities_saved=len(entities),
                        )

                        # Index entities in Algolia
                        success = await algolia_service.batch_index_entities(
                            entities, repository.id, file.path, file.language
                        )

                        if success:
                            total_entities += len(entities)
                            logger.info(
                                "Entities indexed in Algolia",
                                file_path=file.path,
                                entities_indexed=len(entities),
                            )
                    else:
                        logger.warning(
                            "No entities found in file",
                            file_path=file.path,
                            language=file.language,
                            file_size=len(file.content),
                        )

                    # Mark file as analyzed
                    code_file.is_analyzed = True
                    self.db.commit()

                    processed_files += 1

                    # Update progress periodically
                    if processed_files % 10 == 0:
                        repository.processed_files = processed_files
                        self.db.commit()

                        logger.info(
                            "Repository processing progress",
                            repository_id=repository.id,
                            processed_files=processed_files,
                            total_files=len(files),
                            total_entities=total_entities,
                        )

                except Exception as e:
                    # Without a rollback every later file fails with PendingRollbackError
                    self.db.rollback()
                    failed_files += 1
                    logger.error(
                        "Failed to process file",
                        repository_id=repository.id,
                        file_path=file.path,
                        error=str(e),
                    )
                    continue

            # 4. Update repository status
            repository.total_files = len(files)
            repository.processed_files = processed_files

            if total_entities == 0:
                raise IngestionError(
                    f"No code entities were indexed from {len(files)} files "
                    f"({failed_files} failed to process)"
                )

            repository.status = "completed"

            # Calculate total lines from all files
            repository.total_lines = sum(
                len(file.content.splitlines()) for file in files
            )

            # Update language from most common PROGRAMMING language (prioritize over docs)
            if files:
                languages = [
                    f.language for f in files if f.language not in ["text", "markdown"]
                ]

                # If we have programming languages, use them
                if languages:
                    from collections import Counter

                    repository.language = Counter(languages).most_common(1)[0][0]
                else:
                    # Fallback to any language if no programming languages found
                    all_languages = [f.language for f in files if f.language != "text"]
                    if all_languages:
                        from collections import Counter

                        repository.language = Counter(all_languages).most_common(1)[0][
                            0
                        ]

            # Detect framework based on files and dependencies
            repository.framework = await self._detect_framework(files)

            logger.info(
                "Repository processing completed",
                repository_id=repository.id,
                total_files=len(files),
                processed_files=processed_files,
                total_entities=total_entities,
                language=repository.language,
            )

        except Exception as e:
            logger.error(
                "Repository processing failed",
                repository_id=repository.id,
                error=str(e),
            )
            repository.status = "failed"
            raise

    async def _clear_repository_data(self, repository_id: int, algolia_service):
        """Remove a repository's stored files, entities and Algolia records"""
        from app.models.code_entity import CodeEntity
        from app.models.code_file import CodeFile

        if not await algolia_service.delete_repository_index(repository_id, wait=True):
            raise IngestionError(
                "Could not remove previously indexed records from Algolia"
            )

        # Entities reference files, so delete them first
        self.db.query(CodeEntity).filter(
            CodeEntity.repository_id == repository_id
        ).delete(synchronize_session=False)
        self.db.query(CodeFile).filter(
            CodeFile.repository_id == repository_id
        ).delete(synchronize_session=False)
        self.db.commit()

    async def delete_repository(self, repository_id: int):
        from app.models.repository import Repository
        from app.services.algolia_service import AlgoliaService

        repository = (
            self.db.query(Repository).filter(Repository.id == repository_id).first()
        )
        if not repository:
            raise Exception(f"Repository {repository_id} not found")

        # Delete Algolia index entries for this repository
        algolia_service = AlgoliaService()
        await algolia_service.delete_repository_index(repository_id)

        self.db.delete(repository)
        self.db.commit()
