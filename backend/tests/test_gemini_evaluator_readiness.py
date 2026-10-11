import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.core.config import Settings, settings
from app.models.interview_session import QuestionDifficulty, EvaluatorMode
from app.services.ai_provider import (
    GeminiInterviewAIProvider,
    MockRuleEngineProvider,
    get_ai_provider,
    AIProviderError,
    AIProviderUnavailableError,
    AdaptiveDifficultyPolicy,
    GeminiEvaluationSchema,
)


def build_gemini_mock_response(status_code: int, content_dict_or_text):
    """Helper creating an httpx.Response mimicking Google Gemini generateContent response."""
    if isinstance(content_dict_or_text, dict):
        text_content = json.dumps(content_dict_or_text)
    elif isinstance(content_dict_or_text, str):
        text_content = content_dict_or_text
    else:
        text_content = ""

    gemini_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": text_content}],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ]
    }
    raw_text = json.dumps(gemini_payload)

    req = httpx.Request(
        "POST",
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
    )
    return httpx.Response(status_code=status_code, text=raw_text, request=req)


# ==============================================================================
# 1. Configuration & Model Resolution Mismatch Audits
# ==============================================================================

def test_gemini_model_resolution_defaults():
    """Verify that default model resolution selects gemini-1.5-flash."""
    s = Settings()
    assert s.GEMINI_DEFAULT_MODEL == "gemini-1.5-flash"
    assert s.resolved_gemini_model == "gemini-1.5-flash"


def test_gemini_model_resolution_prefers_ai_model_name():
    """Verify that AI_MODEL_NAME takes precedence over GEMINI_DEFAULT_MODEL."""
    s = Settings(AI_MODEL_NAME="gemini-2.0-flash", GEMINI_DEFAULT_MODEL="gemini-1.5-flash")
    assert s.resolved_gemini_model == "gemini-2.0-flash"


def test_gemini_model_resolution_strips_models_prefix():
    """Verify that leading 'models/' prefix is stripped cleanly to prevent 404 URL formation."""
    s = Settings(AI_MODEL_NAME="models/gemini-1.5-pro")
    assert s.resolved_gemini_model == "gemini-1.5-pro"

    # Also verified directly on GeminiInterviewAIProvider
    provider = GeminiInterviewAIProvider(api_key="test-key", model_name="models/gemini-2.0-flash")
    assert provider.model_name == "gemini-2.0-flash"


def test_sanitized_diagnostics_includes_ai_status_without_secret_leak():
    """Verify that diagnostics report AI settings while hiding API keys."""
    s = Settings(
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="AIzaSySecretKey99999",
        AI_MODEL_NAME="gemini-1.5-flash",
    )
    diag = s.get_sanitized_diagnostic()
    assert diag["ai_provider"] == "gemini"
    assert diag["gemini_model"] == "gemini-1.5-flash"
    assert diag["has_gemini_key"] is True
    assert "AIzaSy" not in str(diag)


# ==============================================================================
# 2. Explicit Provider Selection & Fail-Closed Safeguards
# ==============================================================================

def test_gemini_mode_fails_closed_when_key_is_missing():
    """Verify that selecting gemini without a key raises AIProviderUnavailableError and NEVER falls back."""
    with patch.object(settings, "AI_PROVIDER", "gemini"):
        with patch.object(settings, "GEMINI_API_KEY", ""):
            with patch.object(settings, "ALLOW_MOCK_EVALUATOR_FALLBACK", True):
                with pytest.raises(AIProviderUnavailableError) as exc_info:
                    get_ai_provider()
                assert "GEMINI_API_KEY is not configured or is empty" in str(exc_info.value)


def test_mock_mode_is_explicitly_selectable():
    """Verify that mock / rule_engine is explicitly selectable and labelled."""
    for mode_str in ("mock", "rule_engine", "mock_rule_engine"):
        with patch.object(settings, "AI_PROVIDER", mode_str):
            provider = get_ai_provider()
            assert isinstance(provider, MockRuleEngineProvider)
            assert provider.get_mode() == EvaluatorMode.MOCK_RULE_ENGINE


def test_unsupported_provider_raises_error():
    """Verify that an invalid or unsupported provider raises an actionable error."""
    with patch.object(settings, "AI_PROVIDER", "unsupported_provider"):
        with pytest.raises(AIProviderUnavailableError) as exc_info:
            get_ai_provider()
        assert "Unsupported AI_PROVIDER 'unsupported_provider'" in str(exc_info.value)


# ==============================================================================
# 3. Controlled Evaluation Quality & Adaptive Policy Validation
# ==============================================================================

