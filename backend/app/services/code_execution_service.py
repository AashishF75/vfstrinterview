import logging
from typing import Dict, Any, Optional, List, Tuple
import httpx

from app.core.config import settings
from app.models.code_execution import (
    SupportedLanguage,
    ExecutionStatus,
    TestCase,
    TestCaseResult,
    RunCodeResponse,
    normalize_language_name,
)
from app.services.coding_challenge_service import normalize_output

logger = logging.getLogger(__name__)

# Verified Judge0 CE standard language identifiers
JUDGE0_LANGUAGE_IDS: Dict[SupportedLanguage, int] = {
    SupportedLanguage.C: 50,       # C (GCC 9.2.0)
    SupportedLanguage.CPP: 54,     # C++ (GCC 9.2.0)
    SupportedLanguage.JAVA: 62,    # Java (OpenJDK 13.0.1)
    SupportedLanguage.PYTHON: 71,  # Python (3.8.1)
}


class ExecutionServiceUnavailableError(Exception):
    """Raised when the sandboxed code execution provider is unavailable or unconfigured."""
    pass


class CodeExecutionService:
    """
    Sandboxed Code Execution Service.
    Integrates with Judge0 REST API to securely compile and execute candidate code
    in isolated container sandboxes. Enforces strict resource and size bounds.
    Candidate code is NEVER executed inside the application process.
    """

    @classmethod
    def get_language_id(cls, language: SupportedLanguage) -> int:
        """Retrieves the verified Judge0 language ID for a supported language."""
        lang_id = JUDGE0_LANGUAGE_IDS.get(language)
        if lang_id is None:
            raise ValueError(f"No execution engine mapping found for language: {language}")
        return lang_id

    @classmethod
    def is_provider_configured(cls) -> bool:
        """Checks if the sandbox execution endpoint is configured with a valid remote URL."""
        url = (settings.JUDGE0_API_URL or "").strip()
        if not url:
            return False
        import os
        is_prod = (
            (settings.ENVIRONMENT or "").lower() in ("production", "prod")
            or bool(os.getenv("RENDER"))
        )
        if is_prod and ("localhost" in url.lower() or "127.0.0.1" in url or "0.0.0.0" in url):
            return False
        return True

    @classmethod
    def _build_request_headers(cls) -> Dict[str, str]:
        """Constructs secure headers for Judge0 API calls without logging secrets."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if settings.JUDGE0_API_KEY:
            if settings.JUDGE0_API_HOST:
                # RapidAPI Judge0 CE deployment
                headers["X-RapidAPI-Key"] = settings.JUDGE0_API_KEY.strip()
                headers["X-RapidAPI-Host"] = settings.JUDGE0_API_HOST.strip()
            else:
                # Direct API key / Token
                headers["Authorization"] = f"Bearer {settings.JUDGE0_API_KEY.strip()}"

        if settings.JUDGE0_AUTH_TOKEN:
            headers["X-Auth-Token"] = settings.JUDGE0_AUTH_TOKEN.strip()

        return headers

    @classmethod
    def _sanitize_output(cls, output: Optional[str], max_len: int = 32768) -> Optional[str]:
        """Truncates excessively large stdout/stderr to protect against memory exhaustion."""
        if output is None:
            return None
        if len(output) > max_len:
            return output[:max_len] + f"\n... [Output truncated after {max_len} characters]"
        return output

    @classmethod
    async def execute_raw(
        cls,
        language: SupportedLanguage,
        source_code: str,
        stdin: Optional[str] = None,
        cpu_time_limit: Optional[float] = None,
        wall_time_limit: Optional[float] = None,
        memory_limit_kb: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Sends code to the sandboxed execution provider and awaits synchronous completion.
        Returns normalized raw execution metrics and outputs.
        """
        if not cls.is_provider_configured():
            import os
            is_prod = (
                (settings.ENVIRONMENT or "").lower() in ("production", "prod")
                or bool(os.getenv("RENDER"))
            )
            raw_url = (settings.JUDGE0_API_URL or "").strip().lower()
            if is_prod and ("localhost" in raw_url or "127.0.0.1" in raw_url or "0.0.0.0" in raw_url):
                raise ExecutionServiceUnavailableError(
                    "Production configuration error: 'localhost' or '127.0.0.1' cannot be used in a deployed production environment. "
                    "Configure a remotely reachable Judge0 URL in Render environment variables (e.g. JUDGE0_API_URL='https://ce.judge0.com')."
                )
            raise ExecutionServiceUnavailableError(
                "Code execution service is currently unavailable: JUDGE0_API_URL is not configured."
            )

        # Enforce source and input size constraints
        if len(source_code) > settings.CODE_EXECUTION_MAX_SOURCE_LENGTH:
            return {
                "status": ExecutionStatus.VALIDATION_ERROR,
                "stdout": None,
                "stderr": f"Source code length exceeds limit of {settings.CODE_EXECUTION_MAX_SOURCE_LENGTH} bytes.",
                "compile_output": None,
                "execution_time_ms": 0.0,
                "memory_kb": 0,
            }

        if stdin and len(stdin) > settings.CODE_EXECUTION_MAX_INPUT_LENGTH:
            return {
                "status": ExecutionStatus.VALIDATION_ERROR,
                "stdout": None,
                "stderr": f"Input size exceeds limit of {settings.CODE_EXECUTION_MAX_INPUT_LENGTH} bytes.",
                "compile_output": None,
                "execution_time_ms": 0.0,
                "memory_kb": 0,
            }

        lang_id = cls.get_language_id(language)
        base_url = settings.JUDGE0_API_URL.strip().rstrip("/")
        if base_url.endswith("/submissions"):
            base_url = base_url[:-len("/submissions")].rstrip("/")
        endpoint = f"{base_url}/submissions?base64_encoded=false&wait=true"

        payload = {
            "source_code": source_code,
            "language_id": lang_id,
            "stdin": stdin or "",
            "cpu_time_limit": cpu_time_limit or settings.CODE_EXECUTION_CPU_TIME_LIMIT,
            "wall_time_limit": wall_time_limit or settings.CODE_EXECUTION_WALL_TIME_LIMIT,
            "memory_limit": memory_limit_kb or settings.CODE_EXECUTION_MEMORY_LIMIT_KB,
        }

        headers = cls._build_request_headers()
        timeout = settings.CODE_EXECUTION_TIMEOUT_SECONDS

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(endpoint, json=payload, headers=headers)
        except httpx.TimeoutException:
            logger.warning("Code execution request timed out after %s seconds", timeout)
            return {
                "status": ExecutionStatus.TIME_LIMIT_EXCEEDED,
                "stdout": None,
                "stderr": f"Execution request exceeded sandbox timeout ({timeout}s).",
                "compile_output": None,
                "execution_time_ms": timeout * 1000.0,
                "memory_kb": 0,
            }
        except httpx.RequestError as exc:
            logger.error("Network error communicating with code execution sandbox: %s", exc)
            raise ExecutionServiceUnavailableError(
                f"Failed to communicate with sandbox execution provider: {exc.__class__.__name__}"
            )

        if response.status_code in (401, 403):
            logger.error("Authentication rejected by execution provider (%s)", response.status_code)
            raise ExecutionServiceUnavailableError("Execution provider authentication failed. Check API credentials.")
        elif response.status_code == 429:
            logger.warning("Execution provider quota limit exceeded (429)")
            raise ExecutionServiceUnavailableError("Execution provider rate limit or quota exceeded. Please try again later.")
        elif response.status_code >= 500:
            logger.error("Execution provider internal error: %s", response.text[:200])
            raise ExecutionServiceUnavailableError("Execution provider reported an internal error.")
        elif response.status_code not in (200, 201):
            logger.error("Unexpected execution provider status %s: %s", response.status_code, response.text[:200])
            raise ExecutionServiceUnavailableError(f"Execution provider error (HTTP {response.status_code})")

        data = response.json()
        return cls._normalize_judge0_response(data)

    @classmethod
    def _normalize_judge0_response(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Translates Judge0 submission data into normalized application metrics."""
        status_info = data.get("status") or {}
        status_id = status_info.get("id", 0)

        # Map Judge0 status IDs:
        # 3 = Accepted
        # 4 = Wrong Answer
        # 5 = Time Limit Exceeded
        # 6 = Compilation Error
        # 7..12 = Runtime Errors (SIGSEGV, SIGXFSZ, SIGFPE, SIGABRT, NZEC, other)
        # 13..14 = Internal/Format Errors
        if status_id == 3:
            exec_status = ExecutionStatus.SUCCESS
        elif status_id == 4:
            exec_status = ExecutionStatus.WRONG_ANSWER
        elif status_id == 5:
            exec_status = ExecutionStatus.TIME_LIMIT_EXCEEDED
        elif status_id == 6:
            exec_status = ExecutionStatus.COMPILATION_ERROR
        elif 7 <= status_id <= 12:
            exec_status = ExecutionStatus.RUNTIME_ERROR
        else:
            exec_status = ExecutionStatus.RUNTIME_ERROR

        stdout = cls._sanitize_output(data.get("stdout"))
        stderr = cls._sanitize_output(data.get("stderr"))
        compile_output = cls._sanitize_output(data.get("compile_output"))

        # If runtime error message exists
        message = data.get("message")
        if message and not stderr:
            stderr = cls._sanitize_output(message)

        # Parse execution time
        raw_time = data.get("time")
        try:
            exec_time_ms = round(float(raw_time) * 1000.0, 2) if raw_time is not None else None
        except (ValueError, TypeError):
            exec_time_ms = None

        # Parse memory
        raw_mem = data.get("memory")
        try:
            memory_kb = int(raw_mem) if raw_mem is not None else None
        except (ValueError, TypeError):
            memory_kb = None

        return {
            "status": exec_status,
            "stdout": stdout,
            "stderr": stderr,
            "compile_output": compile_output,
            "execution_time_ms": exec_time_ms,
            "memory_kb": memory_kb,
        }

    @classmethod
    async def run_single_or_custom(
        cls,
        session_id: str,
        language_str: str,
        source_code: str,
        custom_input: Optional[str] = None,
        sample_test_cases: Optional[List[TestCase]] = None,
    ) -> RunCodeResponse:
        """
        Executes code for interactive 'Run Code'.
        If custom_input is provided, runs against custom input.
        Otherwise, runs against permitted sample (visible) test cases.
        """
        lang = normalize_language_name(language_str)

        if custom_input is not None:
            # Custom input run
            raw = await cls.execute_raw(
                language=lang,
                source_code=source_code,
                stdin=custom_input,
            )
            return RunCodeResponse(
                session_id=session_id,
                language=lang.value,
                status=raw["status"],
                stdout=raw["stdout"],
                stderr=raw["stderr"],
                compile_output=raw["compile_output"],
                execution_time_ms=raw["execution_time_ms"],
                memory_kb=raw["memory_kb"],
                test_case_results=[],
                total_test_cases=0,
                passed_test_cases=0,
                message="Executed with custom input.",
            )

        # Run against sample test cases
        samples = sample_test_cases or []
        if not samples and custom_input is None:
            raw = await cls.execute_raw(
                language=lang,
                source_code=source_code,
                stdin="",
            )
            return RunCodeResponse(
                session_id=session_id,
                language=lang.value,
                status=raw["status"],
                stdout=raw["stdout"],
                stderr=raw["stderr"],
                compile_output=raw["compile_output"],
                execution_time_ms=raw["execution_time_ms"],
                memory_kb=raw["memory_kb"],
                test_case_results=[],
                total_test_cases=0,
                passed_test_cases=0,
                message="Execution completed.",
            )
        test_results: List[TestCaseResult] = []
        passed_count = 0
        overall_status = ExecutionStatus.SUCCESS

        for case in samples:
            raw = await cls.execute_raw(
                language=lang,
                source_code=source_code,
                stdin=case.input_data,
            )

            # Compilation error aborts entire test suite immediately
            if raw["status"] == ExecutionStatus.COMPILATION_ERROR:
                test_results.append(TestCaseResult(
                    test_case_index=case.test_case_index,
                    is_hidden=False,
                    status=ExecutionStatus.COMPILATION_ERROR,
                    passed=False,
                    execution_time_ms=raw["execution_time_ms"],
                    input_data=case.input_data,
                    expected_output=case.expected_output,
                    actual_output=None,
                    error_message=raw["compile_output"] or raw["stderr"] or "Compilation failed.",
                ))
                overall_status = ExecutionStatus.COMPILATION_ERROR
                break

            # Check runtime or timeout
            if raw["status"] in (ExecutionStatus.RUNTIME_ERROR, ExecutionStatus.TIME_LIMIT_EXCEEDED):
                test_results.append(TestCaseResult(
                    test_case_index=case.test_case_index,
                    is_hidden=False,
                    status=raw["status"],
                    passed=False,
                    execution_time_ms=raw["execution_time_ms"],
                    input_data=case.input_data,
                    expected_output=case.expected_output,
                    actual_output=raw["stdout"],
                    error_message=raw["stderr"] or f"Program terminated with {raw['status'].value}.",
                ))
                if overall_status == ExecutionStatus.SUCCESS:
                    overall_status = raw["status"]
                continue

            # Compare normalized outputs
            normalized_actual = normalize_output(raw["stdout"])
            normalized_expected = normalize_output(case.expected_output)
            is_match = (normalized_actual == normalized_expected)

            if is_match:
                passed_count += 1
                case_status = ExecutionStatus.SUCCESS
            else:
                case_status = ExecutionStatus.WRONG_ANSWER
                if overall_status == ExecutionStatus.SUCCESS:
                    overall_status = ExecutionStatus.WRONG_ANSWER

            test_results.append(TestCaseResult(
                test_case_index=case.test_case_index,
                is_hidden=False,
                status=case_status,
                passed=is_match,
                execution_time_ms=raw["execution_time_ms"],
                input_data=case.input_data,
                expected_output=case.expected_output,
                actual_output=raw["stdout"],
                error_message=raw["stderr"] if not is_match else None,
            ))

        first_compile = next((r for r in test_results if r.status == ExecutionStatus.COMPILATION_ERROR), None)
        compile_out = first_compile.error_message if first_compile else None

        return RunCodeResponse(
            session_id=session_id,
            language=lang.value,
            status=overall_status,
            stdout=test_results[0].actual_output if test_results else None,
            stderr=test_results[0].error_message if (test_results and not test_results[0].passed) else None,
            compile_output=compile_out,
            execution_time_ms=test_results[0].execution_time_ms if test_results else None,
            memory_kb=None,
            test_case_results=test_results,
            total_test_cases=len(samples),
            passed_test_cases=passed_count,
            message=f"{passed_count} / {len(samples)} sample test cases passed." if samples else "Ready.",
        )

    @classmethod
    async def evaluate_full_test_suite(
        cls,
        language: SupportedLanguage,
        source_code: str,
        test_cases: List[TestCase],
    ) -> Tuple[ExecutionStatus, int, int, List[TestCaseResult], Optional[str]]:
        """
        Executes candidate code against the full evaluation test suite (sample + hidden).
        Hides inputs and expected outputs for all hidden test cases.
        Returns: (overall_status, passed_count, total_count, masked_results, compilation_error)
        """
        results: List[TestCaseResult] = []
        passed_count = 0
        overall_status = ExecutionStatus.SUCCESS
        compile_error: Optional[str] = None

        for case in test_cases:
            raw = await cls.execute_raw(
                language=language,
                source_code=source_code,
                stdin=case.input_data,
            )

            # Abort full suite immediately on compilation failure
            if raw["status"] == ExecutionStatus.COMPILATION_ERROR:
                compile_error = raw["compile_output"] or raw["stderr"] or "Compilation error occurred."
                overall_status = ExecutionStatus.COMPILATION_ERROR
                results.append(TestCaseResult(
                    test_case_index=case.test_case_index,
                    is_hidden=case.is_hidden,
                    status=ExecutionStatus.COMPILATION_ERROR,
                    passed=False,
                    execution_time_ms=raw["execution_time_ms"],
                    input_data=None if case.is_hidden else case.input_data,
                    expected_output=None if case.is_hidden else case.expected_output,
                    actual_output=None,
                    error_message="Compilation error." if case.is_hidden else compile_error,
                ))
                break

            if raw["status"] in (ExecutionStatus.RUNTIME_ERROR, ExecutionStatus.TIME_LIMIT_EXCEEDED):
                if overall_status == ExecutionStatus.SUCCESS:
                    overall_status = raw["status"]
                results.append(TestCaseResult(
                    test_case_index=case.test_case_index,
                    is_hidden=case.is_hidden,
                    status=raw["status"],
                    passed=False,
                    execution_time_ms=raw["execution_time_ms"],
                    input_data=None if case.is_hidden else case.input_data,
                    expected_output=None if case.is_hidden else case.expected_output,
                    actual_output=None if case.is_hidden else raw["stdout"],
                    error_message=f"{raw['status'].value} occurred." if case.is_hidden else (raw["stderr"] or raw["status"].value),
                ))
                continue

            # Validate output
            normalized_actual = normalize_output(raw["stdout"])
            normalized_expected = normalize_output(case.expected_output)
            is_match = (normalized_actual == normalized_expected)

            if is_match:
                passed_count += 1
                case_status = ExecutionStatus.SUCCESS
            else:
                case_status = ExecutionStatus.WRONG_ANSWER
                if overall_status == ExecutionStatus.SUCCESS:
                    overall_status = ExecutionStatus.WRONG_ANSWER

            results.append(TestCaseResult(
                test_case_index=case.test_case_index,
                is_hidden=case.is_hidden,
                status=case_status,
                passed=is_match,
                execution_time_ms=raw["execution_time_ms"],
                input_data=None if case.is_hidden else case.input_data,
                expected_output=None if case.is_hidden else case.expected_output,
                actual_output=None if case.is_hidden else raw["stdout"],
                error_message=None if is_match else ("Output mismatch" if case.is_hidden else raw["stderr"]),
            ))

        return overall_status, passed_count, len(test_cases), results, compile_error
