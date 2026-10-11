import pytest
from unittest.mock import MagicMock
from app.core.config import Settings, settings
from app.core.database import get_interview_database, get_auth_database, check_db_health, db_manager

# -----------------------------------------------------------------------------
# Regression Tests for Atlas Test Isolation Safeguards
# -----------------------------------------------------------------------------

def test_default_database_names_remain_unchanged():
    """Verify that default production database names remain vfstr_interview and interview_db."""
    s = Settings(ENVIRONMENT="development")
    assert s.MONGODB_DB_NAME == "vfstr_interview"
    assert s.INTERVIEW_DB_NAME == "interview_db"
    assert s.PROTECTED_PRODUCTION_DATABASES == (
        "vfstr_interview",
        "interview_db",
        "admin",
        "local",
        "config",
    )


def test_configured_interview_database_selection():
    """Verify that get_interview_database uses the configured INTERVIEW_DB_NAME."""
    orig_client = db_manager.client
    orig_interview_db = settings.INTERVIEW_DB_NAME
    try:
        mock_client = MagicMock()
        db_manager.client = mock_client

        # With default setting
        settings.INTERVIEW_DB_NAME = "interview_db"
        _ = get_interview_database()
        mock_client.__getitem__.assert_called_with("interview_db")

        # With custom test database setting
        settings.INTERVIEW_DB_NAME = "interview_db_test"
        _ = get_interview_database()
        mock_client.__getitem__.assert_called_with("interview_db_test")
    finally:
        db_manager.client = orig_client
        settings.INTERVIEW_DB_NAME = orig_interview_db


def test_test_mode_rejects_production_auth_db():
    """Fail-Safe: In test mode, Settings MUST reject the production auth database 'vfstr_interview'."""
    with pytest.raises(ValueError) as exc_info:
        Settings(
            ENVIRONMENT="test",
            MONGODB_DB_NAME="vfstr_interview",
            INTERVIEW_DB_NAME="interview_db_test",
        )
    assert "FATAL TEST ISOLATION ERROR" in str(exc_info.value)
    assert "MONGODB_DB_NAME is set to protected production target 'vfstr_interview'" in str(exc_info.value)


def test_test_mode_rejects_production_interview_db():
    """Fail-Safe: In test mode, Settings MUST reject the production interview database 'interview_db'."""
    with pytest.raises(ValueError) as exc_info:
        Settings(
            ENVIRONMENT="test",
            MONGODB_DB_NAME="vfstr_interview_test",
            INTERVIEW_DB_NAME="interview_db",
        )
    assert "FATAL TEST ISOLATION ERROR" in str(exc_info.value)
    assert "INTERVIEW_DB_NAME is set to protected production target 'interview_db'" in str(exc_info.value)


def test_test_mode_rejects_protected_system_databases():
    """Fail-Safe: In test mode, Settings MUST reject admin, local, and config databases."""
    for sys_db in ("admin", "local", "config"):
        with pytest.raises(ValueError) as exc_info:
            Settings(
                ENVIRONMENT="test",
                MONGODB_DB_NAME=sys_db,
                INTERVIEW_DB_NAME="interview_db_test",
            )
        assert "FATAL TEST ISOLATION ERROR" in str(exc_info.value)


def test_test_mode_requires_test_designated_names():
    """Fail-Safe: In test mode, both database names must explicitly include 'test'."""
    # Auth database lacks 'test'
    with pytest.raises(ValueError) as exc_info:
        Settings(
            ENVIRONMENT="test",
            MONGODB_DB_NAME="vfstr_staging",
            INTERVIEW_DB_NAME="interview_db_test",
        )
    assert "MONGODB_DB_NAME to explicitly include 'test'" in str(exc_info.value)

    # Interview database lacks 'test'
    with pytest.raises(ValueError) as exc_info:
        Settings(
            ENVIRONMENT="test",
            MONGODB_DB_NAME="vfstr_interview_test",
            INTERVIEW_DB_NAME="interview_staging",
        )
    assert "INTERVIEW_DB_NAME to explicitly include 'test'" in str(exc_info.value)


def test_test_mode_accepts_safe_test_names():
    """Safe Operation: Settings cleanly initializes when safe test names are configured."""
    safe_settings = Settings(
        ENVIRONMENT="test",
        MONGODB_DB_NAME="vfstr_interview_test",
        INTERVIEW_DB_NAME="interview_db_test",
    )
    assert safe_settings.ENVIRONMENT == "test"
    assert safe_settings.MONGODB_DB_NAME == "vfstr_interview_test"
    assert safe_settings.INTERVIEW_DB_NAME == "interview_db_test"


def test_ordinary_environment_preserves_production_defaults():
    """Ordinary Operation: In development or production, ordinary database names are accepted."""
    dev_settings = Settings(
        ENVIRONMENT="development",
        MONGODB_DB_NAME="vfstr_interview",
        INTERVIEW_DB_NAME="interview_db",
    )
    assert dev_settings.MONGODB_DB_NAME == "vfstr_interview"
    assert dev_settings.INTERVIEW_DB_NAME == "interview_db"


def test_sanitized_diagnostics_report_both_database_names():
    """Verify that diagnostics include both auth and interview database names without leaking credentials."""
    s = Settings(
        MONGODB_DB_NAME="vfstr_interview",
        INTERVIEW_DB_NAME="interview_db",
        MONGODB_URI="mongodb+srv://user:secret_password@cluster.mongodb.net",
    )
    diag = s.get_sanitized_diagnostic()
    assert diag["database_name"] == "vfstr_interview"
    assert diag["interview_database_name"] == "interview_db"
    assert "secret_password" not in str(diag)
    assert "@" not in str(diag)
