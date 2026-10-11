from abc import ABC, abstractmethod
from typing import Dict, List, Any, Tuple, Optional
import asyncio
import json
import logging
import re
import httpx
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.models.interview_session import QuestionDifficulty, EvaluatorMode

logger = logging.getLogger(__name__)


class AIProviderUnavailableError(Exception):
    """Raised when an AI provider is requested but credentials or services are unconfigured."""
    pass


class AIProviderError(Exception):
    """Raised when an active AI provider encounters a runtime, network, rate-limit, or parsing failure."""
    pass


class AdaptiveDifficultyPolicy:
    """
    Explicit, deterministic difficulty progression policy:
    - Escalate difficulty if score >= 7.5 / 10
    - Maintain difficulty if 5.0 <= score < 7.5 / 10
    - De-escalate difficulty if score < 5.0 / 10
    """
    ESCALATE_THRESHOLD = 7.5
    DE_ESCALATE_THRESHOLD = 5.0

    @classmethod
    def determine_next_difficulty(
        cls, current_difficulty: QuestionDifficulty, score: float
    ) -> Tuple[QuestionDifficulty, str]:
        score = max(0.0, min(10.0, float(score)))

        if score >= cls.ESCALATE_THRESHOLD:
            if current_difficulty == QuestionDifficulty.EASY:
                new_diff = QuestionDifficulty.MEDIUM
                rationale = (
                    f"Candidate scored {score:.1f}/10 (>= {cls.ESCALATE_THRESHOLD}); "
                    "escalating from easy to medium to assess core engineering depth."
                )
            elif current_difficulty == QuestionDifficulty.MEDIUM:
                new_diff = QuestionDifficulty.HARD
                rationale = (
                    f"Candidate demonstrated high proficiency with {score:.1f}/10; "
                    "escalating from medium to hard to evaluate advanced troubleshooting and design."
                )
            else:
                new_diff = QuestionDifficulty.HARD
                rationale = (
                    f"Candidate mastered hard problem with {score:.1f}/10; "
                    "maintaining hard tier for rigorous technical depth."
                )
        elif score < cls.DE_ESCALATE_THRESHOLD:
            if current_difficulty == QuestionDifficulty.HARD:
                new_diff = QuestionDifficulty.MEDIUM
                rationale = (
                    f"Candidate struggled on hard problem (score: {score:.1f}/10 < {cls.DE_ESCALATE_THRESHOLD}); "
                    "de-escalating to medium tier to test core concepts."
                )
            elif current_difficulty == QuestionDifficulty.MEDIUM:
                new_diff = QuestionDifficulty.EASY
                rationale = (
                    f"Candidate struggled on core problem (score: {score:.1f}/10 < {cls.DE_ESCALATE_THRESHOLD}); "
                    "adjusting to foundational easy tier to verify baseline comprehension."
                )
            else:
                new_diff = QuestionDifficulty.EASY
                rationale = (
                    f"Candidate scored {score:.1f}/10; maintaining easy tier "
                    "to assess foundational concepts without excessive penalty."
                )
        else:
            new_diff = current_difficulty
            rationale = (
                f"Candidate exhibited balanced performance with {score:.1f}/10; "
                f"maintaining current {current_difficulty.value} difficulty level."
            )

        return new_diff, rationale


class BaseInterviewAIProvider(ABC):
    """Abstract interface for question generation and technical evaluation."""

    @abstractmethod
    def get_mode(self) -> EvaluatorMode:
        pass

    @abstractmethod
    async def generate_question(
        self,
        topic: str,
        instructions: str,
        difficulty: QuestionDifficulty,
        question_index: int,
        previous_questions: List[str],
    ) -> Dict[str, Any]:
        """Returns dict with: question_text, topic, difficulty."""
        pass

    @abstractmethod
    async def evaluate_answer(
        self,
        question: str,
        answer: str,
        difficulty: QuestionDifficulty,
        topic: str,
    ) -> Dict[str, Any]:
        """Returns dict with: score (0.0-10.0), feedback, strengths, improvements."""
        pass

    @abstractmethod
    async def generate_scorecard_summary(
        self,
        responses: List[Dict[str, Any]],
        interview_title: str,
    ) -> Dict[str, Any]:
        """Returns dict with: overall_score, percentage_score, performance_level, summary_feedback, strengths, areas_for_growth."""
        pass


