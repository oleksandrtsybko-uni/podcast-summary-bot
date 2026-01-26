"""
Application settings and configuration.
Uses Pydantic Settings for environment variable management.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""
    
    # OpenAI Configuration
    openai_api_key: str = Field(..., description="OpenAI API key")
    openai_model: str = Field(
        default="gpt-4o",
        description="OpenAI model for summaries"
    )
    
    # Telegram Configuration
    telegram_bot_token: str = Field(..., description="Telegram bot token")
    telegram_chat_id: str = Field(..., description="Telegram chat/channel ID")
    
    # Application Settings
    log_level: str = Field(default="INFO", description="Logging level")
    data_dir: str = Field(default="data", description="Directory for data files")
    
    # Rate Limiting
    request_delay: float = Field(
        default=1.0,
        description="Delay between API requests in seconds"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance (lazy loaded)
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the application settings (singleton pattern)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
