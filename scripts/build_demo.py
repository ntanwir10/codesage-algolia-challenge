"""Build the public read-only demo for Vercel in build/demo/.

Indexes a few public repositories into a fresh SQLite file and their own Algolia index, then lays
out what Vercel deploys: the backend code, that file and the built dashboard. Indexing uses the
Algolia admin key and GitHub token from --env-file; the deployed demo gets a search-only key.
`make demo-build` runs this, and `make demo-deploy` uploads the folder.
"""

import argparse
import asyncio
import contextlib
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "demo"
DATABASE = OUT / "demo.db"
INDEX = "codesage_demo"
REPOSITORIES = (
    "https://github.com/pmndrs/zustand",
    "https://github.com/pallets/click",
    "https://github.com/ntanwir10/codesage-algolia-challenge",
)


async def index_repositories() -> None:
    from algoliasearch.http.exceptions import RequestException

    from app.core.database import SessionLocal, engine
    from app.core.migrations import upgrade_database
    from app.schemas.repository import RepositoryCreate
    from app.services import repository_service
    from app.services.algolia_service import AlgoliaService

    algolia = AlgoliaService()
    if not algolia.is_available():
        sys.exit("Algolia isn't configured: set ALGOLIA_APP_ID and ALGOLIA_ADMIN_API_KEY in the env file")
    # An earlier build's records would otherwise turn up in searches across repositories
    try:
        task = algolia.client.clear_objects(index_name=INDEX)
        algolia.client.wait_for_task(index_name=INDEX, task_id=task.task_id)
    except RequestException as e:
        if e.status_code != 404:  # no index yet
            raise
    upgrade_database(engine)
    with SessionLocal() as db:
        for url in REPOSITORIES:
            repository = await repository_service.add_repository(db, RepositoryCreate(url=url))
            while repository_service.is_processing(repository.id):
                await asyncio.sleep(1)
            db.refresh(repository)
            print(f"{repository.name}: {repository.status}, {repository.total_files} files")
            if repository.status != "completed":
                sys.exit(f"{repository.name} failed: {repository.error_message}")
    engine.dispose()


def checkpoint() -> None:
    """Fold the WAL into the file: a read-only server opens it immutable and can't replay one"""
    with contextlib.closing(sqlite3.connect(DATABASE)) as db:
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("VACUUM")


def assemble() -> None:
    backend = ROOT / "backend"
    for name in ("app", "codesage_mcp", "alembic"):
        shutil.rmtree(OUT / name, ignore_errors=True)
        shutil.copytree(backend / name, OUT / name, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(backend / "requirements.txt", OUT)
    for name in ("vercel.json", "index.py", ".python-version"):
        shutil.copy2(ROOT / "deployment" / "vercel" / name, OUT)
    # Built with no key: the demo needs none, and a local one must never reach a public page
    env = {**os.environ, "VITE_CODESAGE_API_KEY": "", "VITE_API_BASE_URL": "/api/v1"}
    command = ["npm", "run", "build", "--", "--outDir", str(OUT / "public"), "--emptyOutDir"]
    subprocess.run(command, cwd=ROOT / "frontend", env=env, check=True)
    # Vercel serves public/ only for paths that are files; index.py answers the dashboard's routes
    shutil.copy2(OUT / "public" / "index.html", OUT / "dashboard.html")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env-file", type=Path, default=ROOT / "backend" / ".env",
                        help="where the Algolia admin key and GitHub token come from (default backend/.env)")
    parser.add_argument("--reindex", action="store_true",
                        help="rebuild the data even if build/demo/demo.db exists (clears the demo index)")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.reindex or not DATABASE.exists():
        DATABASE.unlink(missing_ok=True)
        # Set before load_dotenv, which keeps variables that are already set
        os.environ.update({
            "DATABASE_URL": f"sqlite:///{DATABASE}", "ALGOLIA_INDEX_NAME": INDEX, "EMBEDDING_API_KEY": "",
            "INDEX_WORKERS": "inline", "READ_ONLY": "false", "REFRESH_INTERVAL_MINUTES": "0",
        })
        from dotenv import load_dotenv

        if not load_dotenv(args.env_file):
            sys.exit(f"{args.env_file} not found or empty; pass --env-file")
        sys.path.insert(0, str(ROOT / "backend"))
        asyncio.run(index_repositories())
        checkpoint()
    assemble()
    print(f"Ready in {OUT}; run `make demo-deploy`")


if __name__ == "__main__":
    main()