class MockRuleEngineProvider(BaseInterviewAIProvider):
    """
    Deterministic rubric evaluation engine.
    Used for reliable unit testing, offline demonstrations, and as a fallback
    when external cloud AI providers are unconfigured.
    Explicitly tags all outputs with evaluator_mode='mock_rule_engine'.
    """

    NETWORKING_QUESTIONS = {
        QuestionDifficulty.EASY: [
            {
                "topic": "OSI Reference Model",
                "question": "Explain the difference between Layer 2 (Data Link) and Layer 3 (Network) in the OSI model, including the addressing schemes used at each layer.",
                "keywords": ["mac", "ip", "frame", "packet", "switch", "router", "hardware", "logical"],
            },
            {
                "topic": "TCP vs UDP Protocols",
                "question": "Compare TCP and UDP in terms of reliability, header overhead, connection orientation, and typical use cases in network communications.",
                "keywords": ["handshake", "connectionless", "reliable", "unreliable", "overhead", "streaming", "syn", "ack"],
            },
            {
                "topic": "IP Addressing & Subnetting",
                "question": "What is the primary function of a subnet mask, and how does a host determine whether a destination IP address is on the local or a remote network?",
                "keywords": ["network", "host", "and", "bitwise", "default gateway", "local", "broadcast"],
            },
        ],
        QuestionDifficulty.MEDIUM: [
            {
                "topic": "Address Resolution Protocol (ARP)",
                "question": "Walk through the complete ARP process when Host A wants to communicate with Host B on the same local subnet for the first time, including ARP cache handling.",
                "keywords": ["broadcast", "unicast", "arp request", "arp reply", "mac address", "cache", "table", "hardware"],
            },
            {
                "topic": "VLANs & Trunking",
                "question": "Describe why Virtual LANs (VLANs) are implemented in enterprise campus networks and explain how 802.1Q frame tagging enables inter-switch trunk links.",
                "keywords": ["broadcast domain", "802.1q", "tag", "trunk", "access", "native vlan", "segmentation", "switch"],
            },
            {
                "topic": "DHCP DORA Process",
                "question": "Detail the four steps of the DHCP DORA process (Discover, Offer, Request, Acknowledge) and explain why broadcast addressing is used initially.",
                "keywords": ["discover", "offer", "request", "acknowledge", "lease", "broadcast", "udp 67", "udp 68"],
            },
        ],
        QuestionDifficulty.HARD: [
            {
                "topic": "Dynamic Routing & OSPF",
                "question": "Analyze how Link-State routing protocols like OSPF establish adjacencies, exchange LSAs, and prevent routing loops in multi-area topologies.",
                "keywords": ["hello", "adjacency", "lsa", "lsdb", "dijkstra", "spf", "dr", "bdr", "area 0", "loop"],
            },
            {
                "topic": "Network Security & Statefulness",
                "question": "Compare packet-filtering firewalls with stateful inspection firewalls, focusing on how TCP connection state tables are maintained against spoofing attacks.",
                "keywords": ["stateful", "stateless", "connection table", "syn-ack", "fin", "rst", "sequence number", "inspection"],
            },
            {
                "topic": "BGP & Inter-AS Routing",
                "question": "Explain the role of BGP path attributes (such as AS-Path, Next-Hop, Local Preference) in determining the best path for inter-autonomous system traffic routing.",
                "keywords": ["autonomous system", "as-path", "next-hop", "local preference", "med", "peering", "transit", "loop prevention"],
            },
        ],
    }

    def get_mode(self) -> EvaluatorMode:
        return EvaluatorMode.MOCK_RULE_ENGINE

    async def generate_question(
        self,
        topic: str,
        instructions: str,
        difficulty: QuestionDifficulty,
        question_index: int,
        previous_questions: List[str],
    ) -> Dict[str, Any]:
        pool = self.NETWORKING_QUESTIONS.get(difficulty, self.NETWORKING_QUESTIONS[QuestionDifficulty.MEDIUM])
        # Find unused question or cycle cleanly
        candidate = pool[(question_index - 1) % len(pool)]
        for q in pool:
            if q["question"] not in previous_questions:
                candidate = q
                break

        return {
            "question_text": candidate["question"],
            "topic": candidate["topic"],
            "difficulty": difficulty,
        }

    async def evaluate_answer(
        self,
        question: str,
        answer: str,
        difficulty: QuestionDifficulty,
        topic: str,
    ) -> Dict[str, Any]:
        cleaned = answer.strip().lower()
        word_count = len(cleaned.split())

        # Determine target keywords from question bank
        keywords = []
        for d_pool in self.NETWORKING_QUESTIONS.values():
            for item in d_pool:
                if (
                    item["topic"].lower() in topic.lower()
                    or topic.lower() in item["topic"].lower()
                    or item["question"].lower() in question.lower()
                    or question.lower() in item["question"].lower()
                ):
                    keywords = item["keywords"]
                    break
            if keywords:
                break

        if not keywords:
            keywords = ["network", "protocol", "packet", "layer", "ip", "host", "address"]

        matched_kw = [k for k in keywords if k.lower() in cleaned]
        match_ratio = len(matched_kw) / max(1, len(keywords))

        # Heuristic Scoring (0.0 to 10.0)
        # 1. Base attempt component (2.0 points if word_count >= 5)
        base_score = 2.0 if word_count >= 5 else 0.0

        # 2. Technical accuracy / keyword match (up to 6.0 points)
        accuracy_score = match_ratio * 6.0

        # 3. Depth component (up to 2.0 points for >= 25 words)
        depth_score = min(2.0, (word_count / 25.0) * 2.0)

        raw_score = round(min(10.0, max(1.0, base_score + accuracy_score + depth_score)), 1)

        strengths = []
        improvements = []

        if matched_kw:
            strengths.append(f"Correctly referenced technical terms: {', '.join(matched_kw[:4])}.")
        if word_count >= 25:
            strengths.append("Provided a thorough, structured explanation with sufficient depth.")
        else:
            improvements.append("Elaborate further on architectural mechanisms and protocol behavior.")

        missing_kw = [k for k in keywords if k not in matched_kw]
        if missing_kw:
            improvements.append(f"Could strengthen the explanation by covering: {', '.join(missing_kw[:3])}.")

        feedback = (
            f"Evaluated on {topic} ({difficulty.value} tier). "
            f"The response addressed the question with {len(matched_kw)} key technical concepts identified. "
            f"{'Strong clarity and terminology demonstrated.' if raw_score >= 7.0 else 'Fundamentals are present, but deeper operational detail is recommended.'}"
        )

        return {
            "score": raw_score,
            "feedback": feedback,
            "strengths": strengths if strengths else ["Addressed the prompt directly."],
            "improvements": improvements if improvements else ["Continue maintaining concise precision."],
            "rationale": f"Deterministic heuristic rubric evaluation on {topic} ({difficulty.value} tier).",
        }

    async def generate_scorecard_summary(
        self,
        responses: List[Dict[str, Any]],
        interview_title: str,
    ) -> Dict[str, Any]:
        if not responses or not isinstance(responses, list):
            return {
                "overall_score": 0.0,
                "percentage_score": 0.0,
                "performance_level": "Needs Improvement",
                "summary_feedback": "No questions were completed during this session.",
                "strengths": [],
                "areas_for_growth": ["Complete the interview session to receive evaluation."],
            }

        scores = [
            float(r.get("evaluation_score", r.get("score", 0.0)))
            for r in responses if isinstance(r, dict)
        ]
        if not scores:
            overall = 0.0
        else:
            overall = round(sum(scores) / len(scores), 1)
        percentage = round((overall / 10.0) * 100.0, 1)

        if overall >= 8.5:
            perf_level = "Exceptional"
            summary = f"Outstanding performance across all evaluated topics in '{interview_title}'. Demonstrates strong mastery of networking architecture and protocols."
        elif overall >= 7.0:
            perf_level = "Proficient"
            summary = f"Solid technical competence demonstrated in '{interview_title}'. Consistent understanding of core engineering principles."
        elif overall >= 5.0:
            perf_level = "Satisfactory"
            summary = f"Meets baseline expectations for '{interview_title}', but requires further revision on protocol mechanics and edge cases."
        else:
            perf_level = "Needs Improvement"
            summary = f"Significant conceptual gaps identified in '{interview_title}'. Thorough review of foundational networking concepts is advised."

        all_strengths = []
        all_improvements = []
        for r in responses:
            all_strengths.extend(r.get("strengths", []))
            all_improvements.extend(r.get("improvements", []))

        return {
            "overall_score": overall,
            "percentage_score": percentage,
            "performance_level": perf_level,
            "summary_feedback": summary,
            "strengths": list(dict.fromkeys(all_strengths))[:4],
            "areas_for_growth": list(dict.fromkeys(all_improvements))[:4],
        }


