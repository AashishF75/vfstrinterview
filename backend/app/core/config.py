from pathlib import Path
from typing import List, Union, Optional, Tuple, Dict, Any
from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json
import os

# Base directory for backend (c:\VfstrInterview\backend)
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
CANONICAL_ENV_FILE = BACKEND_DIR / ".env"


def resolve_env_file() -> Tuple[Path, bool]:
    """
    Resolves the active .env configuration file:
    1. If ENV_FILE environment variable is explicitly set, use that path.
    2. Canonical path at backend/.env (standard project structure).
    3. Fallback to .env in current working directory.
    Returns (resolved_path, file_exists).
    """
    if os.getenv("ENV_FILE"):
        custom = Path(os.environ["ENV_FILE"]).resolve()
        return custom, custom.is_file()
    if CANONICAL_ENV_FILE.is_file():
        return CANONICAL_ENV_FILE, True
    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        return cwd_env, True
    return CANONICAL_ENV_FILE, False


_active_env_file, _active_env_exists = resolve_env_file()


class Settings(BaseSettings):
    PROJECT_NAME: str = "Adaptive Interview Intelligence - VFSTR"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ENVIRONMENT: str = "development"
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "https://vfstrinterview.vercel.app",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    # Partner Institution Access Policy Configuration
    ALLOWED_EXTERNAL_INSTITUTIONS: List[str] = [
        "Vignan's Institute of Information Technology (VIIT, Visakhapatnam)",
        "Vignan's Lara Institute of Technology & Science (VLITS, Vadlamudi)",
        "Vignan's Institute of Technology and Aeronautical Engineering (VITAE, Hyderabad)",
        "Vignan Institute of Technology and Science (VITS, Deshmukhi)",
        "Vignan's Nirula Institute of Technology & Science for Women (VNITSW, Guntur)",
    ]

    @field_validator("ALLOWED_EXTERNAL_INSTITUTIONS", mode="before")
    @classmethod
    def assemble_allowed_institutions(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    def is_institution_access_permitted(self, college_name: str) -> bool:
        """
        Validates whether a college is permitted under the platform's partner access policy.
        Matches case-insensitively and against institution abbreviations.
        Fails closed: returns False for unknown institutions.
        """
        if not college_name or not college_name.strip():
            return False
        cleaned = college_name.strip().lower()
        for allowed in self.ALLOWED_EXTERNAL_INSTITUTIONS:
            if cleaned == allowed.lower():
                return True
            allowed_main = allowed.split("(")[0].strip().lower()
            if cleaned == allowed_main:
                return True
        return False

    # MongoDB Atlas configuration
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "vfstr_interview"
    INTERVIEW_DB_NAME: str = "interview_db"

    # Protected production databases that must NEVER be used in test mode
    PROTECTED_PRODUCTION_DATABASES: Tuple[str, ...] = (
        "vfstr_interview",
        "interview_db",
        "admin",
        "local",
        "config",
    )

    # JWT Authentication Configuration
    JWT_SECRET_KEY: str = "vfstr_dev_secret_key_8e29a1b4c3d5f670e8a9b2c3d4e5f6a7"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_ISSUER: str = "vfstr-interview"
    JWT_AUDIENCE: str = "vfstr-interview-client"

    # Rate Limiting for Login Protection
    RATE_LIMIT_LOGIN_MAX_ATTEMPTS: int = 5
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = 300  # 5 minutes

    # Administrator Provisioning / Bootstrap
    BOOTSTRAP_ADMIN_EMAIL: Optional[str] = "admin@vfstr.ac.in"
    BOOTSTRAP_ADMIN_PASSWORD: Optional[str] = None
    BOOTSTRAP_SECRET_KEY: Optional[str] = None
    ENABLE_BOOTSTRAP_ENDPOINT: bool = True
    ALLOW_BOOTSTRAP_IN_PRODUCTION: bool = False

    # Email / SMTP Service Settings (Phase 4)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    SMTP_TIMEOUT_SECONDS: float = 5.0
    SMTP_FROM_EMAIL: str = "noreply@vfstr.ac.in"
    SMTP_FROM_NAME: str = "VFSTR Adaptive Interview Platform"
    EMAIL_DISPATCH_ENABLED: bool = False
    REGISTRATION_OTP_EXPIRE_MINUTES: int = 10
    REGISTRATION_OTP_MAX_ATTEMPTS: int = 3
    REGISTRATION_RESEND_COOLDOWN_SECONDS: int = 60

    # Demo Mode Configuration
    DEMO_MODE: bool = False

    # Adaptive AI Mock Interview Engine Configuration
    AI_PROVIDER: Optional[str] = None  # "gemini" | "openai" | None
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    AI_MODEL_NAME: Optional[str] = None
    GEMINI_DEFAULT_MODEL: str = "gemini-1.5-flash"
    GEMINI_API_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
    AI_TEMPERATURE: float = 0.7
    AI_REQUEST_TIMEOUT_SECONDS: float = 20.0
    INTERVIEW_TOTAL_QUESTIONS_DEFAULT: int = 5
    ALLOW_MOCK_EVALUATOR_FALLBACK: Optional[bool] = None

    # Sandboxed Code Execution Service Configuration (Judge0 Compatible API)
    JUDGE0_API_URL: Optional[str] = None  # e.g. "https://judge0-ce.p.rapidapi.com" or "http://localhost:2358"
    JUDGE0_API_KEY: Optional[str] = None  # RapidAPI Key or X-Auth-Token
    JUDGE0_API_HOST: Optional[str] = None # e.g. "judge0-ce.p.rapidapi.com"
    JUDGE0_AUTH_TOKEN: Optional[str] = None # e.g. X-Auth-Token for self-hosted Judge0 instances
    CODE_EXECUTION_TIMEOUT_SECONDS: float = 12.0
    CODE_EXECUTION_CPU_TIME_LIMIT: float = 5.0
    CODE_EXECUTION_WALL_TIME_LIMIT: float = 10.0
    CODE_EXECUTION_MEMORY_LIMIT_KB: int = 128000
    CODE_EXECUTION_MAX_SOURCE_LENGTH: int = 65536
    CODE_EXECUTION_MAX_INPUT_LENGTH: int = 16384

    @property
    def is_demo_otp_allowed(self) -> bool:
        """
        Fail-closed security check for demo OTP hint exposure:
        Returns True ONLY if ALL of the following criteria are strictly met:
        1. Explicit DEMO_MODE flag is True.
        2. ENVIRONMENT is strictly 'development' or 'dev'.
        3. Real email dispatch (EMAIL_DISPATCH_ENABLED) is False.
        Fails closed (returns False) if any criteria are not satisfied or conflict.
        """
        env = (self.ENVIRONMENT or "").strip().lower()
        if not self.DEMO_MODE:
            return False
        if env not in ("development", "dev"):
            return False
        if self.EMAIL_DISPATCH_ENABLED:
            return False
        return True

    # Configuration metadata (sanitized diagnostics)
    CONFIG_FILE_PATH: str = str(_active_env_file)
    CONFIG_FILE_LOADED: bool = _active_env_exists

    @property
    def resolved_gemini_model(self) -> str:
        """
        Resolves the configured Gemini model name with priority:
        1. AI_MODEL_NAME (if set and non-empty)
        2. GEMINI_DEFAULT_MODEL (defaults to 'gemini-1.5-flash')
        Safely strips any leading 'models/' prefix to avoid malformed API endpoint URLs.
        """
        model = (self.AI_MODEL_NAME or self.GEMINI_DEFAULT_MODEL or "gemini-1.5-flash").strip()
        if model.startswith("models/"):
            model = model[len("models/"):]
        return model

    @property
    def target_database_type(self) -> str:
        """Sanitized descriptor of the database target without exposing secrets."""
        uri = (self.MONGODB_URI or "").lower().strip()
        if uri.startswith("mongodb+srv://"):
            return "MongoDB Atlas (Remote SRV)"
        elif "localhost" in uri or "127.0.0.1" in uri or uri.startswith("mongodb://127."):
            return "Local MongoDB (localhost)"
        elif uri.startswith("mongodb://"):
            return "Remote MongoDB (Direct)"
        return "Unknown / Custom Target"

    @property
    def is_remote_or_atlas(self) -> bool:
        """Returns True if the resolved database target is a remote Atlas or non-localhost cluster."""
        uri = (self.MONGODB_URI or "").lower().strip()
        if uri.startswith("mongodb+srv://"):
            return True
        if "localhost" in uri or "127.0.0.1" in uri or uri.startswith("mongodb://127."):
            return False
        return bool(self.MONGODB_URI and self.MONGODB_URI != "mongodb://localhost:27017")

    def get_sanitized_diagnostic(self) -> Dict[str, Any]:
        """Returns sanitized configuration diagnostics safe for logs and console display."""
        return {
            "config_file_path": self.CONFIG_FILE_PATH if self.CONFIG_FILE_LOADED else f"{self.CONFIG_FILE_PATH} (NOT LOADED)",
            "config_file_loaded": self.CONFIG_FILE_LOADED,
            "target_database_type": self.target_database_type,
            "database_name": self.MONGODB_DB_NAME,
            "interview_database_name": self.INTERVIEW_DB_NAME,
            "is_remote_or_atlas": self.is_remote_or_atlas,
            "environment": self.ENVIRONMENT,
            "ai_provider": self.AI_PROVIDER or "mock (fallback default)",
            "gemini_model": self.resolved_gemini_model,
            "has_gemini_key": bool(self.GEMINI_API_KEY and self.GEMINI_API_KEY.strip()),
            "email_dispatch_enabled": self.EMAIL_DISPATCH_ENABLED,
            "has_smtp_host": bool(self.SMTP_HOST),
            "smtp_port": self.SMTP_PORT,
            "smtp_use_ssl": self.SMTP_USE_SSL,
            "smtp_use_tls": self.SMTP_USE_TLS,
            "has_smtp_credentials": bool(self.SMTP_USERNAME and self.SMTP_PASSWORD),
            "has_judge0_configured": bool(self.JUDGE0_API_URL and self.JUDGE0_API_URL.strip()),
            "judge0_api_url": self.JUDGE0_API_URL if self.JUDGE0_API_URL else None,
        }

    @model_validator(mode="before")
    @classmethod
    def resolve_smtp_environment_aliases(cls, data: Any) -> Any:
        """
        Resolves SMTP configuration across multiple common cloud environment variable naming conventions
        (e.g. Render, Gmail, Flask-Mail, Django standard aliases).
        Sanitizes whitespace from Google App Passwords and configures SSL/TLS according to port.
        """
        if not isinstance(data, dict):
            return data

        env = dict(os.environ)

        def get_val(*keys):
            for k in keys:
                if k in data and data[k] is not None:
                    return data[k]
                for ek, ev in env.items():
                    if ek.lower() == k.lower() and str(ev).strip():
                        return str(ev).strip()
            return None

        # 1. Resolve host
        host = get_val("SMTP_HOST", "SMTP_SERVER", "MAIL_SERVER", "EMAIL_HOST")
        if host:
            data["SMTP_HOST"] = host

        # 2. Resolve port
        port_raw = get_val("SMTP_PORT", "MAIL_PORT", "EMAIL_PORT")
        if port_raw:
            try:
                data["SMTP_PORT"] = int(port_raw)
            except (ValueError, TypeError):
                pass

        # 3. Resolve username
        user = get_val("SMTP_USERNAME", "SMTP_USER", "MAIL_USERNAME", "EMAIL_HOST_USER", "GMAIL_USER")
        if user:
            data["SMTP_USERNAME"] = user

        # 4. Resolve password
        pwd = get_val("SMTP_PASSWORD", "SMTP_PASS", "MAIL_PASSWORD", "EMAIL_HOST_PASSWORD", "GMAIL_APP_PASSWORD", "GMAIL_PASSWORD")
        if pwd:
            pwd_clean = str(pwd).strip()
            host_check = (data.get("SMTP_HOST") or "").lower()
            if "gmail" in host_check and " " in pwd_clean:
                pwd_clean = pwd_clean.replace(" ", "")
            data["SMTP_PASSWORD"] = pwd_clean

        # 5. Resolve dispatch enabled
        dispatch = get_val("EMAIL_DISPATCH_ENABLED", "ENABLE_EMAIL_DISPATCH")
        if dispatch is not None:
            if isinstance(dispatch, str):
                data["EMAIL_DISPATCH_ENABLED"] = dispatch.lower() in ("true", "1", "yes", "on")
            else:
                data["EMAIL_DISPATCH_ENABLED"] = bool(dispatch)
        elif data.get("SMTP_HOST") and data.get("SMTP_PASSWORD"):
            data["EMAIL_DISPATCH_ENABLED"] = True

        # 6. Resolve SSL vs TLS
        resolved_port = data.get("SMTP_PORT", 587)
        ssl_val = get_val("SMTP_USE_SSL", "SMTP_SSL", "MAIL_USE_SSL")
        if ssl_val is not None:
            if isinstance(ssl_val, str):
                data["SMTP_USE_SSL"] = ssl_val.lower() in ("true", "1", "yes", "on")
            else:
                data["SMTP_USE_SSL"] = bool(ssl_val)
        elif resolved_port == 465:
            data["SMTP_USE_SSL"] = True
            data["SMTP_USE_TLS"] = False

        tls_val = get_val("SMTP_USE_TLS", "MAIL_USE_TLS", "EMAIL_USE_TLS")
        if tls_val is not None:
            if isinstance(tls_val, str):
                data["SMTP_USE_TLS"] = tls_val.lower() in ("true", "1", "yes", "on")
            else:
                data["SMTP_USE_TLS"] = bool(tls_val)
        elif resolved_port == 465:
            data["SMTP_USE_TLS"] = False

        # 7. Resolve from email
        from_email = get_val("SMTP_FROM_EMAIL", "MAIL_FROM", "DEFAULT_FROM_EMAIL")
        if from_email:
            data["SMTP_FROM_EMAIL"] = from_email

        return data

    @model_validator(mode="after")
    def resolve_mock_evaluator_fallback_default(self) -> "Settings":
        """
        Enforce fail-closed AI evaluation in production:
        Defaults ALLOW_MOCK_EVALUATOR_FALLBACK to False when ENVIRONMENT is 'production' or 'prod'.
        In development or test environments, defaults to True to allow automated testing
        and local development unless explicitly overridden.
        """
        if self.ALLOW_MOCK_EVALUATOR_FALLBACK is None:
            env = (self.ENVIRONMENT or "").strip().lower()
            if env in ("production", "prod"):
                self.ALLOW_MOCK_EVALUATOR_FALLBACK = False
            else:
                self.ALLOW_MOCK_EVALUATOR_FALLBACK = True
        return self

    @model_validator(mode="after")
    def validate_test_mode_database_isolation(self) -> "Settings":
        """
        Strict fail-safe validation:
        If ENVIRONMENT is 'test' or 'testing', both database names must be explicitly
        designated test targets. Rejects any attempt to use production database names or
        un-isolated defaults in test mode before accepting requests or performing writes.
        """
        env = (self.ENVIRONMENT or "").strip().lower()
        if env in ("test", "testing"):
            auth_db = (self.MONGODB_DB_NAME or "").strip()
            interview_db = (self.INTERVIEW_DB_NAME or "").strip()

            # 1. Reject exact matches against protected production databases
            protected_lower = [d.lower() for d in self.PROTECTED_PRODUCTION_DATABASES]
            if auth_db.lower() in protected_lower:
                raise ValueError(
                    f"FATAL TEST ISOLATION ERROR: Test mode active (ENVIRONMENT='{self.ENVIRONMENT}'), "
                    f"but MONGODB_DB_NAME is set to protected production target '{auth_db}'. "
                    f"Test execution must use an isolated database (e.g. 'vfstr_interview_test')."
                )

            if interview_db.lower() in protected_lower:
                raise ValueError(
                    f"FATAL TEST ISOLATION ERROR: Test mode active (ENVIRONMENT='{self.ENVIRONMENT}'), "
                    f"but INTERVIEW_DB_NAME is set to protected production target '{interview_db}'. "
                    f"Test execution must use an isolated database (e.g. 'interview_db_test')."
                )

            # 2. Require explicit test designation in both database names
            if "test" not in auth_db.lower():
                raise ValueError(
                    f"FATAL TEST ISOLATION ERROR: Test mode requires MONGODB_DB_NAME to explicitly include 'test' "
                    f"(current: '{auth_db}')."
                )

            if "test" not in interview_db.lower():
                raise ValueError(
                    f"FATAL TEST ISOLATION ERROR: Test mode requires INTERVIEW_DB_NAME to explicitly include 'test' "
                    f"(current: '{interview_db}')."
                )

        return self

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret_in_production(cls, v: str, info) -> str:
        # Prevent starting in production with the known dev secret key
        env = os.getenv("ENVIRONMENT", "development").lower()
        if env in ("production", "prod") and v == "vfstr_dev_secret_key_8e29a1b4c3d5f670e8a9b2c3d4e5f6a7":
            raise ValueError(
                "FATAL: Production environment detected with default development JWT_SECRET_KEY. "
                "You must configure a secure, random JWT_SECRET_KEY in production."
            )
        return v

    @field_validator("JUDGE0_API_URL")
    @classmethod
    def validate_judge0_url_in_production(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        clean_url = v.strip()
        env = os.getenv("ENVIRONMENT", "development").lower()
        is_prod = env in ("production", "prod") or bool(os.getenv("RENDER"))
        if is_prod:
            lowered = clean_url.lower()
            if "localhost" in lowered or "127.0.0.1" in lowered or "0.0.0.0" in lowered:
                raise ValueError(
                    "Production configuration error: JUDGE0_API_URL cannot point to localhost or 127.0.0.1. "
                    "In deployed production, configure a remotely reachable Judge0 URL "
                    "(e.g. 'https://ce.judge0.com' or 'https://judge0-ce.p.rapidapi.com')."
                )
        return clean_url

    def __init__(self, **values):
        resolved_path, exists = resolve_env_file()
        if "_env_file" not in values and exists:
            values["_env_file"] = str(resolved_path)
        super().__init__(**values)
        if "_env_file" in values and values["_env_file"] is None:
            self.CONFIG_FILE_LOADED = False
            self.CONFIG_FILE_PATH = "[DISABLED / NONE]"
        else:
            self.CONFIG_FILE_LOADED = exists
            self.CONFIG_FILE_PATH = str(resolved_path)

    model_config = SettingsConfigDict(
        env_file=str(_active_env_file) if _active_env_exists else ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
