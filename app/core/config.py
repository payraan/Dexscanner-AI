import os
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: str
    CHAT_ID: str

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # API Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    # --- خطوط زیر اضافه شده‌اند ---
    BITQUERY_API_KEY: str = os.getenv("BITQUERY_API_KEY", "")
    HELIUS_API_KEY: str = os.getenv("HELIUS_API_KEY", "")

    # Scanner
    SCAN_INTERVAL: int = 180
    TRENDING_TOKENS_LIMIT: int = 50

    # Admin
    ADMIN_IDS: str = ""
    ADMIN_CHANNEL_ID: int = 0

    @property
    def admin_list(self) -> List[int]:
        if not self.ADMIN_IDS:
            return []
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip().isdigit()]

    class Config:
        env_file = ".env"

    # Redis
    REDIS_URL: str = ""

settings = Settings()
