import os
import subprocess
import sys
from pathlib import Path
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
PYTHON_EXE = sys.executable

def test_settings_canonical_env_loading():
    """Verify that Settings resolves and loads backend/.env regardless of CWD."""
    from app.core.config import Settings, resolve_env_file, BACKEND_DIR as CFG_BACKEND_DIR
    
    env_path, env_exists = resolve_env_file()
    assert env_exists is True
    assert env_path == CFG_BACKEND_DIR / ".env"

    settings_inst = Settings()
    assert settings_inst.CONFIG_FILE_LOADED is True
    assert settings_inst.is_remote_or_atlas is True
    assert "Atlas" in settings_inst.target_database_type


def test_sanitized_diagnostic_hides_secrets():
    """Verify that get_sanitized_diagnostic never exposes credentials or raw connection strings."""
    from app.core.config import settings

    diag = settings.get_sanitized_diagnostic()
    assert "config_file_path" in diag
    assert "config_file_loaded" in diag
    assert "target_database_type" in diag
    assert "database_name" in diag
    assert "is_remote_or_atlas" in diag

    diag_str = str(diag)
    # Ensure sensitive credentials and connection strings are excluded
    assert "@" not in diag_str
    assert "mongodb+srv://" not in diag_str
    assert "password" not in diag_str.lower()
    assert settings.MONGODB_URI not in diag_str


def test_cli_dry_run_from_repo_root():
    """Verify running CLI --dry-run from repository root loads backend/.env and targets Atlas."""
    cmd = [
        PYTHON_EXE,
        str(BACKEND_DIR / "app" / "cli" / "import_roster_cli.py"),
        "--dry-run"
    ]
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"CLI dry-run failed with stderr:\n{result.stderr}"
    assert "Configuration Source:" in result.stdout
    assert "MongoDB Atlas (Remote SRV)" in result.stdout
    assert "Preflight Validation Status:    PASSED" in result.stdout
    assert "Zero records were written to MongoDB" in result.stdout


def test_cli_dry_run_from_backend_directory():
    """Verify running CLI --dry-run from backend directory also resolves backend/.env."""
    cmd = [
        PYTHON_EXE,
        str(BACKEND_DIR / "app" / "cli" / "import_roster_cli.py"),
        "--dry-run"
    ]
    result = subprocess.run(cmd, cwd=str(BACKEND_DIR), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"CLI dry-run failed with stderr:\n{result.stderr}"
    assert "Configuration Source:" in result.stdout
    assert "MongoDB Atlas (Remote SRV)" in result.stdout
    assert "Preflight Validation Status:    PASSED" in result.stdout


def test_cli_refuses_execute_when_target_is_localhost():
    """Fail-safe: --execute MUST refuse to run when target database resolves to localhost."""
    cmd = [
        PYTHON_EXE,
        str(BACKEND_DIR / "app" / "cli" / "import_roster_cli.py"),
        "--execute"
    ]
    env = dict(os.environ)
    env["MONGODB_URI"] = "mongodb://localhost:27017"
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert "[BLOCKED BY FAIL-SAFE] Production execution refused:" in result.stdout
    assert "Reason: Database target resolved to localhost" in result.stdout
    assert "Live database write aborted. Zero records written." in result.stdout


def test_cli_refuses_execute_when_config_is_missing():
    """Fail-safe: --execute MUST refuse to run when configuration file is missing/not loaded."""
    cmd = [
        PYTHON_EXE,
        str(BACKEND_DIR / "app" / "cli" / "import_roster_cli.py"),
        "--execute"
    ]
    env = dict(os.environ)
    env["ENV_FILE"] = str(REPO_ROOT / "nonexistent" / "missing.env")
    env.pop("MONGODB_URI", None)
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert "[BLOCKED BY FAIL-SAFE] Production execution refused:" in result.stdout
    assert "Configuration file not loaded or not found" in result.stdout
    assert "Live database write aborted. Zero records written." in result.stdout


def test_cli_refuses_rollback_when_target_is_localhost():
    """Fail-safe: --rollback-batch MUST refuse to run when target is localhost."""
    cmd = [
        PYTHON_EXE,
        str(BACKEND_DIR / "app" / "cli" / "import_roster_cli.py"),
        "--rollback-batch",
        "dummy-batch-uuid"
    ]
    env = dict(os.environ)
    env["MONGODB_URI"] = "mongodb://localhost:27017"
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert "[BLOCKED BY FAIL-SAFE] Batch rollback refused:" in result.stdout
    assert "Database target is not configured for remote MongoDB Atlas" in result.stdout
