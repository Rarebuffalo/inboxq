import os
import logging
from typing import Any, Dict
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized configuration management using Pydantic Settings.
    Environment variables are automatically validated and parsed.
    """
    # Environment & Server Config
    ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Database Settings
    DATABASE_URL: str = "sqlite:///./tickets.db"

    # AI Service Settings
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Instantiate settings globally
settings = Settings()


def setup_logging() -> logging.Logger:
    """
    Configure standard library logging format, handlers, and levels.
    """
    log_level = logging.DEBUG if settings.DEBUG else logging.getLevelName(settings.LOG_LEVEL)
    
    # Configure the root logger
    logging.basicConfig(
        level=log_level,
        format=settings.LOG_FORMAT,
        handlers=[
            logging.StreamHandler()
        ]
    )
    
    # Get logger for our application
    logger = logging.getLogger("InboxIQ")
    logger.setLevel(log_level)
    return logger


# Instantiate logger globally
logger = setup_logging()