TEST_QUESTION = (
    "Explain the difference between Layer 2 (Data Link) and Layer 3 (Network) "
    "in the OSI model, including the addressing schemes used at each layer."
)

@pytest.mark.anyio
async def test_quality_case_a_correct_and_complete():
    """Case A: Correct and complete answer receives high score and escalates to Hard."""
    provider = GeminiInterviewAIProvider(api_key="valid-test-key")

    mock_evaluation = {
        "score": 9.0,
        "feedback": (
            "Excellent and comprehensive answer. Precisely distinguishes frame vs packet encapsulation, "
            "Layer 2 48-bit MAC addressing handled by switches, and Layer 3 logical IP addressing handled by routers. "
            "Correctly details ARP resolution and subnet boundaries."
        ),
        "strengths": [
            "Accurate differentiation of physical MAC vs logical IP addressing",
            "Clear explanation of frame-to-packet encapsulation",
            "Correct network device associations (switch vs router)",
        ],
        "improvements": [
            "Could mention 802.1Q VLAN tagging as an advanced Layer 2 mechanism.",
        ],
        "rationale": "Demonstrated complete technical mastery with precise protocol mechanics.",
    }

    correct_answer = (
        "Layer 2 (Data Link) manages node-to-node frame delivery within a single local network segment "
        "using physical 48-bit MAC addresses, handled by switches. Layer 3 (Network) manages end-to-end "
        "packet delivery and inter-network routing across different subnets using logical 32-bit IPv4 or "
        "128-bit IPv6 addresses, handled by routers. Layer 2 frames encapsulate Layer 3 packets, and ARP "
        "resolves Layer 3 IP addresses to Layer 2 MAC addresses."
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = build_gemini_mock_response(200, mock_evaluation)
        res = await provider.evaluate_answer(
            question=TEST_QUESTION,
            answer=correct_answer,
            difficulty=QuestionDifficulty.MEDIUM,
            topic="OSI Reference Model",
        )

        # Schema conformity
        assert res["score"] == 9.0
        assert len(res["feedback"]) >= 10
        assert len(res["strengths"]) >= 1
        assert len(res["improvements"]) >= 1
        assert "rationale" in res

        # Adaptive difficulty policy verification: >= 7.5 escalates Medium to Hard
        next_diff, rationale = AdaptiveDifficultyPolicy.determine_next_difficulty(
            QuestionDifficulty.MEDIUM, res["score"]
        )
        assert next_diff == QuestionDifficulty.HARD
        assert "escalating from medium to hard" in rationale


@pytest.mark.anyio
async def test_quality_case_b_partially_correct():
    """Case B: Partially correct answer receives moderate score and maintains Medium."""
    provider = GeminiInterviewAIProvider(api_key="valid-test-key")

    mock_evaluation = {
        "score": 6.0,
        "feedback": (
            "Partially correct. Accurately states that Layer 2 uses MAC addresses and Layer 3 uses IP addresses. "
            "However, the response omits addressing structures, encapsulation mechanics, and how ARP bridges the layers."
        ),
        "strengths": [
            "Correctly identifies MAC addresses at Layer 2 and IP addresses at Layer 3.",
        ],
        "improvements": [
            "Explain frame encapsulation and packet routing mechanisms.",
            "Describe the role of ARP in resolving Layer 3 to Layer 2 addresses.",
        ],
        "rationale": "Demonstrates basic baseline knowledge, but lacks depth and operational detail.",
    }

    partial_answer = (
        "Layer 2 is data link and uses MAC addresses for switches. Layer 3 is network and uses IP addresses. "
        "Layer 3 routes data across the internet."
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = build_gemini_mock_response(200, mock_evaluation)
        res = await provider.evaluate_answer(
            question=TEST_QUESTION,
            answer=partial_answer,
            difficulty=QuestionDifficulty.MEDIUM,
            topic="OSI Reference Model",
        )

        assert res["score"] == 6.0
        assert len(res["strengths"]) == 1
        assert len(res["improvements"]) == 2

        # Adaptive difficulty policy verification: 5.0 <= score < 7.5 maintains Medium
        next_diff, rationale = AdaptiveDifficultyPolicy.determine_next_difficulty(
            QuestionDifficulty.MEDIUM, res["score"]
        )
        assert next_diff == QuestionDifficulty.MEDIUM
        assert "maintaining current medium difficulty level" in rationale


@pytest.mark.anyio
async def test_quality_case_c_incorrect_or_irrelevant():
    """Case C: Incorrect or irrelevant answer receives low score and de-escalates to Easy."""
    provider = GeminiInterviewAIProvider(api_key="valid-test-key")

    mock_evaluation = {
        "score": 1.5,
        "feedback": (
            "Technically incorrect. Conflates Layer 2 and Layer 3 with Application protocols (HTTP) "
            "and wireless standards (Bluetooth). Port numbers belong to Layer 4 (Transport), not Layer 2 or 3."
        ),
        "strengths": [
            "Attempted the response.",
        ],
        "improvements": [
            "Review the standard OSI 7-layer architecture and individual layer responsibilities.",
            "Understand that Layer 2 uses MAC addressing and Layer 3 uses IP addressing.",
            "Clarify that port numbers are Transport layer (Layer 4) constructs.",
        ],
        "rationale": "Critical factual inaccuracies and layer confusion across all dimensions.",
    }

    incorrect_answer = (
        "Layer 2 is the application layer for HTTP and websites, while Layer 3 is for Bluetooth and audio streaming. "
        "They both use port numbers to connect to databases."
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = build_gemini_mock_response(200, mock_evaluation)
        res = await provider.evaluate_answer(
            question=TEST_QUESTION,
            answer=incorrect_answer,
            difficulty=QuestionDifficulty.MEDIUM,
            topic="OSI Reference Model",
        )

        assert res["score"] == 1.5
        assert len(res["improvements"]) == 3

        # Adaptive difficulty policy verification: score < 5.0 de-escalates Medium to Easy
        next_diff, rationale = AdaptiveDifficultyPolicy.determine_next_difficulty(
            QuestionDifficulty.MEDIUM, res["score"]
        )
        assert next_diff == QuestionDifficulty.EASY
        assert "adjusting to foundational easy tier" in rationale


# ==============================================================================
# 4. Robustness Against Malformed Model Responses
# ==============================================================================

def test_schema_clamps_out_of_range_scores():
    """Verify GeminiEvaluationSchema clamps scores outside [0.0, 10.0]."""
    # Over 10.0 clamped to 10.0
    over_data = GeminiEvaluationSchema(
        score=15.5,
        feedback="Overly high score clamped",
    )
    assert over_data.score == 10.0

    # Negative clamped to 0.0
    under_data = GeminiEvaluationSchema(
        score=-3.5,
        feedback="Negative score clamped",
    )
    assert under_data.score == 0.0

    # Non-numeric converted to 0.0
    invalid_data = GeminiEvaluationSchema(
        score="invalid_score",
        feedback="Invalid string score clamped",
    )
    assert invalid_data.score == 0.0


@pytest.mark.anyio
async def test_gemini_handles_markdown_code_fences_cleanly():
    """Verify GeminiProvider strips ```json code fences."""
    provider = GeminiInterviewAIProvider(api_key="valid-test-key")
    fenced_text = '```json\n{"score": 8.0, "feedback": "Solid networking response", "strengths": ["Clear"], "improvements": []}\n```'
    
    mock_resp = build_gemini_mock_response(200, fenced_text)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await provider.evaluate_answer("Q", "A", QuestionDifficulty.MEDIUM, "Topic")
        assert res["score"] == 8.0
        assert res["feedback"] == "Solid networking response"


@pytest.mark.anyio
async def test_gemini_handles_missing_required_schema_fields():
    """Verify missing required schema fields raises AIProviderError without crashing."""
    provider = GeminiInterviewAIProvider(api_key="valid-test-key")
    # Missing required 'feedback' field
    missing_fields_text = '{"score": 7.0}'
    
    mock_resp = build_gemini_mock_response(200, missing_fields_text)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="required evaluation schema"):
            await provider.evaluate_answer("Q", "A", QuestionDifficulty.MEDIUM, "Topic")


@pytest.mark.anyio
async def test_gemini_header_based_authentication_never_exposes_key_in_url():
    """Security Assertion: Ensure Gemini API key is dispatched exclusively via header."""
    secret_key = "AIzaSySecretTestKeyNeverExpose"
    provider = GeminiInterviewAIProvider(api_key=secret_key)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = build_gemini_mock_response(
            200,
            {"score": 7.0, "feedback": "Valid answer", "strengths": [], "improvements": []},
        )
        await provider.evaluate_answer("Q", "A", QuestionDifficulty.MEDIUM, "Topic")

        call_args = mock_post.call_args
        url_called = call_args.args[0]
        headers_called = call_args.kwargs["headers"]

        assert secret_key not in url_called, "SECURITY VIOLATION: API key exposed in URL query string!"
        assert headers_called["x-goog-api-key"] == secret_key
