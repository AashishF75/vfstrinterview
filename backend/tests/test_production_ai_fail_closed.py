import pytest
from unittest.mock import patch
from fastapi import HTTPException

from app.core.config import Settings, settings
from app.services.ai_provider import (
    get_ai_provider,
    AIProviderUnavailableError,
    GeminiInterviewAIProvider,
    MockRuleEngineProvider,
    EvaluatorMode,
)


def test_production_environment_defaults_mock_fallback_to_false():
    """Verify that in production or prod, ALLOW_MOCK_EVALUATOR_FALLBACK defaults to False."""
    prod_settings = Settings(ENVIRONMENT="production")
    assert prod_settings.ALLOW_MOCK_EVALUATOR_FALLBACK is False

    prod_short_settings = Settings(ENVIRONMENT="prod")
    assert prod_short_settings.ALLOW_MOCK_EVALUATOR_FALLBACK is False


def test_development_and_test_environments_default_mock_fallback_to_true():
    """Verify that development and test environments preserve fallback=True by default."""
    dev_settings = Settings(ENVIRONMENT="development")
    assert dev_settings.ALLOW_MOCK_EVALUATOR_FALLBACK is True

    test_settings = Settings(
        ENVIRONMENT="test",
        MONGODB_DB_NAME="vfstr_interview_test",
        INTERVIEW_DB_NAME="interview_db_test",
    )
    assert test_settings.ALLOW_MOCK_EVALUATOR_FALLBACK is True


def test_explicit_override_is_preserved_when_configured():
    """Verify that explicit configuration of ALLOW_MOCK_EVALUATOR_FALLBACK is respected."""
    custom_prod = Settings(
        ENVIRONMENT="production",
        ALLOW_MOCK_EVALUATOR_FALLBACK=False,
    )
    assert custom_prod.ALLOW_MOCK_EVALUATOR_FALLBACK is False

    custom_dev = Settings(
        ENVIRONMENT="development",
        ALLOW_MOCK_EVALUATOR_FALLBACK=False,
    )
    assert custom_dev.ALLOW_MOCK_EVALUATOR_FALLBACK is False


def test_production_unconfigured_ai_provider_fails_closed():
    """
    Verify that in production, when AI_PROVIDER is unset or empty,
    get_ai_provider() fails closed with AIProviderUnavailableError
    instead of silently returning MockRuleEngineProvider.
    """
    with patch.object(settings, "ENVIRONMENT", "production"):
        with patch.object(settings, "ALLOW_MOCK_EVALUATOR_FALLBACK", False):
            with patch.object(settings, "AI_PROVIDER", None):
                with pytest.raises(AIProviderUnavailableError) as exc_info:
                    get_ai_provider()
                assert "No AI provider is configured and ALLOW_MOCK_EVALUATOR_FALLBACK is disabled" in str(exc_info.value)


def test_production_empty_ai_provider_fails_closed():
    """Verify that in production, an empty string AI_PROVIDER fails closed."""
    with patch.object(settings, "ENVIRONMENT", "production"):
        with patch.object(settings, "ALLOW_MOCK_EVALUATOR_FALLBACK", False):
            with patch.object(settings, "AI_PROVIDER", "   "):
                with pytest.raises(AIProviderUnavailableError) as exc_info:
                    get_ai_provider()
                assert "No AI provider is configured and ALLOW_MOCK_EVALUATOR_FALLBACK is disabled" in str(exc_info.value)


def test_production_invalid_ai_provider_fails_closed():
    """Verify that in production, an invalid AI_PROVIDER fails closed."""
    with patch.object(settings, "ENVIRONMENT", "production"):
        with patch.object(settings, "ALLOW_MOCK_EVALUATOR_FALLBACK", False):
            with patch.object(settings, "AI_PROVIDER", "nonexistent_ai_model"):
                with pytest.raises(AIProviderUnavailableError) as exc_info:
                    get_ai_provider()
                assert "Unsupported AI_PROVIDER 'nonexistent_ai_model'" in str(exc_info.value)


def test_production_gemini_missing_api_key_fails_closed():
    """
    Verify that when AI_PROVIDER='gemini' in production, a missing or blank API key
    fails closed with AIProviderUnavailableError and NEVER falls back to mock.
    """
    with patch.object(settings, "ENVIRONMENT", "production"):
        with patch.object(settings, "ALLOW_MOCK_EVALUATOR_FALLBACK", False):
            with patch.object(settings, "AI_PROVIDER", "gemini"):
                with patch.object(settings, "GEMINI_API_KEY", ""):
                    with pytest.raises(AIProviderUnavailableError) as exc_info:
                        get_ai_provider()
                    assert "GEMINI_API_KEY is not configured or is empty" in str(exc_info.value)


def test_production_valid_gemini_constructs_provider():
    """Verify that with valid key, GeminiInterviewAIProvider is constructed."""
    with patch.object(settings, "ENVIRONMENT", "production"):
        with patch.object(settings, "AI_PROVIDER", "gemini"):
            with patch.object(settings, "GEMINI_API_KEY", "prod-gemini-key-xyz"):
                provider = get_ai_provider()
                assert isinstance(provider, GeminiInterviewAIProvider)
                assert provider.get_mode() == EvaluatorMode.GEMINI
