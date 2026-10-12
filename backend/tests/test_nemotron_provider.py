import json
import logging
import pytest
import httpx
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import settings
from app.models.interview_session import (
    QuestionDifficulty,
    SessionStatus,
    EvaluatorMode,
    utc_now,
)
from app.models.user import UserInDB, UserRole
from app.services.ai_provider import (
    BaseInterviewAIProvider,
    GeminiInterviewAIProvider,
    NemotronInterviewAIProvider,
    FallbackInterviewAIProvider,
    MockRuleEngineProvider,
    get_ai_provider,
    AIProviderError,
    AIProviderUnavailableError,
)


def build_nemotron_mock_response(status_code: int, content_dict_or_text, usage_dict=None, headers=None):
    """Builds a mock httpx.Response simulating NVIDIA NIM OpenAI-compatible API."""
    if isinstance(content_dict_or_text, dict):
        nemotron_payload = {
            "id": "chatcmpl-test-nemotron-123",
            "object": "chat.completion",
            "created": 1728723600,
            "model": "nvidia/nemotron-3-ultra-550b-a55b",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(content_dict_or_text),
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        if usage_dict:
            nemotron_payload["usage"] = usage_dict
        raw_text = json.dumps(nemotron_payload)
    elif isinstance(content_dict_or_text, str):
        raw_text = content_dict_or_text
    else:
        raw_text = ""

    req = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions")
    return httpx.Response(status_code=status_code, text=raw_text, headers=headers or {}, request=req)


# ==============================================================================
# 1. Provider Construction & API Key Validation Tests
# ==============================================================================

def test_nemotron_provider_requires_api_key():
    """Verify Nemotron provider raises AIProviderUnavailableError if key is missing or blank."""
    with pytest.raises(AIProviderUnavailableError, match="NVIDIA_API_KEY must not be empty"):
        NemotronInterviewAIProvider(api_key="")

    with pytest.raises(AIProviderUnavailableError):
        NemotronInterviewAIProvider(api_key="   ")


def test_factory_fails_closed_when_nemotron_key_missing():
    """Verify get_ai_provider fails closed when AI_PROVIDER='nemotron' but key is missing."""
    with patch.object(settings, "AI_PROVIDER", "nemotron"):
        with patch.object(settings, "NVIDIA_API_KEY", ""):
            with patch.object(settings, "ALLOW_MOCK_EVALUATOR_FALLBACK", True):
                with pytest.raises(AIProviderUnavailableError, match="NVIDIA_API_KEY is not configured"):
                    get_ai_provider()


def test_factory_returns_nemotron_provider_when_configured():
    """Verify get_ai_provider constructs NemotronInterviewAIProvider when configured."""
    with patch.object(settings, "AI_PROVIDER", "nemotron"):
        with patch.object(settings, "NVIDIA_API_KEY", "nvapi-mock-test-key-12345"):
            with patch.object(settings, "AI_FALLBACK_PROVIDER", None):
                provider = get_ai_provider()
                assert isinstance(provider, NemotronInterviewAIProvider)
                assert provider.get_mode() == EvaluatorMode.NEMOTRON


def test_factory_supports_nvidia_and_nemotron_3_ultra_aliases():
    """Verify factory accepts 'nvidia' and 'nemotron_3_ultra' provider names."""
    with patch.object(settings, "AI_PROVIDER", "nvidia"):
        with patch.object(settings, "NVIDIA_API_KEY", "nvapi-mock-test-key"):
            with patch.object(settings, "AI_FALLBACK_PROVIDER", None):
                provider = get_ai_provider()
                assert isinstance(provider, NemotronInterviewAIProvider)

    with patch.object(settings, "AI_PROVIDER", "nemotron_3_ultra"):
        with patch.object(settings, "NVIDIA_API_KEY", "nvapi-mock-test-key"):
            with patch.object(settings, "AI_FALLBACK_PROVIDER", None):
                provider = get_ai_provider()
                assert isinstance(provider, NemotronInterviewAIProvider)


# ==============================================================================
# 2. Valid Structured Output Generation
# ==============================================================================

@pytest.mark.anyio
async def test_nemotron_generate_question_valid():
    """Verify Nemotron question generation with structured JSON."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key")
    expected_q = {
        "question_text": "Explain the architectural differences between distance-vector and link-state routing protocols.",
        "topic": "Routing Protocols",
        "difficulty": "medium",
    }
    mock_resp = build_nemotron_mock_response(200, expected_q)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await provider.generate_question(
            topic="Computer Networks",
            instructions="Focus on link-state routing",
            difficulty=QuestionDifficulty.MEDIUM,
            question_index=1,
            previous_questions=[],
        )

        assert res["question_text"] == expected_q["question_text"]
        assert res["topic"] == expected_q["topic"]
        assert res["difficulty"] == QuestionDifficulty.MEDIUM

        sent_call = mock_post.call_args
        assert sent_call.kwargs["headers"]["Authorization"] == "Bearer nvapi-test-key"
        sent_json = sent_call.kwargs["json"]
        assert sent_json["model"] == "nvidia/nemotron-3-ultra-550b-a55b"
        assert sent_json["response_format"] == {"type": "json_object"}


@pytest.mark.anyio
async def test_nemotron_evaluate_answer_valid():
    """Verify Nemotron answer evaluation with structured rubric."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key")
    expected_eval = {
        "score": 9.0,
        "feedback": "Comprehensive technical answer detailing Dijkstra's algorithm and link-state advertisement mechanisms.",
        "strengths": ["Clear LSA explanation", "Accurate topological database description"],
        "improvements": ["Elaborate on DR/BDR election edge cases"],
        "rationale": "High precision and depth for medium tier.",
    }
    mock_resp = build_nemotron_mock_response(200, expected_eval)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        eval_res = await provider.evaluate_answer(
            question="Explain OSPF link-state routing.",
            answer="OSPF uses Dijkstra SPF algorithm and exchanges LSAs to build a link-state database.",
            difficulty=QuestionDifficulty.MEDIUM,
            topic="Routing Protocols",
            expected_answer="Must mention LSAs and SPF algorithm.",
            keywords=["lsa", "dijkstra", "lsdb"],
        )

        assert eval_res["score"] == 9.0
        assert "Comprehensive technical answer" in eval_res["feedback"]
        assert len(eval_res["strengths"]) == 2
        assert len(eval_res["improvements"]) == 1
        assert eval_res["rationale"] is not None


