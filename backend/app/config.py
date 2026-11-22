import os
import secrets
from typing import List
from pathlib import Path
from dotenv import load_dotenv

# Try to find .env file at the project root
_base_dir = Path(__file__).resolve().parent.parent.parent
_env_file = _base_dir / ".env"

if _env_file.exists():
    load_dotenv(dotenv_path=_env_file)
else:
    load_dotenv()


class Settings:
    APP_ENV: str = os.getenv("APP_ENV", "production").strip().lower()
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ADMIN_PIN: str = os.getenv("ADMIN_PIN", "")
    ALLOW_INSECURE_TEST_PIN: bool = os.getenv("ALLOW_INSECURE_TEST_PIN", "false").lower() in ("true", "1", "yes")
    ALLOWED_ORIGINS_RAW: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
    STORE_OPEN: bool = os.getenv("STORE_OPEN", "false").lower() in ("true", "1", "yes")
    TRUST_PROXY: bool = os.getenv("TRUST_PROXY", "false").lower() in ("true", "1", "yes")

    _raw_db = os.getenv("DB_URL", "sqlite:///./smartshelf.db")
    if _raw_db.startswith("sqlite:///."):
        DB_URL: str = f"sqlite:///{(_base_dir / _raw_db.replace('sqlite:///./', '')).as_posix()}"
    else:
        DB_URL: str = _raw_db

    @property
    def DATABASE_URL(self) -> str:
        return self.DB_URL
    TOKEN_TTL_SECONDS: int = int(os.getenv("TOKEN_TTL_SECONDS", "28800"))
    ENTRY_TOKEN_TTL_SECONDS: int = int(os.getenv("ENTRY_TOKEN_TTL_SECONDS", "30"))
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", str(_base_dir / "frontend" / "static" / "uploads"))
    STABLE_SECONDS: float = float(os.getenv("STABLE_SECONDS", "1.5"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", f"http://localhost:{os.getenv('PORT', '8000')}").rstrip("/")
    FRONTEND_PUBLIC_URL: str = os.getenv("FRONTEND_PUBLIC_URL", "")
    USE_SSL: bool = os.getenv("USE_SSL", "false").lower() in ("true", "1", "yes")
    SSL_CERT_FILE: str = os.getenv("SSL_CERT_FILE", "certs/cert.pem")
    SSL_KEY_FILE: str = os.getenv("SSL_KEY_FILE", "certs/key.pem")
    THRESHOLD_PRESENT: float = float(os.getenv("THRESHOLD_PRESENT", "0.60"))
    THRESHOLD_ABSENT: float = float(os.getenv("THRESHOLD_ABSENT", "0.60"))
    SIMILARITY_ALPHA: float = float(os.getenv("SIMILARITY_ALPHA", "0.5"))
    SESSION_IDLE_TIMEOUT: int = int(os.getenv("SESSION_IDLE_TIMEOUT", "900"))
    _raw_model = os.getenv("RECOGNITION_MODEL_PATH", "ai/models/mobilenetv2-7.onnx")
    RECOGNITION_MODEL_PATH: str = str((_base_dir / _raw_model).resolve())
    RECOGNITION_ACCEPT_THRESHOLD: float = float(os.getenv("RECOGNITION_ACCEPT_THRESHOLD", "0.65"))
    RECOGNITION_MARGIN_THRESHOLD: float = float(os.getenv("RECOGNITION_MARGIN_THRESHOLD", "0.08"))
    BOTTLE_MODEL_PATH: str = str((_base_dir / os.getenv("BOTTLE_MODEL_PATH", "ai/models/yolo26n.onnx")).resolve())
    BOTTLE_DATASET_DIR: str = str((_base_dir / os.getenv("BOTTLE_DATASET_DIR", "data/bottle_dataset")).resolve())

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if k in ("TRUST_PROXY", "STORE_OPEN", "USE_SSL", "ALLOW_INSECURE_TEST_PIN") and isinstance(v, str):
                v = v.lower() in ("true", "1", "yes")
            setattr(self, k, v)

    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        origins = []
        if self.ALLOWED_ORIGINS_RAW:
            origins.extend([o.strip() for o in self.ALLOWED_ORIGINS_RAW.split(",") if o.strip()])
        if self.FRONTEND_PUBLIC_URL:
            f_url = self.FRONTEND_PUBLIC_URL.strip().rstrip("/")
            if f_url and f_url not in origins:
                origins.append(f_url)
        if self.PUBLIC_BASE_URL:
            p_url = self.PUBLIC_BASE_URL.strip().rstrip("/")
            if p_url and p_url not in origins:
                origins.append(p_url)
        if not origins:
            return ["http://localhost:8000", "http://127.0.0.1:8000"]
        return origins

    def validate_security(self, allow_dev_pin: bool = False):
        """Validate security requirements on startup."""
        if not self.SECRET_KEY:
            if self.APP_ENV == "production":
                raise ValueError("SECURITY ERROR: SECRET_KEY must be configured in production.")
            self.SECRET_KEY = secrets.token_hex(32)
        if self.APP_ENV == "production" and (
            len(self.SECRET_KEY) < 32 or self.SECRET_KEY.lower().startswith("change-me")
        ):
            raise ValueError("SECURITY ERROR: SECRET_KEY must be a strong random value in production.")

        pin = (self.ADMIN_PIN or "").strip()
        if pin == "1234" and self.ALLOW_INSECURE_TEST_PIN and self.STORE_OPEN:
            raise ValueError("SECURITY ERROR: Test PIN 1234 requires STORE_OPEN=false. Set a strong PIN before opening the store.")
        explicit_test_pin = pin == "1234" and self.ALLOW_INSECURE_TEST_PIN and not self.STORE_OPEN
        short_pin_allowed = pin == "1234" and (allow_dev_pin or explicit_test_pin)
        if not pin or (pin == "1234" and not short_pin_allowed) or (len(pin) < 8 and not short_pin_allowed) or (self.APP_ENV == "production" and pin.lower().startswith("change-me")):
            raise ValueError(
                "SECURITY ERROR: Insecure ADMIN_PIN! "
                "ADMIN_PIN cannot be empty, '1234', or shorter than 8 characters. "
                "Please configure a strong PIN in .env or run 'scripts\\gen_secrets.bat'."
            )


        try:
            token_ttl = int(self.TOKEN_TTL_SECONDS)
        except (TypeError, ValueError):
            raise ValueError("SECURITY ERROR: TOKEN_TTL_SECONDS must be an integer.")
        if not 60 <= token_ttl <= 86400:
            raise ValueError("SECURITY ERROR: TOKEN_TTL_SECONDS must be between 60 and 86400 seconds.")
        if not 15 <= int(self.ENTRY_TOKEN_TTL_SECONDS) <= 300:
            raise ValueError("SECURITY ERROR: ENTRY_TOKEN_TTL_SECONDS must be between 15 and 300 seconds.")


settings = Settings()
settings.validate_security(allow_dev_pin=False)
