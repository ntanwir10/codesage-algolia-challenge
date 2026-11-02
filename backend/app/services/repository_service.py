"""
CodeSage - MCP-First Code Discovery: Repository Service

Turns a GitHub repository into searchable code: fetch its files, parse them
into code entities, store both in the database and index the entities in
Algolia. Processing runs as an in-process background job, at most one per
repository, and always ends in `completed` or `failed` with a reason.
"""

import asyncio
import contextlib
import json
import time
import uuid
import weakref
from collections import Counter
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.database import SessionLocal
from app.core.security import failure_message
from app.models.code_entity import CodeEntity
from app.models.code_file import CodeFile
from app.models.repository import Repository
from app.schemas.repository import RepositoryCreate
from app.services import embeddings, git_source
from app.services.github_service import GitHubService, RepositoryCheckError, parse_repository_url

logger = structlog.get_logger()

# Files written to the database per commit
DB_BATCH_SIZE = 200

# Appended when a reprocess fails but the previous run's index is untouched and stays searchable
PREVIOUS_INDEX_NOTE = " Search still uses the previous index."

# What a failed reprocess puts back, so the repository shows the run that is still searchable
_RUN_FIELDS = ("total_files", "processed_files", "total_lines", "language", "framework",
               "commit_sha", "processed_at")

# Languages whose files are documentation or data rather than program source
NON_PROGRAMMING_LANGUAGES = {"text", "markdown", "json", "yaml", "xml", "css", "scss", "html"}

# An incremental run deletes changed files' old Algolia records this many paths per request
PATHS_PER_DELETE = 50

# What an incremental run copies from an unchanged file's previous entities
_ENTITY_COPY = [
    c.name for c in CodeEntity.__table__.columns if c.name not in ("id", "file_id", "created_at", "updated_at")
]

# Background jobs keyed by repository id. Module level, so a job outlives the
# request that started it and a repository is never processed twice at once.
_jobs: dict[int, asyncio.Task] = {}

# Each run holds up to GitHubService.max_total_bytes of files in memory; cap how many run at once
MAX_CONCURRENT_RUNS = 2
_run_slots: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = (
    weakref.WeakKeyDictionary()
)


def _run_slot() -> asyncio.Semaphore:
    """This event loop's semaphore: one shared across loops raises once both have waited on it"""
    loop = asyncio.get_running_loop()
    if loop not in _run_slots:
        _run_slots[loop] = asyncio.Semaphore(MAX_CONCURRENT_RUNS)
    return _run_slots[loop]


ALGOLIA_MISSING = "Search indexing is not configured on the server (Algolia credentials are missing)."


class RepositoryAddError(Exception):
    """add_repository refused; the REST endpoint and the MCP tool both report these"""

    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: dict[str, str] | None = None,
        repository_id: int | None = None,
    ):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers
        self.repository_id = repository_id  # the existing row, for a duplicate (409)


class IngestionError(Exception):
    """A processing run that would leave the repository with nothing searchable"""

    user_facing = True  # messages are written for the person who added the repository


class RepositoryBusyError(Exception):
    """The repository already has a processing job running"""


def is_processing(repository_id: int) -> bool:
    task = _jobs.get(repository_id)
    return task is not None and not task.done()


def start_processing(
    repository_id: int, force_reprocess: bool = False, incremental: bool = False
) -> asyncio.Task:
    """Schedule a background processing job for one repository"""
    if is_processing(repository_id):
        raise RepositoryBusyError(f"Repository {repository_id} is already being processed")

    task = asyncio.create_task(_run_job(repository_id, force_reprocess, incremental))
    _jobs[repository_id] = task

    def _forget(finished: asyncio.Task):
        if _jobs.get(repository_id) is finished:
            del _jobs[repository_id]

    task.add_done_callback(_forget)
    return task