@pytest.mark.anyio
async def test_nemotron_generate_scorecard_summary_valid():
    """Verify Nemotron scorecard summary generation."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key")
    expected_summary = {
        "overall_score": 8.5,
        "percentage_score": 85.0,
        "performance_level": "Exceptional",
        "summary_feedback": "Candidate exhibited strong technical depth across all networking challenges.",
        "strengths": ["Consistent protocol clarity", "Strong architectural rationale"],
        "areas_for_growth": ["Deepen security and stateful filtering concepts"],
    }
    mock_resp = build_nemotron_mock_response(200, expected_summary)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        responses = [
            {"question_index": 1, "question_text": "What is ARP?", "difficulty": "medium", "evaluation_score": 8.0, "evaluation_feedback": "Good"},
            {"question_index": 2, "question_text": "What is OSPF?", "difficulty": "hard", "evaluation_score": 9.0, "evaluation_feedback": "Great"},
        ]
        res = await provider.generate_scorecard_summary(responses=responses, interview_title="Networking Assessment")

        assert res["overall_score"] == 8.5
        assert res["percentage_score"] == 85.0
        assert res["performance_level"] == "Exceptional"
        assert len(res["strengths"]) == 2


@pytest.mark.anyio
async def test_nemotron_generate_scorecard_summary_empty():
    """Verify empty response list produces default scorecard summary without API call."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key")
    res = await provider.generate_scorecard_summary(responses=[], interview_title="Empty Session")
    assert res["overall_score"] == 0.0
    assert res["percentage_score"] == 0.0
    assert res["performance_level"] == "Needs Improvement"


# ==============================================================================
# 3. Code Fences and Score Clamping Protections
# ==============================================================================