# ==============================================================================
# Google Gemini Structured Output Schemas & Implementation
# ==============================================================================

class GeminiEvaluationSchema(BaseModel):
    score: float
    feedback: str = Field(..., min_length=5)
    strengths: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    rationale: Optional[str] = Field(default=None)

    @field_validator("score", mode="before")
    @classmethod
    def clamp_score(cls, v: Any) -> float:
        try:
            val = float(v)
        except (ValueError, TypeError):
            val = 0.0
        return round(max(0.0, min(10.0, val)), 1)


class GeminiQuestionSchema(BaseModel):
    question_text: str = Field(..., min_length=10)
    topic: str = Field(..., min_length=2)
    difficulty: QuestionDifficulty


class GeminiScorecardSchema(BaseModel):
    overall_score: float
    percentage_score: float
    performance_level: str
    summary_feedback: str
    strengths: List[str] = Field(default_factory=list)
    areas_for_growth: List[str] = Field(default_factory=list)

    @field_validator("overall_score", mode="before")
    @classmethod
    def clamp_overall(cls, v: Any) -> float:
        try:
            val = float(v)
        except (ValueError, TypeError):
            val = 0.0
        return round(max(0.0, min(10.0, val)), 1)

    @field_validator("percentage_score", mode="before")
    @classmethod
    def clamp_percentage(cls, v: Any) -> float:
        try:
            val = float(v)
        except (ValueError, TypeError):
            val = 0.0
        return round(max(0.0, min(100.0, val)), 1)


