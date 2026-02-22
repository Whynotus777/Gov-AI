"""Application configuration."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "GovContract AI"
    debug: bool = False
    
    # SAM.gov API
    sam_gov_api_key: str = ""
    sam_gov_base_url: str = "https://api.sam.gov/prod/opportunities/v2/search"
    
    # Anthropic
    anthropic_api_key: str = ""
    
    # Supabase (V2)
    supabase_url: str = ""
    supabase_anon_key: str = ""

    # PostgreSQL — asyncpg connection string (leave blank for in-memory V1 mode)
    # Format: postgresql+asyncpg://user:password@host:port/dbname
    # Supabase: postgresql+asyncpg://postgres.{ref}:{pw}@{region}.pooler.supabase.com:5432/postgres
    database_url: str = ""
    
    # Matching thresholds
    high_match_threshold: float = 70.0
    medium_match_threshold: float = 50.0
    
    # Rate limiting
    sam_requests_per_second: int = 10
    claude_max_tokens_per_analysis: int = 1024

    # Email alerts (SendGrid)
    sendgrid_api_key: str = ""
    alert_email_to: str = ""

    # Scout agent
    scout_interval_hours: int = 6
    scout_score_threshold: float = 40.0

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
