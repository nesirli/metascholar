from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "MetaScholar"
    # Relative to the working directory (repo root locally, /app in the container),
    # so it resolves correctly whether the package is run from source or installed
    # into site-packages. Override with CORPUS_PATH if needed.
    corpus_path: Path = Path("data/corpus.jsonl")

    openai_api_key: str
    # Hosted platforms (e.g. Dokploy) provide DATABASE_URL; individual variables
    # are used for local development.
    database_url: str | None = None
    postgres_host: str | None = None
    postgres_db: str | None = None
    postgres_user: str | None = None
    postgres_password: str | None = None
    app_username: str
    app_password: str

    def get_postgres_kwargs(self) -> dict:
        """Return psycopg connection kwargs.

        Explicit POSTGRES_* variables take precedence, so deployments that set
        them keep working even if the platform also injects DATABASE_URL.
        If only DATABASE_URL is set (the usual hosted case), use that.
        """
        if self.postgres_host:
            return {
                "host": self.postgres_host,
                "dbname": self.postgres_db,
                "user": self.postgres_user,
                "password": self.postgres_password,
            }

        if self.database_url:
            parsed = urlparse(self.database_url)
            query = parse_qs(parsed.query)
            kwargs = {
                "host": parsed.hostname,
                "dbname": parsed.path.lstrip("/"),
                "user": parsed.username,
                "password": parsed.password,
                "port": parsed.port or 5432,
            }
            if "sslmode" in query:
                kwargs["sslmode"] = query["sslmode"][0]
            return kwargs

        raise ValueError(
            "No Postgres configuration found. Set DATABASE_URL "
            "or POSTGRES_HOST/POSTGRES_DB/POSTGRES_USER/POSTGRES_PASSWORD."
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
