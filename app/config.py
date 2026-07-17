from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/lms_idesp"
    SECRET_KEY: str = ""  # gere com: openssl rand -hex 32
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@lms-idesp.com"
    SMTP_TLS: bool = True

    RESET_TOKEN_EXPIRE_MINUTES: int = 60
    BASE_URL: str = "http://localhost:8000/api/v1"

    # Storage (desenvolvimento)
    STORAGE_BACKEND: str = "local"
    S3_ENDPOINT: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET: str = "lms-conteudos"
    S3_REGION: str = "us-east-1"
    MAX_UPLOAD_SIZE: int = 500 * 1024 * 1024

    # Storage (testes)
    TEST_STORAGE_BACKEND: str = ""
    TEST_S3_BUCKET: str = "lms-conteudos-test"

    # Database (testes)
    TEST_DATABASE_URL: str = ""

    # Teams / Microsoft Graph
    TEAMS_TENANT_ID: str = ""
    TEAMS_CLIENT_ID: str = ""
    TEAMS_CLIENT_SECRET: str = ""
    TEAMS_ORGANIZER_EMAIL: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @model_validator(mode="after")
    def normalize_database_url(self) -> "Settings":
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if "sslmode=" in url:
            url = url.split("?")[0]
        self.DATABASE_URL = url

        test_url = self.TEST_DATABASE_URL
        if test_url.startswith("postgres://"):
            test_url = test_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif test_url.startswith("postgresql://"):
            test_url = test_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if "sslmode=" in test_url:
            test_url = test_url.split("?")[0]
        self.TEST_DATABASE_URL = test_url

        return self


settings = Settings()