async def _run_job(repository_id: int, force_reprocess: bool, incremental: bool = False):
    """Process one repository with its own database session"""
    try:
        with SessionLocal() as db:
            repository = db.get(Repository, repository_id)
            if repository is None:
                logger.error("Repository not found for processing", repository_id=repository_id)
                return
            await RepositoryService(db).process_repository(repository, force_reprocess, incremental)
    except Exception as e:
        # process_repository records its own failures; this is a last resort
        logger.error(
            "Background repository job crashed",
            repository_id=repository_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        _fail_if_still_processing(repository_id)


def _fail_if_still_processing(repository_id: int) -> None:
    """After a crash, don't leave the row 'processing' with no job behind it until a restart"""
    try:
        with SessionLocal() as db:
            repository = db.get(Repository, repository_id)
            if repository is not None and repository.status == "processing":
                repository.status = "failed"
                repository.error_message = "Processing stopped unexpectedly; reprocess the repository"
                db.commit()
    except Exception as e:
        logger.error("Could not mark the crashed job failed", repository_id=repository_id, error=str(e))


async def _to_thread_to_completion(fn):
    """asyncio.to_thread that, if the caller is cancelled, still waits for the thread, so
    the caller's finally (freeing the job slot) can't run while the thread uses its session"""
    future = asyncio.ensure_future(asyncio.to_thread(fn))
    try:
        return await asyncio.shield(future)
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            await future
        raise


def recover_interrupted_jobs(db: Session) -> int:
    """Fail repositories a previous server process left pending or processing"""
    stuck = (
        db.query(Repository)
        .filter(Repository.status.in_(("pending", "processing")))
        .all()
    )
    for repository in stuck:
        repository.status = "failed"
        repository.error_message = (
            "Processing was interrupted by a server restart; reprocess the repository"
        )
    db.commit()
    if stuck:
        logger.warning("Marked interrupted repositories as failed", count=len(stuck))
    return len(stuck)


class RepositoryService:
    """Repository lifecycle: create, process, delete, statistics"""

    def __init__(self, db: Session):
        self.db = db
        self._run_id = ""  # tags this run's Algolia records
        self._cut = 0  # this repository's rows up to this id are from before this run
        self._indexed = False  # set once this run has sent records to Algolia

    async def create_repository(self, repository_data: RepositoryCreate) -> Repository:
        """Create a repository and schedule its processing"""
        db_repo = Repository(
            name=repository_data.name,
            description=repository_data.description,
            url=repository_data.url,
            branch=repository_data.branch,
            language=repository_data.language,
            status="pending",
            total_files=0,
            processed_files=0,
            total_lines=0,
        )
        self.db.add(db_repo)
        self.db.commit()
        self.db.refresh(db_repo)

        start_processing(db_repo.id)
        logger.info(
            "Repository created and queued for processing",
            repository_id=db_repo.id,
            name=db_repo.name,
        )
        return db_repo

    async def process_repository(
        self, repository: Repository, force_reprocess: bool = False, incremental: bool = False
    ) -> Repository:
        """Process a repository, recording `completed` or `failed` with a reason"""
        if repository.status == "completed" and not force_reprocess:
            logger.info("Repository already completed", repository_id=repository.id)
            return repository

        had_index = repository.status == "completed"
        previous = {field: getattr(repository, field) for field in _RUN_FIELDS}
        repository.status = "processing"
        repository.processed_files = 0  # the previous run's count would show as progress
        repository.error_message = None
        self.db.commit()
        await self._broadcast_repository_status(repository)
        self._start_run(repository.id)

        try:
            # A run already shows "processing" while it waits here for a free slot
            async with _run_slot():
                started = time.monotonic()  # after the wait for a slot, so it times the run itself
                await self.process_repository_files(repository, incremental)
        except Exception as e:
            # Discard any half-written work so recording the failure can't fail too
            self.db.rollback()
            await self._discard_run(repository.id)
            reason = failure_message(e)
            if had_index:
                # The previous run's rows and records were never touched, so it stays searchable
                for field, value in previous.items():
                    setattr(repository, field, value)
                repository.status = "completed"
                failure = f"Reprocessing failed: {reason.rstrip('.')}."
                repository.error_message = failure[: 500 - len(PREVIOUS_INDEX_NOTE)] + PREVIOUS_INDEX_NOTE
            else:
                repository.status = "failed"
                repository.error_message = reason
            self.db.commit()
            logger.error(
                "Repository processing failed",
                repository_id=repository.id,
                error=repository.error_message,
                error_type=type(e).__name__,
                kept_previous_index=had_index,
            )
            if had_index:
                await self._broadcast_repository_status(repository, message=repository.error_message)
            else:
                await self._broadcast_repository_status(
                    repository, error=repository.error_message, message="Processing failed"
                )
            return repository

        repository.status = "completed"
        repository.processed_at = datetime.now(UTC)
        self.db.commit()
        logger.info(
            "Repository processing completed",
            repository_id=repository.id,
            total_files=repository.total_files,
            processed_files=repository.processed_files,
            duration_s=round(time.monotonic() - started, 1),
        )
        await self._broadcast_repository_status(
            repository, message=repository.error_message or "Processing completed successfully"
        )
        return repository

    async def process_repository_files(self, repository: Repository, incremental: bool = False):
        """GitHub fetch → parse → store → Algolia index. Raises on any failure.

        Incremental: a file whose content and language match the previous run's row is reused.
        Its rows are copied without parsing and its Algolia records are left in place.
        """
        from app.services.algolia_service import AlgoliaService
        from app.services.code_parser import CodeParser
        from app.services.git_source import GitSource
        from app.services.github_service import GitHubService

        algolia_service = AlgoliaService()
        if not algolia_service.is_available():
            raise IngestionError(
                "Algolia credentials not configured. Set ALGOLIA_APP_ID and ALGOLIA_ADMIN_API_KEY."
            )
        if not repository.url:
            raise IngestionError("Repository URL is required for processing")

        # 1. Git host: list and download the repository's code files.
        # No branch means the repository's default branch. github.com uses its REST API;
        # every other host is cloned with git.
        host = parse_repository_url(repository.url)[0]
        github = GitHubService() if host == "github.com" else GitSource()
        files = await github.get_repository_files(repository.url, repository.branch or None)
        repository.commit_sha = github.commit_sha
        logger.info("Repository files retrieved", repository_id=repository.id, file_count=len(files))
        if not files:
            raise IngestionError("No supported code files found in repository")

        await algolia_service.setup_index_settings()
        # The previous run's rows and records stay until this run is complete (step 4)

        # 2. Parse files and store them with their entities, a batch per commit
        code_parser = CodeParser()
        documents = []
        processed_files = 0
        failed_files = 0
        unparsed_files = 0
        previous: dict[str, CodeFile] = {}
        if incremental:
            previous = {
                row.file_path: row
                for row in self.db.query(CodeFile)
                .options(selectinload(CodeFile.entities))
                .filter(CodeFile.repository_id == repository.id, CodeFile.id <= self._cut)
            }
        kept: set[str] = set()  # reused paths whose rows committed; their old records stay

        for start in range(0, len(files), DB_BATCH_SIZE):
            batch = files[start : start + DB_BATCH_SIZE]
            batch_documents = []
            batch_reused = []
            for file in batch:
                old = previous.get(file.path)
                reuse = old is not None and old.content == file.content and old.language == file.language
                entities = []
                if not reuse:
                    try:
                        entities = await code_parser.extract_entities(
                            file.path, file.content, file.language
                        )
                    except Exception as e:
                        # Still stored, just without entities; the run reports it
                        unparsed_files += 1
                        logger.error(
                            "Failed to parse code file",
                            file_path=file.path,
                            error=failure_message(e),
                        )
                code_file = CodeFile(
                    repository_id=repository.id,
                    file_path=file.path,
                    content=file.content,
                    language=file.language,
                    line_count=len(file.content.splitlines()),
                )
                if reuse:
                    code_file.entities = [
                        CodeEntity(**{name: getattr(entity, name) for name in _ENTITY_COPY})
                        for entity in old.entities
                    ]
                    batch_reused.append(file.path)
                else:
                    code_file.entities = [
                        CodeEntity(
                            repository_id=repository.id,
                            entity_type=entity.entity_type,
                            entity_name=entity.name[:255],
                            start_line=entity.line_start,
                            end_line=entity.line_end,
                            signature=entity.content,
                            docstring=entity.description,
                            entity_metadata={
                                "parameters": entity.parameters,
                                "return_type": entity.return_type,
                            },
                        )
                        for entity in entities
                    ]
                    batch_documents.extend(
                        algolia_service.build_documents(
                            entities, repository.id, file.path, file.language, self._run_id
                        )
                    )
                self.db.add(code_file)

            try:
                # Flushing a batch can write thousands of rows; keep it off the event loop.
                # The job owns this session, so using it from a worker thread is safe.
                await asyncio.to_thread(self.db.commit)
            except Exception as e:
                # Without a rollback every later batch fails with PendingRollbackError
                self.db.rollback()
                failed_files += len(batch)
                logger.error(
                    "Failed to store file batch",
                    repository_id=repository.id,
                    first_file=batch[0].path,
                    error=failure_message(e),
                )
                continue

            documents.extend(batch_documents)
            kept.update(batch_reused)
            processed_files += len(batch)
            repository.processed_files = processed_files
            repository.total_files = len(files)
            self.db.commit()
            await self._broadcast_repository_status(repository)

        repository.total_files = len(files)
        repository.processed_files = processed_files
        repository.total_lines = sum(len(f.content.splitlines()) for f in files)

        # An incremental run where no indexed file changed has nothing new, and that's fine
        if not documents and not kept:
            raise IngestionError(
                f"No code entities were indexed from {len(files)} files "
                f"({failed_files} failed to process)"
            )

        # 3. Algolia: index everything in chunked batch requests
        if documents:
            self._indexed = True
            if not await algolia_service.index_documents(documents):
                raise IngestionError("Algolia rejected the indexing request")

        # 3b. Semantic search (bring your own key): vectors for this run's definitions that lack
        # one from the current model. A failure leaves keyword search intact and is reported below
        unembedded = await self._embed_definitions(repository.id) if embeddings.is_configured() else 0

        # 4. This run is complete: drop the previous run's rows and records. Not waited on:
        # Algolia applies an index's tasks in order, and a timeout must not discard a good run
        await self._delete_rows(repository.id, previous=True)
        if kept:
            # Earlier records stay for the reused files; every other previous path goes
            stale_records = not await self._delete_old_records(
                algolia_service, repository.id, sorted(set(previous) - kept)
            )
        else:
            stale_records = not await algolia_service.delete_repository_index(
                repository.id, run_filter=f'NOT run_id:"{self._run_id}"'
            )

        programming = [f.language for f in files if f.language not in NON_PROGRAMMING_LANGUAGES]
        if programming:
            repository.language = Counter(programming).most_common(1)[0][0]
        repository.framework = self._detect_framework(files)

        # The run still completes, but a partial index must say what it left out
        problems = []
        if failed_files:
            problems.append(f"{failed_files} of {len(files)} files could not be stored")
        if unparsed_files:
            problems.append(f"{unparsed_files} files could not be parsed")
        if github.skipped_files:
            problems.append(
                f"{github.skipped_files} files over the {github.max_files}-file or "
                f"{github.max_total_bytes // 2**20} MB limit were skipped"
            )
        if unembedded:
            problems.append(f"{unembedded} definitions have no semantic search vectors (the embedding API failed)")
        if github.listing_truncated:
            problems.append(
                "the repository is too large to list in full, so some directories were not indexed"
            )
        if stale_records and kept:
            problems.append(
                "search still holds old records for some changed or removed files "
                "until they change again or a full reprocess"
            )
        elif stale_records:
            problems.append("search still holds the previous run's records until the next run")
        if problems:
            repository.error_message = "Partially indexed: " + "; ".join(problems)

        logger.info(
            "Repository indexed",
            repository_id=repository.id,
            total_files=len(files),
            processed_files=processed_files,
            failed_files=failed_files,
            reused_files=len(kept),
            indexed_entities=len(documents),
            language=repository.language,
        )

    async def get_repository_statistics(self, repository: Repository) -> dict:
        """File, line and entity counts from the stored data"""
        entity_counts = dict(
            self.db.query(CodeEntity.entity_type, func.count())
            .filter(CodeEntity.repository_id == repository.id)
            .group_by(CodeEntity.entity_type)
            .all()
        )
        language_counts = dict(
            self.db.query(CodeFile.language, func.count())
            .filter(CodeFile.repository_id == repository.id)
            .group_by(CodeFile.language)
            .all()
        )
        # The languages search can filter on: only those with indexed entities
        entity_languages = dict(
            self.db.query(CodeFile.language, func.count())
            .select_from(CodeEntity)
            .join(CodeFile, CodeEntity.file_id == CodeFile.id)
            .filter(CodeEntity.repository_id == repository.id)
            .group_by(CodeFile.language)
            .all()
        )
        return {
            "repository_id": repository.id,
            "status": repository.status,
            "total_files": repository.total_files,
            "processed_files": repository.processed_files,
            "total_lines": repository.total_lines,
            "total_entities": sum(entity_counts.values()),
            "entities_by_type": entity_counts,
            "files_by_language": language_counts,
            "entities_by_language": entity_languages,
            "language": repository.language,
            "framework": repository.framework,
        }

    @staticmethod
    def _detect_framework(files) -> str | None:
        """Best-effort framework from package.json dependencies and Python imports"""
        js_frameworks = [
            ("next", "nextjs"), ("@angular/core", "angular"), ("vue", "vue"),
            ("svelte", "svelte"), ("react", "react"), ("express", "express"),
        ]
        python_frameworks = ["django", "fastapi", "flask"]

        for file in files:
            if file.filename != "package.json":
                continue
            try:
                manifest = json.loads(file.content)
                dependencies = {
                    **manifest.get("dependencies", {}),
                    **manifest.get("devDependencies", {}),
                }
            except (ValueError, AttributeError, TypeError):
                continue  # not JSON, or not an object of objects (e.g. a fixture holding a list)
            for package, framework in js_frameworks:
                if package in dependencies:
                    return framework

        python_sources = "\n".join(f.content for f in files if f.language == "python")
        for framework in python_frameworks:
            if f"import {framework}" in python_sources or f"from {framework}" in python_sources:
                return framework
        return None

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

    async def _clear_repository_data(self, repository_id: int, algolia_service, wait: bool = True):
        """Remove a repository's stored files, entities and Algolia records.

        A plain delete passes wait=False: Algolia applies an index's tasks in order, so records
        indexed later under a reused id still land after the delete instead of being removed by it.
        """
        if not await algolia_service.delete_repository_index(repository_id, wait=wait):
            raise IngestionError("Could not remove previously indexed records from Algolia")

        def clear_rows():
            # Entities reference files, so delete them first
            self.db.query(CodeEntity).filter(CodeEntity.repository_id == repository_id).delete(
                synchronize_session=False
            )
            self.db.query(CodeFile).filter(CodeFile.repository_id == repository_id).delete(
                synchronize_session=False
            )
            self.db.commit()

        # Large repositories have thousands of rows to delete; keep it off the event loop
        await _to_thread_to_completion(clear_rows)

    def _start_run(self, repository_id: int) -> None:
        self._run_id = uuid.uuid4().hex[:12]
        # Row ids only grow, so this repository's rows up to here are the previous run's
        self._cut = (
            self.db.query(func.max(CodeFile.id))
            .filter(CodeFile.repository_id == repository_id)
            .scalar()
        ) or 0
        self._indexed = False

    async def _delete_rows(self, repository_id: int, *, previous: bool) -> None:
        """Delete the previous run's rows (previous=True) or this run's"""
        cut = self._cut

        def delete():
            # Entities reference files, so delete them first
            entity_run = CodeEntity.file_id <= cut if previous else CodeEntity.file_id > cut
            file_run = CodeFile.id <= cut if previous else CodeFile.id > cut
            self.db.query(CodeEntity).filter(CodeEntity.repository_id == repository_id, entity_run).delete(
                synchronize_session=False
            )
            self.db.query(CodeFile).filter(CodeFile.repository_id == repository_id, file_run).delete(
                synchronize_session=False
            )
            self.db.commit()

        await _to_thread_to_completion(delete)

    async def _embed_definitions(self, repository_id: int) -> int:
        """Embed this run's definitions that have no vector from the current model.

        Reused files keep theirs. Returns how many are still without one: 0, or all of them
        when the API failed. The text is the kind, name and path, then the definition's lines.
        """
        model = embeddings.model_name()
        rows = (
            self.db.query(CodeEntity)
            .filter(
                CodeEntity.repository_id == repository_id,
                CodeEntity.file_id > self._cut,
                CodeEntity.entity_type != "import",
                or_(CodeEntity.embedding_model.is_(None), CodeEntity.embedding_model != model),
            )
            .all()
        )
        if not rows:
            return 0
        # Each file once, split once: a join would copy a file's content for every definition in it
        files = {
            file_id: (path, content.splitlines())
            for file_id, path, content in self.db.query(CodeFile.id, CodeFile.file_path, CodeFile.content)
            .filter(CodeFile.id.in_({entity.file_id for entity in rows}))
        }
        texts = []
        for entity in rows:
            path, lines = files[entity.file_id]
            body = lines[(entity.start_line or 1) - 1 : entity.end_line or None]
            texts.append(f"{entity.entity_type} {entity.entity_name} in {path}\n" + "\n".join(body))
        del files
        try:
            vectors = await embeddings.embed(texts)
        except embeddings.EmbeddingError as e:
            logger.warning("Could not embed definitions", repository_id=repository_id, error=str(e))
            return len(rows)
        for entity, vector in zip(rows, vectors, strict=True):
            entity.embedding, entity.embedding_model = vector, model
        await asyncio.to_thread(self.db.commit)
        return 0

    async def _delete_old_records(self, algolia_service, repository_id: int, paths: list[str]) -> bool:
        """Delete earlier runs' records for these paths; False if any request failed"""
        deleted = True
        for start in range(0, len(paths), PATHS_PER_DELETE):
            any_path = " OR ".join(
                f'file_path:"{algolia_service._escape_filter_value(path)}"'
                for path in paths[start : start + PATHS_PER_DELETE]
            )
            deleted &= await algolia_service.delete_repository_index(
                repository_id, run_filter=f'NOT run_id:"{self._run_id}" AND ({any_path})'
            )
        return deleted

    async def _discard_run(self, repository_id: int) -> None:
        """Remove what a failed run wrote; the previous run's rows and records stay as they were"""
        from app.services.algolia_service import AlgoliaService

        try:
            await self._delete_rows(repository_id, previous=False)
            if self._indexed and not await AlgoliaService().delete_repository_index(
                repository_id, run_filter=f'run_id:"{self._run_id}"'
            ):
                # The next successful run removes them along with every other old run's
                logger.warning("Could not remove a failed run's records", repository_id=repository_id)
        except Exception as e:
            self.db.rollback()
            logger.error("Could not discard a failed run", repository_id=repository_id, error=failure_message(e))

    async def delete_repository(self, repository: Repository) -> bool:
        """Delete a repository and its Algolia records.

        Returns False, leaving the database row in place, when the Algolia
        delete fails, so no orphaned records are left behind.
        """
        from app.services.algolia_service import AlgoliaService

        if is_processing(repository.id):
            raise RepositoryBusyError(f"Repository {repository.id} is being processed")

        # Hold the job slot so no run can start while the Algolia delete is awaited
        _jobs[repository.id] = asyncio.current_task()
        try:
            # Bulk-deletes the rows off the event loop, so the ORM cascade below finds none to load
            try:
                await self._clear_repository_data(repository.id, AlgoliaService(), wait=False)
            except IngestionError:
                return False

            self.db.delete(repository)
            self.db.commit()
            from app.services.websocket_service import websocket_manager

            websocket_manager.forget_repository(repository.id)
            return True
        finally:
            del _jobs[repository.id]


async def check_source(url: str, branch: str | None) -> None:
    """Pre-flight: can the repository (and branch) be read? Raises RepositoryCheckError"""
    if parse_repository_url(url)[0] == "github.com":
        await GitHubService().check_repository(url, branch)
    else:
        await git_source.check_remote(url, branch)


FRESHNESS_TTL = 600  # seconds; a page polling every few seconds still asks the host once per 10 minutes
_freshness: dict[tuple, tuple[float, dict]] = {}


async def index_freshness(repository: Repository) -> dict:
    """Whether the indexed commit is behind the repository's branch now, cached for FRESHNESS_TTL.

    GitHub counts the commits; other hosts only say whether the branch moved. A new commit_sha,
    branch or URL is a new cache key. Raises RepositoryCheckError when the host can't be asked.
    """
    key = (repository.id, repository.url, repository.branch, repository.commit_sha)
    cached = _freshness.get(key)
    if cached and time.monotonic() - cached[0] < FRESHNESS_TTL:
        return cached[1]
    if parse_repository_url(repository.url)[0] == "github.com":
        branch, behind, changed = await GitHubService().commits_behind(
            repository.url, repository.commit_sha, repository.branch
        )
    else:
        branch, head = await git_source.remote_head(repository.url, repository.branch)
        behind, changed = None, head != repository.commit_sha
    result = {"branch": branch, "commits_behind": behind, "changed": changed, "checked_at": datetime.now(UTC)}
    _freshness[key] = (time.monotonic(), result)
    return result


async def refresh_once() -> int:
    """Start an incremental run for each completed repository whose branch has moved.

    Returns how many runs it started. One repository's problem never stops the others.
    """
    with SessionLocal() as db:
        repositories = (
            db.query(Repository)
            .filter(Repository.status == "completed", Repository.commit_sha.isnot(None))
            .order_by(Repository.id)
            .all()
        )
    started = 0
    for repository in repositories:
        if is_processing(repository.id):
            continue
        try:
            try:
                changed = (await index_freshness(repository))["changed"]
            except RepositoryCheckError as e:
                # A force-push makes GitHub's compare 404 (422 here). The run checks again,
                # and if the branch is really gone it fails and keeps the previous index
                if e.status_code != 422:
                    raise
                changed = True
            if changed:
                start_processing(repository.id, force_reprocess=True, incremental=True)
                started += 1
        except Exception as e:
            logger.warning(
                "Scheduled refresh skipped a repository",
                repository_id=repository.id,
                error=failure_message(e),
            )
    return started


async def refresh_loop(interval_minutes: float) -> None:
    """Run refresh_once every interval, waiting one interval first. Cancel it to stop."""
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            started = await refresh_once()
        except Exception as e:
            logger.error("Scheduled refresh failed", error=failure_message(e))
        else:
            if started:
                logger.info("Scheduled refresh started runs", count=started)


async def add_repository(db: Session, repository: RepositoryCreate) -> Repository:
    """Check and create a repository, and schedule its processing.

    Raises RepositoryAddError for a duplicate (409), missing Algolia credentials (503) or a
    repository the pre-flight check refuses. `repository` is already validated and normalised.
    """
    from app.services import algolia_service

    existing = (
        db.query(Repository).filter(func.lower(Repository.url) == repository.url.lower()).first()
    )
    if existing:
        name = repository.url.removeprefix("https://").removeprefix("github.com/")
        raise RepositoryAddError(409, f"{name} has already been added.", repository_id=existing.id)

    if not algolia_service.AlgoliaService().is_available():
        raise RepositoryAddError(503, ALGOLIA_MISSING)
    try:
        await check_source(repository.url, repository.branch)
    except RepositoryCheckError as e:
        raise RepositoryAddError(e.status_code, e.detail, e.headers) from e

    try:
        new_repository = await RepositoryService(db).create_repository(repository)
    except IntegrityError as e:
        # Another request added the same URL between the check above and this insert
        db.rollback()
        raise RepositoryAddError(409, f"Repository with URL {repository.url} already exists") from e

    logger.info("Repository created", repository_id=new_repository.id)
    return new_repository
