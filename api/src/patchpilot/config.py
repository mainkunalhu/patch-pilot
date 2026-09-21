from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    groq_api_key: str = ""
    database_url: str = "postgresql://patchpilot:patchpilot@localhost:5432/patchpilot"
    ollama_host: str = "http://localhost:11434"
    embed_model: str = "nomic-embed-text"


settings = Settings()
