import pytest
from fastapi.testclient import TestClient
from app.core.config import Settings, settings
from app.main import app

client = TestClient(app)

PROD_ORIGIN = "https://vfstrinterview.vercel.app"
DEV_ORIGIN_LOCAL = "http://localhost:5173"
DEV_ORIGIN_IP = "http://127.0.0.1:5173"
UNAUTHORIZED_ORIGIN = "https://unauthorized-attacker.example.com"


def test_cors_settings_includes_production_origin():
    """Verify that default Settings includes the production Vercel origin."""
    default_settings = Settings()
    assert PROD_ORIGIN in default_settings.CORS_ORIGINS
    assert DEV_ORIGIN_LOCAL in default_settings.CORS_ORIGINS
    assert DEV_ORIGIN_IP in default_settings.CORS_ORIGINS


def test_cors_settings_validator_handles_string_formats():
    """Verify that assemble_cors_origins validator correctly parses strings."""
    # Comma-separated format
    s_csv = Settings(CORS_ORIGINS="https://vfstrinterview.vercel.app, http://localhost:5173")
    assert s_csv.CORS_ORIGINS == ["https://vfstrinterview.vercel.app", "http://localhost:5173"]

    # JSON array string format
    s_json = Settings(CORS_ORIGINS='["https://vfstrinterview.vercel.app"]')
    assert s_json.CORS_ORIGINS == ["https://vfstrinterview.vercel.app"]


def test_preflight_options_for_production_origin():
    """Verify CORS preflight OPTIONS request for production Vercel origin returns 200 with allow headers."""
    resp = client.options(
        "/api/health",
        headers={
            "Origin": PROD_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == PROD_ORIGIN
    assert resp.headers.get("access-control-allow-credentials") == "true"
    allowed_headers = resp.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers


def test_preflight_options_for_post_auth_endpoint():
    """Verify CORS preflight OPTIONS for POST auth login endpoint."""
    resp = client.options(
        "/api/auth/login",
        headers={
            "Origin": PROD_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == PROD_ORIGIN
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_actual_request_from_production_origin_has_cors_headers():
    """Verify actual GET request from production origin includes Access-Control-Allow-Origin."""
    resp = client.get(
        "/api/health",
        headers={"Origin": PROD_ORIGIN},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == PROD_ORIGIN
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_unauthorized_origin_rejected_in_preflight():
    """Verify unauthorized origin does not receive Access-Control-Allow-Origin."""
    resp = client.options(
        "/api/health",
        headers={
            "Origin": UNAUTHORIZED_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    # Starlette CORSMiddleware responds with 400 on disallowed origin preflight
    assert resp.headers.get("access-control-allow-origin") != UNAUTHORIZED_ORIGIN


def test_unauthorized_origin_actual_request_omits_allow_origin():
    """Verify actual request from unauthorized origin does not return allow-origin header."""
    resp = client.get(
        "/api/health",
        headers={"Origin": UNAUTHORIZED_ORIGIN},
    )
    # The endpoint may return 200, but MUST NOT include access-control-allow-origin for unauthorized origin
    assert resp.headers.get("access-control-allow-origin") is None
