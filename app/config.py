from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APIFY_TOKEN: str
    APIFY_ACTOR_ID: str = "compass~crawler-google-places"
    N8N_WEBHOOK_URL: str

    APP_ENV: str = "development"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()