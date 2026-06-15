from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


def _get_env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


@dataclass(frozen=True)
class AppConfig:
    env: str
    local_mode: bool
    secret_key: str
    api_host: str
    api_port: int
    auth_host: str
    auth_port: int
    dash_host: str
    dash_port: int

    @property
    def debug(self) -> bool:
        return self.local_mode


@dataclass(frozen=True)
class PostgresConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    external_host: str | None = None
    ssl_mode: str | None = None

    def dsn(self, external: bool = False) -> str:
        host = self.external_host if external and self.external_host else self.host
        ssl = f"?sslmode={self.ssl_mode}" if self.ssl_mode else ""
        user = quote_plus(self.user)
        password = quote_plus(self.password)
        return (
            f"postgresql://{user}:{password}@{host}:{self.port}/"
            f"{self.database}{ssl}"
        )


@dataclass(frozen=True)
class MongoConfig:
    host: str
    port: int
    database: str
    user: str | None = None
    password: str | None = None
    auth_source: str | None = None
    tls: bool = False
    uri: str | None = None

    def dsn(self) -> str:
        if self.uri:
            return self.uri
        credentials = ""
        if self.user and self.password:
            credentials = f"{quote_plus(self.user)}:{quote_plus(self.password)}@"
        options = []
        if self.auth_source:
            options.append(f"authSource={self.auth_source}")
        if self.tls:
            options.append("tls=true")
        query = f"?{'&'.join(options)}" if options else ""
        return f"mongodb://{credentials}{self.host}:{self.port}/{self.database}{query}"


def get_app_config() -> AppConfig:
    env = (_get_env("APP_ENV", "local") or "local").strip().lower()
    local_mode = _get_bool("LOCAL_MODE", env != "production")
    secret_key = _get_env("SECRET_KEY")
    if not secret_key:
        if local_mode:
            secret_key = "local-dev-secret-key"
        else:
            raise RuntimeError("")

    return AppConfig(
        env=env,
        local_mode=local_mode,
        secret_key=secret_key,
        api_host=_get_env("API_HOST", "127.0.0.1") or "127.0.0.1",
        api_port=_get_int("API_PORT", 8000),
        auth_host=_get_env("AUTH_HOST", "127.0.0.1") or "127.0.0.1",
        auth_port=_get_int("AUTH_PORT", 5002),
        dash_host=_get_env("DASH_HOST", "127.0.0.1") or "127.0.0.1",
        dash_port=_get_int("DASH_PORT", 5001),
    )


def get_postgres_config() -> PostgresConfig:
    return PostgresConfig(
        host=_get_env("POSTGRES_HOST", "localhost") or "localhost",
        port=_get_int("POSTGRES_PORT", 5432),
        database=_get_env("POSTGRES_DB", "proyecto_lgbti_relacional")
        or "proyecto_lgbti_relacional",
        user=_get_env("POSTGRES_USER", "postgres") or "postgres",
        password=_get_env("POSTGRES_PASSWORD", "") or "",
        external_host=_get_env("POSTGRES_EXTERNAL_HOST"),
        ssl_mode=_get_env("POSTGRES_SSL_MODE"),
    )


def get_mongo_config() -> MongoConfig:
    return MongoConfig(
        host=_get_env("MONGO_HOST", "localhost") or "localhost",
        port=_get_int("MONGO_PORT", 27017),
        database=_get_env("MONGO_DB", "proyecto_lgbti_no_relacional")
        or "proyecto_lgbti_no_relacional",
        user=_get_env("MONGO_USER"),
        password=_get_env("MONGO_PASSWORD"),
        auth_source=_get_env("MONGO_AUTH_SOURCE"),
        tls=_get_bool("MONGO_TLS", False),
        uri=_get_env("MONGO_URI"),
    )

