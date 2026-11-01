"""Seed the end-to-end database: one indexed repository with two files and their definitions.

playwright.config.ts runs this from backend/ before starting the e2e backend. It refuses any
database but the e2e file, so it can never touch codesage.db.
"""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

url = os.environ.get("DATABASE_URL", "")
if not url.startswith("sqlite:///") or not url.endswith("/codesage-e2e.db"):
    sys.exit(f"Refusing to seed {url!r}: not the end-to-end database")
Path(url.removeprefix("sqlite:///")).unlink(missing_ok=True)

# After the guard: importing the app opens the database named by DATABASE_URL
from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.migrations import upgrade_database  # noqa: E402
from app.models import CodeEntity, CodeFile, Repository  # noqa: E402

APP = (
    "def greet(name):\n"
    '    return f"Hello, {name}"\n'
    "\n"
    "\n"
    "class Greeter:\n"
    "    def hello(self):\n"
    '        return greet("world")\n'
)
README = "# Demo\n\nA tiny repository for the end-to-end tests.\n"

upgrade_database(engine)
with SessionLocal() as db:
    repository = Repository(
        name="e2e/demo",
        # .invalid never resolves, so the page's freshness check fails quietly and offline
        url="https://git.example.invalid/e2e/demo",
        status="completed",
        commit_sha="abc1234" + "0" * 33,
        total_files=2,
        processed_files=2,
        total_lines=10,
        language="python",
        processed_at=datetime.now(UTC),
    )
    db.add(repository)
    db.flush()
    for path, content, language, entities in [
        ("src/app.py", APP, "python", [("greet", "function", 1, 2), ("Greeter", "class", 5, 7), ("hello", "function", 6, 7)]),
        ("README.md", README, "markdown", [("Demo", "doc_section", 1, 3)]),
    ]:
        file = CodeFile(
            repository_id=repository.id,
            file_path=path,
            content=content,
            language=language,
            line_count=content.count("\n"),
        )
        db.add(file)
        db.flush()
        for name, kind, start, end in entities:
            db.add(
                CodeEntity(
                    file_id=file.id,
                    repository_id=repository.id,
                    entity_type=kind,
                    entity_name=name,
                    start_line=start,
                    end_line=end,
                    signature=content.splitlines()[start - 1],
                )
            )
    db.commit()
print("Seeded the end-to-end database")
