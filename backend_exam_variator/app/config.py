"""Backend configuration."""

import os

from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("EXAM_DATA_DIR") or BASE_DIR.parent / "data")
FRONTEND_DIR = Path(
    os.environ.get("EXAM_FRONTEND_DIR") or BASE_DIR.parent / "frontend_exam_variator" / "out"
)
JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    cors_origins: list[str] = ["http://localhost:3000"]
    max_upload_size_mb: int = 50

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
