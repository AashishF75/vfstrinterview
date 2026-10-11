import pytest
from unittest.mock import AsyncMock, patch
from app.core.config import settings

@pytest.fixture(scope="session", autouse=True)
def guard_against_production_database_writes():
    """
    Global fail-safe guard for all pytest executions:
    1. If ENVIRONMENT is 'test' or 'testing', strictly asserts that database names are not protected targets.
    2. If active configuration points to protected production databases, disarms live MongoDB
       connections and index lifecycle in app.main to guarantee that pytest NEVER connects to or mutates Atlas.
    """
    protected_names = [d.lower() for d in settings.PROTECTED_PRODUCTION_DATABASES]
    is_protected_auth = settings.MONGODB_DB_NAME.lower() in protected_names
    is_protected_interview = settings.INTERVIEW_DB_NAME.lower() in protected_names

    if settings.ENVIRONMENT.lower() in ("test", "testing"):
        assert not is_protected_auth, (
            f"FATAL: Test suite running with protected production auth database: {settings.MONGODB_DB_NAME}"
        )
        assert not is_protected_interview, (
            f"FATAL: Test suite running with protected production interview database: {settings.INTERVIEW_DB_NAME}"
        )

    # When tests run in non-isolated/development config, disarm live Atlas connections and index builds
    if is_protected_auth or is_protected_interview:
        with patch("app.main.connect_to_mongo", new_callable=AsyncMock), \
             patch("app.main.ensure_indexes", new_callable=AsyncMock), \
             patch("app.main.ensure_interview_indexes", new_callable=AsyncMock), \
             patch("app.main.close_mongo_connection", new_callable=AsyncMock):
            yield
            return

    yield

