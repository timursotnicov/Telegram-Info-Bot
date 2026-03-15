import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    db_path: str = os.getenv("DB_PATH", "savebot.db")
    webhook_host: str = os.getenv("WEBHOOK_HOST", "")
    webhook_path: str = os.getenv("WEBHOOK_PATH", "/webhook")
    webhook_port: int = int(os.getenv("WEBHOOK_PORT", "8443"))
    use_polling: bool = os.getenv("USE_POLLING", "true").lower() == "true"


config = Config()
