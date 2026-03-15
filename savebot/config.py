import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    ai_model: str = os.getenv("AI_MODEL", "google/gemma-3-27b-it:free")
    ai_fallback_models: list = None  # Set in __post_init__ equivalent below
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

config.allowed_users = _parse_allowed_users()
config.ai_fallback_models = [
    config.ai_model,
    "arcee-ai/trinity-large-preview:free",
    "google/gemma-3-12b-it:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
]
