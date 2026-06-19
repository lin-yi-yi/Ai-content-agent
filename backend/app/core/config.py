"""应用配置"""
import os
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent.parent.parent.parent / ".env"
load_dotenv(ENV_PATH)


class Settings:
    APP_ENV = os.getenv("APP_ENV", "local")
    APP_NAME = os.getenv("APP_NAME", "AI Content Growth Agent")
    BACKEND_CORS_ORIGINS = os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:5173")
    DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root@127.0.0.1:3306/ai_content_agent?charset=utf8mb4")
    DEFAULT_LLM_PROVIDER = os.getenv("DEFAULT_LLM_PROVIDER", "deepseek")
    DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "deepseek-chat")
    TOPIC_SCORE_PROVIDER = os.getenv("TOPIC_SCORE_PROVIDER", DEFAULT_LLM_PROVIDER)
    TOPIC_SCORE_MODEL = os.getenv("TOPIC_SCORE_MODEL", DEFAULT_LLM_MODEL)
    DRAFT_GENERATION_PROVIDER = os.getenv("DRAFT_GENERATION_PROVIDER", DEFAULT_LLM_PROVIDER)
    DRAFT_GENERATION_MODEL = os.getenv("DRAFT_GENERATION_MODEL", DEFAULT_LLM_MODEL)
    CARD_GENERATION_PROVIDER = os.getenv("CARD_GENERATION_PROVIDER", DEFAULT_LLM_PROVIDER)
    CARD_GENERATION_MODEL = os.getenv("CARD_GENERATION_MODEL", DEFAULT_LLM_MODEL)
    COMPLIANCE_CHECK_PROVIDER = os.getenv("COMPLIANCE_CHECK_PROVIDER", DEFAULT_LLM_PROVIDER)
    COMPLIANCE_CHECK_MODEL = os.getenv("COMPLIANCE_CHECK_MODEL", DEFAULT_LLM_MODEL)


settings = Settings()