@pytest.mark.anyio
async def test_nemotron_handles_markdown_code_fences():
    """Verify markdown ```json code fences returned by Nemotron are stripped cleanly."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key")
    raw_payload = {
        "id": "chatcmpl-fence",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "```json\n{\"question_text\": \"Explain 802.1Q VLAN encapsulation tags.\", \"topic\": \"VLANs\", \"difficulty\": \"medium\"}\n```",
                },
                "finish_reason": "stop",
            }
        ],
    }
    mock_resp = httpx.Response(status_code=200, text=json.dumps(raw_payload), request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await provider.generate_question(
            topic="VLANs", instructions="", difficulty=QuestionDifficulty.MEDIUM, question_index=1, previous_questions=[]
        )
        assert res["question_text"] == "Explain 802.1Q VLAN encapsulation tags."
        assert res["topic"] == "VLANs"


@pytest.mark.anyio
async def test_nemotron_clamps_score_to_ten():
    """Verify score is clamped within [0.0, 10.0]."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key")
    mock_resp = build_nemotron_mock_response(200, {
        "score": 12.0,  # Exceeds 10
        "feedback": "Exceptional answer that exceeded all metrics.",
        "strengths": ["Superb"],
        "improvements": [],
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await provider.evaluate_answer("What is IP?", "IP is ...", QuestionDifficulty.EASY, "IP")
        assert res["score"] == 10.0


# ==============================================================================
# 4. Error Handling: HTTP Errors, Auth, Rate Limits, Timeouts
# ==============================================================================

@pytest.mark.anyio
async def test_nemotron_handles_http_401_auth_error():
    """Verify HTTP 401 raises AIProviderError and masks any sensitive tokens."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-invalid-key-secret")
    mock_resp = httpx.Response(
        status_code=401,
        text=json.dumps({"error": {"message": "Invalid API Key: nvapi-invalid-key-secret"}}),
        request=httpx.Request("POST", "http://test"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="Nemotron API authentication failed"):
            await provider.generate_question(
                topic="TCP", instructions="", difficulty=QuestionDifficulty.EASY, question_index=1, previous_questions=[]
            )


@pytest.mark.anyio
async def test_nemotron_handles_http_403_forbidden_error():
    """Verify HTTP 403 raises AIProviderError."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-forbidden-key")
    mock_resp = httpx.Response(status_code=403, text="Forbidden", request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="Nemotron API authentication failed"):
            await provider.generate_question(
                topic="TCP", instructions="", difficulty=QuestionDifficulty.EASY, question_index=1, previous_questions=[]
            )


@pytest.mark.anyio
async def test_nemotron_handles_rate_limit_with_retry_after():
    """Verify HTTP 429 respects Retry-After and retries successfully."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key", max_retries=1)
    rate_limit_resp = httpx.Response(
        status_code=429,
        headers={"Retry-After": "0.01"},
        text="Rate limit exceeded",
        request=httpx.Request("POST", "http://test"),
    )
    success_resp = build_nemotron_mock_response(200, {
        "question_text": "Explain TCP flow control using sliding windows.",
        "topic": "TCP Flow Control",
        "difficulty": "medium",
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [rate_limit_resp, success_resp]
        res = await provider.generate_question(
            topic="TCP", instructions="", difficulty=QuestionDifficulty.MEDIUM, question_index=1, previous_questions=[]
        )
        assert res["question_text"] == "Explain TCP flow control using sliding windows."
        assert mock_post.call_count == 2


@pytest.mark.anyio
async def test_nemotron_exhausted_rate_limit_raises_error():
    """Verify exhausted HTTP 429 retries raise AIProviderError."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key", max_retries=1)
    rate_limit_resp = httpx.Response(
        status_code=429,
        text="Rate limit exceeded",
        request=httpx.Request("POST", "http://test"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = rate_limit_resp
        with pytest.raises(AIProviderError, match="Nemotron API quota or rate limit exceeded"):
            await provider.generate_question(
                topic="TCP", instructions="", difficulty=QuestionDifficulty.EASY, question_index=1, previous_questions=[]
            )


@pytest.mark.anyio
async def test_nemotron_retries_transient_503_and_succeeds():
    """Verify transient HTTP 503 is retried and succeeds on next attempt."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key", max_retries=2)
    unavailable_resp = httpx.Response(status_code=503, text="Service Unavailable", request=httpx.Request("POST", "http://test"))
    success_resp = build_nemotron_mock_response(200, {
        "score": 7.5,
        "feedback": "Good understanding of subnetting.",
        "strengths": ["Accurate calculation"],
        "improvements": ["Include broadcast address"],
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [unavailable_resp, success_resp]
        eval_res = await provider.evaluate_answer(
            question="Calculate subnets for /26.", answer="There are 4 subnets of 64 addresses.", difficulty=QuestionDifficulty.EASY, topic="Subnetting"
        )
        assert eval_res["score"] == 7.5
        assert mock_post.call_count == 2


@pytest.mark.anyio
async def test_nemotron_handles_timeout_and_retries():
    """Verify httpx.TimeoutException triggers retry and recovers."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key", max_retries=1)
    success_resp = build_nemotron_mock_response(200, {
        "question_text": "Describe the 4 steps of the DHCP DORA process.",
        "topic": "DHCP Protocol",
        "difficulty": "medium",
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [httpx.TimeoutException("Read timed out"), success_resp]
        res = await provider.generate_question(
            topic="DHCP", instructions="", difficulty=QuestionDifficulty.MEDIUM, question_index=1, previous_questions=[]
        )
        assert res["topic"] == "DHCP Protocol"
        assert mock_post.call_count == 2


@pytest.mark.anyio
async def test_nemotron_exhausted_timeout_raises_error():
    """Verify exhausted timeout raises AIProviderError."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key", max_retries=0)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Read timed out")
        with pytest.raises(AIProviderError, match="Nemotron API request timed out"):
            await provider.generate_question(
                topic="DHCP", instructions="", difficulty=QuestionDifficulty.MEDIUM, question_index=1, previous_questions=[]
            )


@pytest.mark.anyio
async def test_nemotron_network_error_raises_clean_exception():
    """Verify network connection failures raise clean AIProviderError without exposing secrets."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key", max_retries=0)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        with pytest.raises(AIProviderError, match="Nemotron network connection failed"):
            await provider.generate_question(
                topic="DNS", instructions="", difficulty=QuestionDifficulty.EASY, question_index=1, previous_questions=[]
            )


@pytest.mark.anyio
async def test_nemotron_deadline_exceeded():
    """Verify total deadline budget enforcement fails boundedly."""
    provider = NemotronInterviewAIProvider(
        api_key="nvapi-test-key",
        total_deadline_seconds=0.001,
        max_retries=2,
    )

    with patch("time.monotonic", side_effect=[100.0, 105.0, 110.0]):
        with pytest.raises(AIProviderError, match="deadline"):
            await provider.generate_question(
                topic="BGP", instructions="", difficulty=QuestionDifficulty.HARD, question_index=1, previous_questions=[]
            )


# ==============================================================================
# 5. Malformed Response & Schema Validation Protections
# ==============================================================================

@pytest.mark.anyio
async def test_nemotron_handles_non_json_http_body():
    """Verify non-JSON response body raises AIProviderError."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key")
    mock_resp = httpx.Response(status_code=200, text="<html>502 Bad Gateway</html>", request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="non-JSON"):
            await provider.generate_question(
                topic="OSPF", instructions="", difficulty=QuestionDifficulty.HARD, question_index=1, previous_questions=[]
            )


@pytest.mark.anyio
async def test_nemotron_handles_empty_choices():
    """Verify empty choices list raises AIProviderError."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key")
    raw_payload = {"choices": []}
    mock_resp = httpx.Response(status_code=200, text=json.dumps(raw_payload), request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="Nemotron returned no completion choices"):
            await provider.generate_question(
                topic="OSPF", instructions="", difficulty=QuestionDifficulty.HARD, question_index=1, previous_questions=[]
            )


@pytest.mark.anyio
async def test_nemotron_handles_malformed_inner_json():
    """Verify invalid JSON text inside choice message raises AIProviderError."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key")
    raw_payload = {
        "choices": [
            {"message": {"content": "{ broken json without closing braces..."}}
        ]
    }
    mock_resp = httpx.Response(status_code=200, text=json.dumps(raw_payload), request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="could not be parsed as valid JSON"):
            await provider.generate_question(
                topic="OSPF", instructions="", difficulty=QuestionDifficulty.HARD, question_index=1, previous_questions=[]
            )


@pytest.mark.anyio
async def test_nemotron_handles_schema_mismatch():
    """Verify schema mismatch (e.g. missing required question_text) raises AIProviderError."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-test-key")
    # Missing required question_text
    mock_resp = build_nemotron_mock_response(200, {"topic": "Only Topic", "difficulty": "easy"})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="schema"):
            await provider.generate_question(
                topic="OSPF", instructions="", difficulty=QuestionDifficulty.HARD, question_index=1, previous_questions=[]
            )


