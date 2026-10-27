#!/usr/bin/env python3
"""Make sure backend/.env has a CODESAGE_API_KEY and frontend/.env carries the same one.

Generates a key only when it is missing, empty or a `your-...-here` placeholder;
any other key is never changed. Never prints the key. Standard library only.
"""

import os
import re
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_claude_desktop import read_env_value, write_atomic  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BACKEND_KEY = "CODESAGE_API_KEY"
FRONTEND_KEY = "VITE_CODESAGE_API_KEY"
# Same rule as _placeholder_is_unset in backend/app/core/config.py
PLACEHOLDER = re.compile(r"your-.*-here")


def _assign(env_file: Path, name: str, value: str, only_empty: bool) -> None:
    """Drop existing `name` lines (only empty ones if only_empty), then append name=value."""
    text = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    tail = r'\s*(?:""|\'\')?\s*(?:#.*)?' if only_empty else r".*"
    drop = re.compile(rf"^\s*(?:export\s+)?{name}\s*={tail}$")
    kept = [ln for ln in text.splitlines() if not drop.match(ln)]
    write_atomic(env_file, ("\n".join([*kept, f"{name}={value}"]) + "\n").encode())


def _chmod_600(path: Path) -> None:
    if path.exists() and path.stat().st_mode & 0o777 != 0o600:
        os.chmod(path, 0o600)


def ensure(backend_env: Path, frontend_env: Path) -> int:
    if not backend_env.is_file():
        print("error: backend/.env not found; run 'make setup' first", file=sys.stderr)
        return 1
    key = read_env_value(backend_env, BACKEND_KEY)
    placeholder = bool(key and PLACEHOLDER.fullmatch(key))
    generated = not key or placeholder
    if generated:
        key = secrets.token_urlsafe(32)
        _assign(backend_env, BACKEND_KEY, key, only_empty=not placeholder)
        print("Generated a CodeSage API key in backend/.env")
    synced = read_env_value(frontend_env, FRONTEND_KEY) == key
    if not synced:
        _assign(frontend_env, FRONTEND_KEY, key, only_empty=False)
        print("Copied it to frontend/.env (restart Vite to pick it up)")
    _chmod_600(backend_env)
    _chmod_600(frontend_env)
    if generated:
        print("Run 'make install-claude' and restart Claude Desktop so Claude uses it.")
    return 0


def main(argv: list[str] | None = None) -> int:
    paths = argv if argv else [str(REPO / "backend" / ".env"), str(REPO / "frontend" / ".env")]
    return ensure(Path(paths[0]), Path(paths[1]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
