from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APIFY_TOKEN: str
    APIFY_ACTOR_ID: str = "compass~crawler-google-places"
    N8N_WEBHOOK_URL: str = ""

    DATABASE_URL: str = "sqlite:///./data/catering_outreach.db"
    API_KEY: Optional[str] = None

    SENDGRID_API_KEY: Optional[str] = None
    SENDGRID_FROM_EMAIL: Optional[str] = None
    SENDGRID_FROM_NAME: str = "Catering Outreach Team"

    APP_ENV: str = "development"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