# ==============================================================================
# 6. Privacy & Redaction Protections
# ==============================================================================

def test_nemotron_secret_redaction():
    """Verify _redact_secrets replaces both NVIDIA nvapi keys and Google keys."""
    provider = NemotronInterviewAIProvider(api_key="nvapi-secret-key-12345678")
    sample_text = "Error calling endpoint with key nvapi-secret-key-12345678 and AIzaSyD9mockKeyForGoogle0123456789abcde"
    redacted = provider._redact_secrets(sample_text)
    assert "nvapi-secret-key-12345678" not in redacted
    assert "AIzaSyD9mockKeyForGoogle0123456789abcde" not in redacted
    assert "[REDACTED]" in redacted


# ==============================================================================
# 7. Controlled Provider Fallback Behavior Tests
# ==============================================================================

@pytest.mark.anyio
async def test_fallback_provider_primary_succeeds_secondary_never_called():
    """Verify fallback provider never invokes secondary when primary succeeds."""
    primary_mock = AsyncMock(spec=BaseInterviewAIProvider)
    primary_mock.get_mode.return_value = EvaluatorMode.NEMOTRON
    primary_mock.generate_question.return_value = {
        "question_text": "Primary question text.",
        "topic": "Networking",
        "difficulty": QuestionDifficulty.MEDIUM,
    }

    fallback_mock = AsyncMock(spec=BaseInterviewAIProvider)
    fallback_mock.get_mode.return_value = EvaluatorMode.MOCK_RULE_ENGINE

    wrapper = FallbackInterviewAIProvider(primary=primary_mock, fallback=fallback_mock)
    res = await wrapper.generate_question(
        topic="Networking", instructions="", difficulty=QuestionDifficulty.MEDIUM, question_index=1, previous_questions=[]
    )

    assert res["question_text"] == "Primary question text."
    primary_mock.generate_question.assert_awaited_once()
    fallback_mock.generate_question.assert_not_awaited()


