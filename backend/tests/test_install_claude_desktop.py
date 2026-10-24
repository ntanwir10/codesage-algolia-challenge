"""Tests for scripts/install_claude_desktop.py (runs against tmp_path configs only)."""

import importlib.util
import json
import stat
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "install_claude_desktop.py"
spec = importlib.util.spec_from_file_location("install_claude_desktop", SCRIPT)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def run(config: Path, *extra: str) -> int:
    return installer.main(
        ["--config", str(config), "--server-url", "http://x:1", "--api-key", "k-123", *extra]
    )


def test_creates_config_when_missing(tmp_path):
    cfg = tmp_path / "Claude" / "claude_desktop_config.json"
    assert run(cfg) == 0
    entry = json.loads(cfg.read_text())["mcpServers"]["codesage"]
    assert entry["command"].endswith("mcp_launcher.sh") and Path(entry["command"]).is_absolute()
    assert entry["env"] == {"MCP_SERVER_URL": "http://x:1", "CODESAGE_API_KEY": "k-123"}


def test_merges_and_preserves_other_servers_and_keys(tmp_path):
    cfg = tmp_path / "c.json"
    original = {"theme": "dark", "mcpServers": {"other": {"command": "x"}}}
    cfg.write_text(json.dumps(original))
    assert run(cfg) == 0
    data = json.loads(cfg.read_text())
    assert data["theme"] == "dark"
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert "codesage" in data["mcpServers"]


def test_writes_backup_and_mode_600(tmp_path):
    cfg = tmp_path / "c.json"
    cfg.write_text('{"a": 1}')
    assert run(cfg) == 0
    backups = list(tmp_path.glob("c.json.bak-*"))
    assert len(backups) == 1 and json.loads(backups[0].read_text()) == {"a": 1}
    assert stat.S_IMODE(cfg.stat().st_mode) == 0o600
    assert not list(tmp_path.glob("*.tmp"))


def test_refuses_invalid_json(tmp_path, capsys):
    cfg = tmp_path / "c.json"
    cfg.write_text("{not json")
    assert run(cfg) == 1
    assert cfg.read_text() == "{not json"
    assert not list(tmp_path.glob("c.json.bak-*"))
    assert "not valid JSON" in capsys.readouterr().err


def test_dry_run_masks_key_and_writes_nothing(tmp_path, capsys):
    cfg = tmp_path / "c.json"
    cfg.write_text('{"a": 1}')
    assert run(cfg, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "k-123" not in out and "********" in out
    assert json.loads(cfg.read_text()) == {"a": 1}
    assert not list(tmp_path.glob("c.json.bak-*"))


def test_env_file_parser_never_evaluates(tmp_path):
    env = tmp_path / ".env"
    env.write_text('# c\nOTHER=1\nexport CODESAGE_API_KEY="abc $(touch pwned)"\n')
    assert installer.read_env_value(env, "CODESAGE_API_KEY") == "abc $(touch pwned)"
    assert installer.read_env_value(tmp_path / "missing", "X") is None
    assert not (tmp_path / "pwned").exists()


@pytest.mark.parametrize("name", ["codesage", "cs2"])
def test_custom_name(tmp_path, name):
    cfg = tmp_path / "c.json"
    assert run(cfg, "--name", name) == 0
    assert name in json.loads(cfg.read_text())["mcpServers"]


def test_refuses_a_password_in_the_url(tmp_path, capsys):
    cfg = tmp_path / "c.json"
    assert installer.main(["--config", str(cfg), "--server-url", "https://ann:pw@h"]) == 1
    assert "--basic-auth" in capsys.readouterr().err
    assert not cfg.exists()


def test_basic_auth_stores_password_in_keychain_and_only_user_in_config(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(installer.shutil, "which", lambda name: "/usr/bin/security")
    monkeypatch.setattr(
        installer.subprocess, "run", lambda cmd: calls.append(cmd) or type("R", (), {"returncode": 0})()
    )
    cfg = tmp_path / "c.json"
    assert run(cfg, "--basic-auth", "ann") == 0
    env = json.loads(cfg.read_text())["mcpServers"]["codesage"]["env"]
    assert env["CODESAGE_BASIC_AUTH_USER"] == "ann"
    assert "pw" not in cfg.read_text() and "PASSWORD" not in cfg.read_text()
    # -w is last, so `security` prompts and the password never appears in argv
    assert calls == [["security", "add-generic-password", "-U", "-s", "codesage-mcp", "-a", "ann", "-w"]]