class GeminiInterviewAIProvider(BaseInterviewAIProvider):
    """
    Production-ready Google Gemini AI provider implementation using structured REST generation.
    Connects to the official Google Gemini API (v1beta) using httpx.
    Validates model responses through Pydantic schemas and strictly handles
    timeouts, quota exhaustion (429), authentication failures (401/403),
    service unavailability, and malformed JSON.
    Never exposes API keys in URLs, error messages, or logs.
    """

    def __init__(
        self,
        api_key: str,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        if not api_key or not api_key.strip():
            raise AIProviderUnavailableError("GEMINI_API_KEY must not be empty.")
        self._api_key = api_key.strip()
        raw_model = (model_name or settings.resolved_gemini_model).strip()
        if raw_model.startswith("models/"):
            raw_model = raw_model[len("models/"):]
        self.model_name = raw_model
        self.base_url = (base_url or settings.GEMINI_API_BASE_URL).rstrip("/")
        self.timeout_seconds = float(timeout_seconds or settings.AI_REQUEST_TIMEOUT_SECONDS)

    def get_mode(self) -> EvaluatorMode:
        return EvaluatorMode.GEMINI

    def _clean_json_text(self, text: str) -> str:
        """Strips markdown code fences and whitespace from model output."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        return cleaned.strip()

    async def _call_gemini_api(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes HTTP POST request to Google Gemini API with header-based authentication,
        timeout enforcement, and structured JSON parsing.
        """
        url = f"{self.base_url}/models/{self.model_name}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }
        payload: Dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": settings.AI_TEMPERATURE,
                "responseMimeType": "application/json",
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        response = None
        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException:
                if attempt < max_retries:
                    await asyncio.sleep(1.0)
                    continue
                logger.error("Gemini API request timed out after %.1fs", self.timeout_seconds)
                raise AIProviderError(f"Gemini API request timed out after {self.timeout_seconds}s.")
            except httpx.RequestError as exc:
                if attempt < max_retries:
                    await asyncio.sleep(1.0)
                    continue
                logger.error("Gemini API network request error: %s", type(exc).__name__)
                raise AIProviderError(f"Gemini network connection failed: {type(exc).__name__}")

            if response.status_code in [429, 503] and attempt < max_retries:
                logger.warning(
                    "Transient Gemini API response HTTP %d (attempt %d/%d); retrying...",
                    response.status_code,
                    attempt + 1,
                    max_retries + 1,
                )
                await asyncio.sleep(1.5)
                continue
            break

        if response.status_code in [401, 403]:
            logger.error("Gemini API returned authentication error HTTP %d", response.status_code)
            raise AIProviderError("Gemini API authentication failed. Verify configured GEMINI_API_KEY.")
        elif response.status_code == 429:
            logger.error("Gemini API returned rate-limit or quota exhaustion HTTP 429")
            raise AIProviderError("Gemini API quota or rate limit exceeded. Please retry shortly.")
        elif response.status_code in [500, 502, 503, 504]:
            logger.error("Gemini API service unavailable HTTP %d", response.status_code)
            err_detail = ""
            try:
                err_data = response.json()
                err_detail = err_data.get("error", {}).get("message", "")
            except Exception:
                pass
            if err_detail:
                err_detail = re.sub(r"AIza[0-9A-Za-z\-_]{35}", "[REDACTED]", err_detail)
                err_detail = err_detail.replace(self._api_key, "[REDACTED]")
                raise AIProviderError(
                    f"Gemini AI service is temporarily unavailable (HTTP {response.status_code}): {err_detail}"
                )
            raise AIProviderError(f"Gemini AI service is temporarily unavailable (HTTP {response.status_code}).")
        elif response.is_error:
            logger.error("Gemini API error HTTP %d", response.status_code)
            err_detail = ""
            try:
                err_data = response.json()
                err_detail = err_data.get("error", {}).get("message", "")
            except Exception:
                pass
            if err_detail:
                err_detail = re.sub(r"AIza[0-9A-Za-z\-_]{35}", "[REDACTED]", err_detail)
                err_detail = err_detail.replace(self._api_key, "[REDACTED]")
                raise AIProviderError(f"Gemini API returned HTTP {response.status_code}: {err_detail}")
            raise AIProviderError(f"Gemini API returned error HTTP {response.status_code}.")

        try:
            resp_data = response.json()
        except Exception:
            raise AIProviderError("Gemini API returned non-JSON HTTP body.")

        candidates = resp_data.get("candidates", [])
        if not candidates:
            block_reason = resp_data.get("promptFeedback", {}).get("blockReason", "empty response")
            raise AIProviderError(f"Gemini returned no candidates (reason: {block_reason}).")

        first_candidate = candidates[0]
        content_parts = first_candidate.get("content", {}).get("parts", [])
        if not content_parts or not content_parts[0].get("text"):
            raise AIProviderError("Gemini candidate contains empty content parts.")

        raw_text = content_parts[0]["text"]
        cleaned_json = self._clean_json_text(raw_text)

        try:
            parsed = json.loads(cleaned_json)
        except json.JSONDecodeError as exc:
            logger.error("Gemini response is not valid JSON: %s", exc)
            raise AIProviderError("Gemini response could not be parsed as valid JSON.")

        if not isinstance(parsed, dict):
            raise AIProviderError("Gemini response did not return a JSON object.")

        return parsed

    async def generate_question(
        self,
        topic: str,
        instructions: str,
        difficulty: QuestionDifficulty,
        question_index: int,
        previous_questions: List[str],
    ) -> Dict[str, Any]:
        system_prompt = (
            "You are an expert technical interviewer assessing undergraduate computer science engineering candidates. "
            "Generate a single, technically rigorous interview question based on the assigned topic and instructions, "
            f"specifically targeting the '{difficulty.value}' difficulty tier:\n"
            "- easy: Foundational conceptual clarity (OSI layers, standard headers, port numbers, baseline definitions).\n"
            "- medium: Operational protocol workflows (handshakes, ARP resolution, 802.1Q frame tagging, DHCP DORA, subnet calculation).\n"
            "- hard: Multi-protocol architecture, state tables, loop prevention, dynamic routing (OSPF LSAs, BGP path selection, stateful packet filtering).\n\n"
            "CRITICAL REQUIREMENTS:\n"
            "1. Do NOT repeat or closely paraphrase any previous questions provided.\n"
            "2. Output strictly JSON conforming to: "
            "{\"question_text\": string, \"topic\": string, \"difficulty\": string}.\n"
            "3. Ensure 'difficulty' matches the requested tier."
        )
        prev_q_str = "\n".join(f"- {q}" for q in previous_questions) if previous_questions else "(None)"
        user_prompt = (
            f"Interview Topic: {topic}\n"
            f"Special Instructions: {instructions or 'None'}\n"
            f"Target Difficulty: {difficulty.value}\n"
            f"Question Index: {question_index}\n"
            f"Previous Questions Asked in this Session:\n{prev_q_str}\n\n"
            "Generate the next question as strict JSON."
        )
        data = await self._call_gemini_api(prompt=user_prompt, system_instruction=system_prompt)
        try:
            validated = GeminiQuestionSchema.model_validate(data)
        except Exception as exc:
            logger.error("Gemini question schema validation failed: %s", exc)
            raise AIProviderError("Gemini response did not match the required question schema.")

        return {
            "question_text": validated.question_text,
            "topic": validated.topic,
            "difficulty": validated.difficulty,
        }

    async def evaluate_answer(
        self,
        question: str,
        answer: str,
        difficulty: QuestionDifficulty,
        topic: str,
    ) -> Dict[str, Any]:
        system_prompt = (
            "You are an expert technical interviewer assessing university engineering students in computer networking. "
            "Evaluate the candidate's answer using a rigorous multi-dimensional rubric:\n"
            "1. RELEVANCE & CORRECTNESS: Does the answer directly address the specific question asked? Are protocol mechanisms, headers, and layer interactions factually and technically correct?\n"
            "2. COMPLETENESS & DEPTH: Does the answer cover the essential steps and operational nuances expected for the difficulty tier, or is it merely superficial?\n"
            "3. CLARITY & COHERENCE (ANTI-KEYWORD STUFFING): CRITICAL: Do NOT reward answers that merely dump buzzwords or technical terms without coherent explanation of how they interact. "
            "Penalize disjointed keyword lists, hallucinated protocols, or incorrect layer associations.\n"
            "4. SCORING SCALE (0.0 to 10.0):\n"
            "   - 9.0 - 10.0: Flawless technical mastery with precise architecture and operational detail.\n"
            "   - 7.5 - 8.9: Proficient, technically sound response with minor omissions.\n"
            "   - 5.0 - 7.4: Satisfactory baseline understanding, but lacks depth or misses key mechanisms.\n"
            "   - 1.0 - 4.9: Flawed understanding, significant inaccuracies, keyword stuffing without substance, or superficial attempt.\n"
            "   - 0.0: Blank, irrelevant, or nonsense response.\n\n"
            "Output strictly JSON conforming to: "
            "{\"score\": float (0.0-10.0), \"feedback\": string, \"strengths\": [string], \"improvements\": [string], \"rationale\": string}."
        )
        user_prompt = (
            f"Topic: {topic}\n"
            f"Difficulty Tier: {difficulty.value}\n"
            f"Question Asked:\n{question}\n\n"
            f"Candidate's Submitted Answer:\n{answer}\n\n"
            "Evaluate the candidate's response and output strictly conforming JSON."
        )
        data = await self._call_gemini_api(prompt=user_prompt, system_instruction=system_prompt)
        try:
            validated = GeminiEvaluationSchema.model_validate(data)
        except Exception as exc:
            logger.error("Gemini answer evaluation schema validation failed: %s", exc)
            raise AIProviderError("Gemini response did not match the required evaluation schema.")

        return {
            "score": validated.score,
            "feedback": validated.feedback,
            "strengths": validated.strengths if validated.strengths else ["Addressed prompt directly."],
            "improvements": validated.improvements if validated.improvements else ["Continue maintaining technical precision."],
            "rationale": validated.rationale or validated.feedback,
        }

    async def generate_scorecard_summary(
        self,
        responses: List[Dict[str, Any]],
        interview_title: str,
    ) -> Dict[str, Any]:
        if not responses or not isinstance(responses, list):
            return {
                "overall_score": 0.0,
                "percentage_score": 0.0,
                "performance_level": "Needs Improvement",
                "summary_feedback": "No questions were completed during this session.",
                "strengths": [],
                "areas_for_growth": ["Complete the interview session to receive evaluation."],
            }

        valid_scores = [
            float(r.get("evaluation_score", r.get("score", 0.0)))
            for r in responses if isinstance(r, dict)
        ]
        calc_overall = round(sum(valid_scores) / max(1, len(valid_scores)), 1)
        calc_percentage = round((calc_overall / 10.0) * 100.0, 1)

        system_prompt = (
            "You are an expert technical interviewer summarizing a candidate's completed adaptive mock interview session. "
            "Review all evaluated questions, scores, and feedback to formulate a holistic evaluation summary.\n"
            "Assign performance_level strictly based on overall score:\n"
            "- >= 8.5: 'Exceptional'\n"
            "- 7.0 - 8.4: 'Proficient'\n"
            "- 5.0 - 6.9: 'Satisfactory'\n"
            "- < 5.0: 'Needs Improvement'\n\n"
            "Output strictly JSON conforming to: "
            "{\"overall_score\": float, \"percentage_score\": float, \"performance_level\": string, \"summary_feedback\": string, \"strengths\": [string], \"areas_for_growth\": [string]}."
        )
        resp_summary_lines = []
        for r in responses:
            score_val = r.get("evaluation_score", r.get("score", 0.0))
            feedback_val = r.get("evaluation_feedback", r.get("feedback", ""))
            resp_summary_lines.append(
                f"Q{r.get('question_index')}: {r.get('question_text')} "
                f"[{r.get('difficulty')} tier] - Score: {score_val}/10 - Feedback: {feedback_val}"
            )
        user_prompt = (
            f"Interview Title: {interview_title}\n"
            f"Question Evaluations:\n" + "\n".join(resp_summary_lines) + "\n\n"
            f"Calculated Overall Score: {calc_overall}/10 ({calc_percentage}%)\n\n"
            "Provide the finalized holistic performance summary as strict JSON."
        )
        data = await self._call_gemini_api(prompt=user_prompt, system_instruction=system_prompt)
        try:
            validated = GeminiScorecardSchema.model_validate(data)
        except Exception as exc:
            logger.error("Gemini scorecard summary schema validation failed: %s; using calculated fallback", exc)
            raise AIProviderError("Gemini response did not match the required scorecard schema.")

        return {
            "overall_score": validated.overall_score,
            "percentage_score": validated.percentage_score,
            "performance_level": validated.performance_level,
            "summary_feedback": validated.summary_feedback,
            "strengths": validated.strengths[:4],
            "areas_for_growth": validated.areas_for_growth[:4],
        }


def get_ai_provider() -> BaseInterviewAIProvider:
    """
    Factory resolving the active AI provider interface.
    - If provider is 'gemini' or 'google': strictly requires GEMINI_API_KEY and returns GeminiInterviewAIProvider.
      Fails closed if GEMINI_API_KEY is missing (never silently falls back to mock).
    - If provider is 'mock', 'rule_engine', or 'mock_rule_engine': explicitly returns MockRuleEngineProvider.
    - If provider is 'openai' or 'gpt': strictly requires OPENAI_API_KEY.
    - If provider is unconfigured/empty: returns MockRuleEngineProvider ONLY when ALLOW_MOCK_EVALUATOR_FALLBACK is True.
    - If an unsupported provider name is specified: raises AIProviderUnavailableError.
    """
    provider_name = (settings.AI_PROVIDER or "").strip().lower()

    if provider_name in ["gemini", "google"]:
        if not settings.GEMINI_API_KEY or not settings.GEMINI_API_KEY.strip():
            raise AIProviderUnavailableError(
                "Gemini AI provider explicitly selected (AI_PROVIDER='gemini'), "
                "but GEMINI_API_KEY is not configured or is empty. "
                "Configure a valid GEMINI_API_KEY or select AI_PROVIDER='mock'."
            )
        return GeminiInterviewAIProvider(
            api_key=settings.GEMINI_API_KEY,
            model_name=settings.resolved_gemini_model,
            base_url=settings.GEMINI_API_BASE_URL,
            timeout_seconds=settings.AI_REQUEST_TIMEOUT_SECONDS,
        )

    elif provider_name in ["mock", "rule_engine", "mock_rule_engine"]:
        return MockRuleEngineProvider()

    elif provider_name in ["openai", "gpt"]:
        if not settings.OPENAI_API_KEY or not settings.OPENAI_API_KEY.strip():
            raise AIProviderUnavailableError(
                "OpenAI provider selected but OPENAI_API_KEY is not configured in environment."
            )
        raise AIProviderUnavailableError("Real OpenAI provider requires active verified API key.")

    elif not provider_name:
        # Fallback to deterministic rule-based rubric provider when external AI is not configured
        if settings.ALLOW_MOCK_EVALUATOR_FALLBACK:
            return MockRuleEngineProvider()
        raise AIProviderUnavailableError(
            "No AI provider is configured and ALLOW_MOCK_EVALUATOR_FALLBACK is disabled."
        )

    raise AIProviderUnavailableError(
        f"Unsupported AI_PROVIDER '{settings.AI_PROVIDER}'. Supported options: 'gemini', 'mock'."
    )

