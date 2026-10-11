from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


class SupportedLanguage(str, Enum):
    PYTHON = "python"
    JAVA = "java"
    C = "c"
    CPP = "cpp"


def normalize_language_name(lang: str) -> SupportedLanguage:
    """Normalizes input language string into a canonical SupportedLanguage enum."""
    if not lang or not isinstance(lang, str):
        raise ValueError("Language identifier is required")
    cleaned = lang.strip().lower()
    if cleaned in ("python", "python3", "py"):
        return SupportedLanguage.PYTHON
    elif cleaned in ("java", "openjdk"):
        return SupportedLanguage.JAVA
    elif cleaned in ("c", "gcc"):
        return SupportedLanguage.C
    elif cleaned in ("cpp", "c++", "cplusplus", "g++"):
        return SupportedLanguage.CPP
    raise ValueError(f"Unsupported programming language '{lang}'. Supported languages are: Java, C, C++, Python.")


class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    WRONG_ANSWER = "WRONG_ANSWER"
    COMPILATION_ERROR = "COMPILATION_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TIME_LIMIT_EXCEEDED = "TIME_LIMIT_EXCEEDED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    VALIDATION_ERROR = "VALIDATION_ERROR"


class TestCase(BaseModel):
    test_case_index: int
    input_data: str
    expected_output: str
    is_hidden: bool = False
    explanation: Optional[str] = None


class TestCaseResult(BaseModel):
    test_case_index: int
    is_hidden: bool
    status: ExecutionStatus
    passed: bool
    execution_time_ms: Optional[float] = None
    input_data: Optional[str] = None
    expected_output: Optional[str] = None
    actual_output: Optional[str] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RunCodeRequest(BaseModel):
    language: str = Field(..., min_length=1, max_length=50)
    source_code: str = Field(..., min_length=1, max_length=65536)
    custom_input: Optional[str] = Field(default=None, max_length=16384)


class RunCodeResponse(BaseModel):
    session_id: str
    language: str
    status: ExecutionStatus
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    compile_output: Optional[str] = None
    execution_time_ms: Optional[float] = None
    memory_kb: Optional[int] = None
    test_case_results: List[TestCaseResult] = Field(default_factory=list)
    total_test_cases: int = 0
    passed_test_cases: int = 0
    message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SubmitCodeRequest(BaseModel):
    language: str = Field(..., min_length=1, max_length=50)
    source_code: str = Field(..., min_length=1, max_length=65536)


class SubmitCodeResponse(BaseModel):
    session_id: str
    question_index: int
    language: str
    status: ExecutionStatus
    evaluated_score: float
    tests_passed: int
    tests_total: int
    pass_percentage: float
    feedback: str
    strengths: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    test_case_results: List[TestCaseResult] = Field(default_factory=list)
    is_session_completed: bool
    next_question: Optional[Any] = None
    scorecard_id: Optional[str] = None
    evaluator_mode: str = "sandboxed_compiler"

    model_config = ConfigDict(from_attributes=True)
