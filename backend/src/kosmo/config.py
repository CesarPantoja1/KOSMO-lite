import tempfile
from pathlib import Path
from typing import Literal, Self
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_postgres_url(raw: str) -> str:
    """Normaliza una URL de PostgreSQL para asyncpg, incluyendo Supabase Pooler.

    - Reemplaza el scheme ``postgresql://`` por ``postgresql+asyncpg://``.
    - En conexiones pooler (Supabase o puerto 6543) desactiva el statement cache,
      que es incompatible con PgBouncer en modo transaction.
    """
    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+asyncpg://", 1)

    parsed = urlsplit(raw)
    if parsed.scheme == "postgresql+asyncpg" and (
        (
            parsed.hostname is not None
            and (
                parsed.hostname.endswith(".pooler.supabase.com")
                or parsed.hostname.endswith(".supabase.co")
                or "pooler" in parsed.hostname
            )
        )
        or parsed.port == 6543
    ):
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.pop("statement_cache_size", None)
        query.setdefault("prepared_statement_cache_size", "0")
        raw = urlunsplit(parsed._replace(query=urlencode(query)))

    return raw


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Runtime
    env: Literal["development", "staging", "production"]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Secretos criptográficos — contenido PEM (prioridad) o rutas como fallback
    jwt_private_key_pem: SecretStr | None = None
    jwt_public_key_pem: SecretStr | None = None
    jwt_private_key_path: str | None = None
    jwt_public_key_path: str | None = None
    fernet_master_key: SecretStr | None = None

    # JWT
    jwt_algorithm: Literal["RS256"] = "RS256"
    jwt_issuer: str = "kosmo"
    jwt_audience: str = "kosmo-api"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 604800

    # Argon2id (OWASP 2025)
    argon2_memory_kib: int = 65536
    argon2_time_cost: int = 3
    argon2_parallelism: int = 4

    # DSN de persistencia
    database_url: SecretStr
    redis_url: SecretStr | None = None
    db_pool_size: int = 60
    db_max_overflow: int = 40
    db_pool_timeout: float = 45.0
    db_pool_recycle: int = 1800
    redis_max_connections: int = 150
    redis_socket_timeout: float = 10.0
    redis_socket_connect_timeout: float = 5.0

    # LLM BYOK
    llm_provider: Literal["anthropic", "openai", "gemini", "deepseek", "noop"]
    llm_model: str
    llm_api_key: SecretStr | None = None
    llm_max_concurrency: int = 100
    user_ai_config_cache_ttl_seconds: float = 60.0

    # Embeddings
    embedding_provider: Literal["auto", "openai", "fastembed", "none"] = "auto"

    # Codegen (OpenCode)
    opencode_base_url: str = "http://127.0.0.1:4096"
    opencode_launcher_base_url: str | None = None
    opencode_launcher_token: SecretStr | None = None
    opencode_server_username: str = "opencode"
    opencode_server_password: SecretStr | None = None
    opencode_model: str | None = None
    opencode_timeout_seconds: float = 900.0
    opencode_read_timeout_seconds: float = 900.0
    opencode_connect_timeout_seconds: float = 30.0
    opencode_write_timeout_seconds: float = 60.0
    kosmo_workspaces_dir: Path = Field(default_factory=lambda: Path(tempfile.gettempdir()) / "kosmo-workspaces")
    kosmo_mcp_base_url: str = "http://127.0.0.1:8000/mcp"
    code_runner_base_url: str | None = None
    code_runner_token: SecretStr | None = None
    implementation_broker_ttl_seconds: float = 1800.0

    # Integraciones
    github_client_id: str | None = None
    github_client_secret: SecretStr | None = None
    railway_client_id: str | None = None
    railway_client_secret: SecretStr | None = None

    # API
    api_version: str = "v1"
    cors_allowed_origins: str = "http://localhost:3000"
    auth_disabled: bool = False
    rate_limit_required: bool = False
    generation_rate_limit_per_hour: int = 120
    trusted_proxies: str = "127.0.0.1,::1,testclient,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    server_workers: int = Field(default=1, validation_alias="WORKERS")

    # Observabilidad
    logfire_token: SecretStr | None = None
    otel_service_name: str = "kosmo-backend"
    otel_environment: str = "development"

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_async_postgres_url(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            return normalize_postgres_url(value.get_secret_value())
        if isinstance(value, str):
            return normalize_postgres_url(value)
        return value

    @model_validator(mode="after")
    def _resolve_signing_keys(self) -> Self:
        """Resuelve el contenido PEM: variable de entorno → lectura de archivo."""
        if self.auth_disabled:
            if self.env == "production":
                raise ValueError("AUTH_DISABLED no puede ser 'true' en entorno de producción.")
            return self

        if self.jwt_private_key_pem is None:
            if self.jwt_private_key_path is None:
                raise ValueError("Debe configurar JWT_PRIVATE_KEY_PEM o JWT_PRIVATE_KEY_PATH")
            pem = Path(self.jwt_private_key_path).read_text(encoding="utf-8")
            self.jwt_private_key_pem = SecretStr(pem)

        if self.jwt_public_key_pem is None:
            if self.jwt_public_key_path is None:
                raise ValueError("Debe configurar JWT_PUBLIC_KEY_PEM o JWT_PUBLIC_KEY_PATH")
            pem = Path(self.jwt_public_key_path).read_text(encoding="utf-8")
            self.jwt_public_key_pem = SecretStr(pem)

        if self.fernet_master_key is None:
            raise ValueError("Debe configurar FERNET_MASTER_KEY cuando AUTH_DISABLED=false")

        if self.redis_url is None:
            raise ValueError("Debe configurar REDIS_URL cuando AUTH_DISABLED=false")

        if self.env == "production" and self.redis_url:
            parsed_redis = urlsplit(self.redis_url.get_secret_value())
            if not parsed_redis.password:
                raise ValueError(
                    "REDIS_URL debe incluir contraseña de autenticación en entorno de producción "
                    "(ej. 'redis://:password@host:port/db')."
                )

        return self

    @property
    def parsed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _validate_cors_configuration(self) -> Self:
        if self.env == "production":
            origins = self.parsed_cors_origins
            if not origins:
                raise ValueError("Debe configurar al menos un origen en CORS_ALLOWED_ORIGINS para producción")
            if any(o == "*" for o in origins):
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS no puede ser '*' en entorno de producción. "
                    "Debe especificar orígenes explícitos (ej. 'https://app.kosmo.dev')."
                )
            for origin in origins:
                if not (origin.startswith("https://") or origin.startswith("http://")):
                    raise ValueError(
                        f"Origen CORS inválido '{origin}' en producción. Debe iniciar con 'https://' o 'http://'."
                    )
        return self


settings = Settings()  # pyright: ignore[reportCallIssue]
