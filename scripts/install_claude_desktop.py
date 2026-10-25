#!/usr/bin/env python3
"""Register the CodeSage MCP server in Claude Desktop's config (stdlib only).

Merges ``mcpServers[<name>]`` into the existing JSON, keeping every other key,
backs the file up first, and writes atomically with mode 600.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parent.parent
LAUNCHER = REPO / "mcp_launcher.sh"
ENV_FILE = REPO / "backend" / ".env"
DEFAULT_URL = "http://127.0.0.1:8001"


def default_config_path() -> Path:
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def read_env_value(env_file: Path, key: str) -> str | None:
    """Minimal KEY=VALUE parser. Never evaluates anything."""
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    value = None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if k.startswith("export "):
            k = k[len("export ") :].strip()
        if k != key:
            continue
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        elif " #" in v:
            v = v.split(" #", 1)[0].rstrip()
        value = v
    return value


def merge_config(existing: dict, name: str, entry: dict) -> dict:
    merged = dict(existing)
    servers = merged.get("mcpServers")
    if servers is None:
        servers = {}
    if not isinstance(servers, dict):
        raise ValueError("'mcpServers' in the existing config is not an object")
    merged["mcpServers"] = {**servers, name: entry}
    return merged


def masked(config: dict, name: str) -> dict:
    out = json.loads(json.dumps(config))
    env = out.get("mcpServers", {}).get(name, {}).get("env", {})
    if env.get("CODESAGE_API_KEY"):
        env["CODESAGE_API_KEY"] = "********"
    return out


def write_atomic(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Add the CodeSage MCP server to Claude Desktop.")
    ap.add_argument(
        "--config", type=Path, default=None, help="Claude Desktop config path (default: per-OS)"
    )
    ap.add_argument(
        "--name", default="codesage", help="server name in mcpServers (default: codesage)"
    )
    ap.add_argument(
        "--server-url", default=None, help=f"backend URL (default: MCP_SERVER_URL or {DEFAULT_URL})"
    )
    ap.add_argument(
        "--api-key", default=None, help="API key (default: CODESAGE_API_KEY from backend/.env)"
    )
    ap.add_argument(
        "--basic-auth",
        metavar="USER",
        default=None,
        help="login for a basic-auth proxy; the password is stored in the macOS Keychain",
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="print the merged config (key masked); write nothing"
    )
    args = ap.parse_args(argv)

    config_path = args.config or default_config_path()
    server_url = args.server_url or os.environ.get("MCP_SERVER_URL") or DEFAULT_URL
    # Behind the basic-auth proxy nginx supplies the key, so don't copy the backend's into this config
    api_key = args.api_key or ("" if args.basic_auth else read_env_value(ENV_FILE, "CODESAGE_API_KEY")) or ""

    if urlsplit(server_url).password:
        print(
            "error: --server-url contains a password, which would be stored in plain text; "
            "use --basic-auth USER instead (the password goes to the macOS Keychain)",
            file=sys.stderr,
        )
        return 1
    if args.basic_auth and not shutil.which("security"):
        print("error: --basic-auth needs the macOS Keychain (`security`)", file=sys.stderr)
        return 1

    existing: dict = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as exc:
            print(
                f"error: {config_path} is not valid JSON ({exc}); refusing to overwrite it",
                file=sys.stderr,
            )
            return 1
        if not isinstance(existing, dict):
            print(
                f"error: {config_path} does not contain a JSON object; refusing to overwrite it",
                file=sys.stderr,
            )
            return 1

    entry = {
        "command": str(LAUNCHER),
        "env": {"MCP_SERVER_URL": server_url, "CODESAGE_API_KEY": api_key},
    }
    if args.basic_auth:
        entry["env"]["CODESAGE_BASIC_AUTH_USER"] = args.basic_auth
    try:
        merged = merge_config(existing, args.name, entry)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"# dry run: would write {config_path}")
        print(json.dumps(masked(merged, args.name), indent=2))
        return 0

    if args.basic_auth:
        print(f"Enter the password for {args.basic_auth}; it is stored in the Keychain only.")
        # -w as the last option makes `security` prompt, so the password is never in argv
        cmd = ["security", "add-generic-password", "-U", "-s", "codesage-mcp", "-a", args.basic_auth, "-w"]
        if subprocess.run(cmd).returncode != 0:
            print("error: could not store the password in the Keychain", file=sys.stderr)
            return 1
    if not api_key and not args.basic_auth:
        print(
            "warning: no API key found (--api-key or CODESAGE_API_KEY in backend/.env); writing it empty",
            file=sys.stderr,
        )
    if config_path.exists():
        backup = config_path.with_name(f"{config_path.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        backup.write_bytes(config_path.read_bytes())
        os.chmod(backup, 0o600)
        print(f"backup: {backup}")
    write_atomic(config_path, json.dumps(merged, indent=2) + "\n")
    print(f"updated {config_path}: mcpServers.{args.name} -> {LAUNCHER}")
    print("Restart Claude Desktop to pick it up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
