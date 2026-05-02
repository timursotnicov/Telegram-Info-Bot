import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _load_environment() -> None:
    """Load environment-specific dotenv files without overriding real env vars."""
    app_env = os.getenv("APP_ENV", "dev").strip().lower() or "dev"
    explicit_env_file = os.getenv("ENV_FILE")

    candidates = []
    if explicit_env_file:
        candidates.append(Path(explicit_env_file))
    candidates.append(Path(f".env.{app_env}"))
    candidates.append(Path(".env"))

    for env_path in candidates:
        if env_path.exists():
            load_dotenv(env_path, override=False)


_load_environment()


@dataclass
class Config:
    app_env: str = os.getenv("APP_ENV", "dev")
    bot_token: str = os.getenv("BOT_TOKEN", "")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    ai_model: str = os.getenv("AI_MODEL", "google/gemini-2.5-flash-lite")
    ai_fallback_models: list = None  # Set in __post_init__ equivalent below
    ocr_model: str = os.getenv("OCR_MODEL", "google/gemini-2.5-flash-lite")
    db_path: str = os.getenv("DB_PATH", "savebot.db")
    webhook_host: str = os.getenv("WEBHOOK_HOST", "")
    webhook_path: str = os.getenv("WEBHOOK_PATH", "/webhook")
    webhook_port: int = int(os.getenv("WEBHOOK_PORT", "8443"))
    use_polling: bool = os.getenv("USE_POLLING", "true").lower() == "true"


config = Config()


def _parse_allowed_users():
    users_str = os.getenv("ALLOWED_USERS", "")
    if not users_str:
        return []
    return [int(u.strip()) for u in users_str.split(",") if u.strip()]


def _parse_model_list(value: str) -> list[str]:
    return [m.strip() for m in value.split(",") if m.strip()]


def _unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


config.allowed_users = _parse_allowed_users()
_configured_fallback_models = _parse_model_list(os.getenv("AI_FALLBACK_MODELS", ""))
config.ai_fallback_models = _unique([
    config.ai_model,
    *(_configured_fallback_models or [
        "google/gemini-2.5-flash",
        "openrouter/free",
        "openai/gpt-oss-20b:free",
    ]),
])

def _validate_config():
    """Fail fast with clear error if required env vars are missing."""
    if not config.bot_token:
        raise ValueError("BOT_TOKEN environment variable is required. Set it in .env file.")
    if not config.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is required. Set it in .env file.")

_validate_config()
