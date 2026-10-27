"""Tests for scripts/ensure_api_key.py (tmp_path env files only)."""

import importlib.util
import stat
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ensure_api_key.py"
spec = importlib.util.spec_from_file_location("ensure_api_key", SCRIPT)
ensure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ensure)


def mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


@pytest.fixture
def envs(tmp_path):
    return tmp_path / "backend.env", tmp_path / "frontend.env"


def run(envs) -> int:
    return ensure.main([str(envs[0]), str(envs[1])])


def key_of(path: Path, name="CODESAGE_API_KEY"):
    return ensure.read_env_value(path, name)


@pytest.mark.parametrize(
    "line",
    [None, "CODESAGE_API_KEY=", "export CODESAGE_API_KEY=", "CODESAGE_API_KEY = ", 'CODESAGE_API_KEY=""'],
)
def test_generates_when_missing_or_empty(envs, line, capsys):
    b, f = envs
    b.write_text("A=1\n" + (line + "\n" if line else "") + "B=2\n")
    assert run(envs) == 0
    key = key_of(b)
    assert key and len(key) >= 32
    assert b.read_text().count("CODESAGE_API_KEY") == 1
    assert b.read_text().splitlines()[:2] == ["A=1", "B=2"] or "A=1" in b.read_text()
    assert key_of(f, "VITE_CODESAGE_API_KEY") == key
    out = capsys.readouterr().out
    assert key not in out
    assert "Generated a CodeSage API key in backend/.env" in out
    assert "Copied it to frontend/.env" in out
    assert "make install-claude" in out


@pytest.mark.parametrize(
    "line",
    [
        "CODESAGE_API_KEY=your-api-key-here",
        'CODESAGE_API_KEY="your-codesage-key-here"',
        "export CODESAGE_API_KEY=your-key-here  # from the old example",
    ],
)
def test_placeholder_is_replaced(envs, line, capsys):
    b, f = envs
    b.write_text(f"A=1\n{line}\nB=2\n")
    assert run(envs) == 0
    key = key_of(b)
    assert key and len(key) >= 32
    assert b.read_text().count("CODESAGE_API_KEY") == 1
    assert "A=1" in b.read_text() and "B=2" in b.read_text()
    assert key_of(f, "VITE_CODESAGE_API_KEY") == key
    assert "Generated a CodeSage API key in backend/.env" in capsys.readouterr().out


def test_key_that_only_mentions_placeholder_words_is_kept(envs):
    b, _ = envs
    b.write_text("CODESAGE_API_KEY=your-real-key-here-not\n")
    run(envs)
    assert key_of(b) == "your-real-key-here-not"


def test_existing_key_kept_and_rerun_is_silent(envs, capsys):
    b, f = envs
    b.write_text("CODESAGE_API_KEY=keep-me\n")
    f.write_text("VITE_CODESAGE_API_KEY=keep-me\n")
    b.chmod(0o600)
    f.chmod(0o600)
    assert run(envs) == 0
    assert run(envs) == 0
    assert key_of(b) == "keep-me"
    assert capsys.readouterr().out == ""


def test_second_run_after_generation_is_noop(envs, capsys):
    b, _ = envs
    b.write_text("A=1\n")
    run(envs)
    before = b.read_text()
    capsys.readouterr()
    assert run(envs) == 0
    assert b.read_text() == before
    assert capsys.readouterr().out == ""


def test_frontend_synced_keeps_other_lines(envs, capsys):
    b, f = envs
    b.write_text("CODESAGE_API_KEY=real\n")
    f.write_text("VITE_API_BASE_URL=http://x\nVITE_CODESAGE_API_KEY=old\n")
    assert run(envs) == 0
    assert key_of(f, "VITE_CODESAGE_API_KEY") == "real"
    assert "VITE_API_BASE_URL=http://x" in f.read_text()
    assert f.read_text().count("VITE_CODESAGE_API_KEY") == 1
    out = capsys.readouterr().out
    assert "real" not in out and "Generated" not in out and "install-claude" not in out
    assert "Copied it to frontend/.env" in out


def test_modes_fixed_even_when_nothing_changes(envs):
    b, f = envs
    b.write_text("CODESAGE_API_KEY=k\n")
    f.write_text("VITE_CODESAGE_API_KEY=k\n")
    b.chmod(0o644)
    f.chmod(0o644)
    run(envs)
    assert mode(b) == 0o600 and mode(f) == 0o600


def test_modes_after_generation(envs):
    b, f = envs
    b.write_text("A=1\n")
    run(envs)
    assert mode(b) == 0o600 and mode(f) == 0o600


def test_missing_backend_env(envs, capsys):
    assert run(envs) == 1
    assert "error: backend/.env not found; run 'make setup' first" in capsys.readouterr().err
    assert not envs[1].exists()


def test_other_backend_lines_untouched(envs):
    b, _ = envs
    other = "# note\nALGOLIA_APP_ID=abc\nexport X='y z'\n\nCODESAGE_API_KEY=\nZ=3"
    b.write_text(other + "\n")
    run(envs)
    kept = [ln for ln in b.read_text().splitlines() if not ln.startswith("CODESAGE_API_KEY")]
    assert kept == [ln for ln in other.splitlines() if not ln.startswith("CODESAGE_API_KEY")]