@pytest.mark.anyio
async def test_fallback_provider_primary_fails_secondary_invoked_once():
    """Verify fallback provider invokes secondary exactly once when primary raises AIProviderError."""
    primary_mock = AsyncMock(spec=BaseInterviewAIProvider)
    primary_mock.get_mode.return_value = EvaluatorMode.NEMOTRON
    primary_mock.generate_question.side_effect = AIProviderError("Nemotron timed out")

    fallback_mock = AsyncMock(spec=BaseInterviewAIProvider)
    fallback_mock.get_mode.return_value = EvaluatorMode.GEMINI
    fallback_mock.generate_question.return_value = {
        "question_text": "Fallback Gemini question text.",
        "topic": "Networking",
        "difficulty": QuestionDifficulty.MEDIUM,
    }

    wrapper = FallbackInterviewAIProvider(primary=primary_mock, fallback=fallback_mock)
    res = await wrapper.generate_question(
        topic="Networking", instructions="", difficulty=QuestionDifficulty.MEDIUM, question_index=1, previous_questions=[]
    )

    assert res["question_text"] == "Fallback Gemini question text."
    primary_mock.generate_question.assert_awaited_once()
    fallback_mock.generate_question.assert_awaited_once()


@pytest.mark.anyio
async def test_fallback_provider_both_fail_no_loop():
    """Verify that when secondary also fails, error is raised immediately without looping back to primary."""
    primary_mock = AsyncMock(spec=BaseInterviewAIProvider)
    primary_mock.get_mode.return_value = EvaluatorMode.NEMOTRON
    primary_mock.evaluate_answer.side_effect = AIProviderError("Nemotron failure")

    fallback_mock = AsyncMock(spec=BaseInterviewAIProvider)
    fallback_mock.get_mode.return_value = EvaluatorMode.GEMINI
    fallback_mock.evaluate_answer.side_effect = AIProviderError("Gemini failure")

    wrapper = FallbackInterviewAIProvider(primary=primary_mock, fallback=fallback_mock)

    with pytest.raises(AIProviderError, match="Gemini failure"):
        await wrapper.evaluate_answer(
            question="Q?", answer="A", difficulty=QuestionDifficulty.MEDIUM, topic="Topic"
        )

    # Strictly 1 call to primary, 1 call to fallback (NO recursion, NO ping-pong loops)
    assert primary_mock.evaluate_answer.await_count == 1
    assert fallback_mock.evaluate_answer.await_count == 1


def test_factory_wires_fallback_provider_when_configured():
    """Verify get_ai_provider wraps in FallbackInterviewAIProvider when AI_FALLBACK_PROVIDER is set."""
    with patch.object(settings, "AI_PROVIDER", "nemotron"):
        with patch.object(settings, "NVIDIA_API_KEY", "nvapi-test"):
            with patch.object(settings, "AI_FALLBACK_PROVIDER", "mock"):
                provider = get_ai_provider()
                assert isinstance(provider, FallbackInterviewAIProvider)
                assert isinstance(provider.primary, NemotronInterviewAIProvider)
                assert isinstance(provider.fallback, MockRuleEngineProvider)


def test_factory_ignores_same_provider_fallback():
    """Verify configuring fallback to same provider does not create redundant wrapper."""
    with patch.object(settings, "AI_PROVIDER", "nemotron"):
        with patch.object(settings, "NVIDIA_API_KEY", "nvapi-test"):
            with patch.object(settings, "AI_FALLBACK_PROVIDER", "nemotron"):
                provider = get_ai_provider()
                assert isinstance(provider, NemotronInterviewAIProvider)
