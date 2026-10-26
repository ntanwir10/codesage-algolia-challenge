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
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600


def test_backup_is_a_byte_for_byte_copy(tmp_path):
    cfg = tmp_path / "c.json"
    original = b'{\r\n  "a": "caf\xc3\xa9"\r\n}\r\n'  # CRLF line endings, non-ASCII
    cfg.write_bytes(original)
    assert run(cfg) == 0
    (backup,) = tmp_path.glob("c.json.bak-*")
    assert backup.read_bytes() == original
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


def test_basic_auth_does_not_copy_the_backend_key(tmp_path, monkeypatch):
    # nginx supplies the key behind the basic-auth proxy; the config must not carry it
    env_file = tmp_path / ".env"
    env_file.write_text("CODESAGE_API_KEY=backend-secret\n")
    monkeypatch.setattr(installer, "ENV_FILE", env_file)
    monkeypatch.setattr(installer.shutil, "which", lambda name: "/usr/bin/security")
    monkeypatch.setattr(installer.subprocess, "run", lambda cmd: type("R", (), {"returncode": 0})())
    cfg = tmp_path / "c.json"
    assert installer.main(["--config", str(cfg), "--server-url", "https://x", "--basic-auth", "ann"]) == 0
    assert "backend-secret" not in cfg.read_text()


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


def test_unreadable_config_is_a_clean_error(tmp_path, capsys):
    cfg = tmp_path / "c.json"
    cfg.mkdir()  # reading a directory raises OSError
    assert run(cfg) == 1
    assert f"error: cannot read {cfg}:" in capsys.readouterr().err


def test_non_utf8_config_is_a_clean_error(tmp_path, capsys):
    cfg = tmp_path / "c.json"
    cfg.write_bytes(b"\xff\xfe\x00{")
    assert run(cfg) == 1
    assert f"error: cannot read {cfg}:" in capsys.readouterr().err
    assert cfg.read_bytes() == b"\xff\xfe\x00{"


def test_unwritable_directory_fails_before_the_keychain(tmp_path, monkeypatch, capsys):
    stored = []
    monkeypatch.setattr(installer.shutil, "which", lambda name: "/usr/bin/security")
    monkeypatch.setattr(installer.subprocess, "run", lambda cmd: stored.append(cmd))
    monkeypatch.setattr(installer.os, "access", lambda path, mode: False)
    cfg = tmp_path / "c.json"
    assert run(cfg, "--basic-auth", "ann") == 1
    assert f"error: cannot write {cfg}:" in capsys.readouterr().err
    assert stored == [] and not cfg.exists()


def test_write_failure_is_a_clean_error(tmp_path, monkeypatch, capsys):
    def deny(path, data):
        raise PermissionError("denied")

    monkeypatch.setattr(installer, "write_atomic", deny)
    cfg = tmp_path / "c.json"
    assert run(cfg) == 1
    assert f"error: cannot write {cfg}: denied" in capsys.readouterr().err


def test_missing_claude_desktop_folder_warns_but_proceeds(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "Claude" / "claude_desktop_config.json"
    monkeypatch.setattr(installer, "default_config_path", lambda: cfg)
    assert installer.main(["--server-url", "http://x:1", "--api-key", "k"]) == 0
    assert "Claude Desktop doesn't seem to be installed" in capsys.readouterr().err
    assert cfg.exists()


def test_explicit_config_path_skips_the_missing_folder_warning(tmp_path, capsys):
    assert run(tmp_path / "new" / "c.json") == 0
    assert "doesn't seem to be installed" not in capsys.readouterr().err


@pytest.mark.parametrize("url", ["localhost:8001", "ftp://x", "http://", "backend"])
def test_bad_server_url_is_refused(tmp_path, capsys, url):
    cfg = tmp_path / "c.json"
    assert installer.main(["--config", str(cfg), "--server-url", url, "--api-key", "k"]) == 1
    assert "--server-url must be an http(s) URL with a host" in capsys.readouterr().err
    assert not cfg.exists()


def test_backup_names_are_unique_within_the_same_second(tmp_path):
    cfg = tmp_path / "c.json"
    cfg.write_text("{}")
    for _ in range(3):
        assert run(cfg) == 0
    assert len(list(tmp_path.glob("c.json.bak-*"))) == 3


def test_keychain_failure_says_nothing_changed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(installer.shutil, "which", lambda name: "/usr/bin/security")
    monkeypatch.setattr(installer.subprocess, "run", lambda cmd: type("R", (), {"returncode": 1})())
    cfg = tmp_path / "c.json"
    assert run(cfg, "--basic-auth", "ann") == 1
    assert "nothing was changed" in capsys.readouterr().err
    assert not cfg.exists()
