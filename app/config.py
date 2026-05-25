"""
アプリ全体の設定を .env から読み込むモジュール
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# プロジェクトルート（salon-color-inventory/）のパス
BASE_DIR = Path(__file__).resolve().parent.parent

def _load_env() -> None:
    """プロジェクトルートの .env を読み込む（uvicorn の cwd に依存しない）"""
    load_dotenv(BASE_DIR / ".env", override=True)


def _get_settings() -> "Settings":
    """起動のたびに最新の環境変数を反映する"""
    _load_env()
    return Settings(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-secret-key"),
        ACCESS_TOKEN_EXPIRE_MINUTES=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")),
        DATABASE_URL=os.getenv("DATABASE_URL", "sqlite:///./data/inventory.db"),
        ANTHROPIC_API_KEY=(os.getenv("ANTHROPIC_API_KEY") or "").strip(),
        ANTHROPIC_MODEL=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514").strip(),
        ALGORITHM="HS256",
    )


class Settings:
    """環境変数をまとめて管理するクラス"""

    def __init__(
        self,
        SECRET_KEY: str,
        ACCESS_TOKEN_EXPIRE_MINUTES: int,
        DATABASE_URL: str,
        ANTHROPIC_API_KEY: str,
        ANTHROPIC_MODEL: str,
        ALGORITHM: str,
    ):
        self.SECRET_KEY = SECRET_KEY
        self.ACCESS_TOKEN_EXPIRE_MINUTES = ACCESS_TOKEN_EXPIRE_MINUTES
        self.DATABASE_URL = DATABASE_URL
        self.ANTHROPIC_API_KEY = ANTHROPIC_API_KEY
        self.ANTHROPIC_MODEL = ANTHROPIC_MODEL
        self.ALGORITHM = ALGORITHM


# 後方互換: from app.config import settings
settings = _get_settings()
