from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from urllib.parse import parse_qs, quote_plus, unquote, urlparse, urlsplit, urlunsplit

from dotenv import load_dotenv

if (
    os.getenv("APP_ENV", "local").strip().casefold() != "production"
    or os.getenv("LOCAL_MODE", "").strip().casefold() in {"1", "true", "yes", "on"}
):
    load_dotenv()

_LOCAL_SECRET_KEY = secrets.token_urlsafe(32)


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


def _get_clean_env(name: str, default: str | None = None) -> str | None:
    value = _get_env(name, default)
    if value is None:
        return None
    return value.strip().strip('"').strip("'") or None


def _is_production() -> bool:
    env = (_get_env("APP_ENV", "local") or "local").strip().lower()
    return env == "production" and not _get_bool("LOCAL_MODE", False)


@dataclass(frozen=True)
class AppConfig:
    env: str
    local_mode: bool
    secret_key: str = field(repr=False)
    api_host: str
    api_port: int
    auth_host: str
    auth_port: int
    dash_host: str
    dash_port: int
    use_mock_trend_data: bool = False

    @property
    def debug(self) -> bool:
        return self.local_mode


@dataclass(frozen=True)
class PostgresConfig:
    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)
    external_host: str | None = None
    ssl_mode: str | None = None

    def dsn(self, external: bool = False) -> str:
        host = self.external_host if external and self.external_host else self.host
        ssl = f"?sslmode={self.ssl_mode}" if self.ssl_mode else ""
        user = quote_plus(self.user)
        password = quote_plus(self.password)
        return f"postgresql://{user}:{password}@{host}:{self.port}/{self.database}{ssl}"


@dataclass(frozen=True)
class MongoConfig:
    host: str
    port: int
    database: str
    user: str | None = None
    password: str | None = field(default=None, repr=False)
    auth_source: str | None = None
    tls: bool = False
    uri: str | None = field(default=None, repr=False)
    server_selection_timeout_ms: int = 2500

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
    use_mock_trend_data = _get_bool("USE_MOCK_TREND_DATA", False)
    if env == "production" and not local_mode and use_mock_trend_data:
        raise RuntimeError("USE_MOCK_TREND_DATA cannot be enabled in production.")
    secret_key = _get_env("SECRET_KEY")
    if not secret_key:
        if local_mode:
            secret_key = _LOCAL_SECRET_KEY
        else:
            raise RuntimeError("SECRET_KEY must be configured in production.")
    if not local_mode and len(secret_key) < 32:
        raise RuntimeError("SECRET_KEY must contain at least 32 characters in production.")

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
        use_mock_trend_data=use_mock_trend_data,
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
        ssl_mode=_get_env("POSTGRES_SSL_MODE", "require" if _is_production() else None),
    )


def get_postgres_dsn() -> str:
    database_url = _get_clean_env("DATABASE_URL")
    if database_url:
        prefix = "DATABASE_URL="
        database_url = database_url.removeprefix(prefix)
        ssl_mode = _get_clean_env("POSTGRES_SSL_MODE", "require" if _is_production() else None)
        configured_ssl_mode = _postgres_ssl_mode(database_url)
        if _is_production() and configured_ssl_mode in {"allow", "disable", "prefer"}:
            raise RuntimeError("DATABASE_URL must require TLS in production.")
        if ssl_mode and configured_ssl_mode is None:
            separator = "&" if "?" in database_url else "?"
            database_url = f"{database_url}{separator}sslmode={quote_plus(ssl_mode)}"
        return os.path.expandvars(database_url)
    if _is_production() and not _get_clean_env("POSTGRES_HOST"):
        raise RuntimeError("DATABASE_URL or POSTGRES_HOST must be set in production.")
    return get_postgres_config().dsn()


def get_postgres_connect_timeout() -> int:
    return _get_int("DB_CONNECT_TIMEOUT_SECONDS", 3)


def get_mongo_config() -> MongoConfig:
    uri = _secure_mongo_uri(_get_clean_env("MONGO_URI"))
    host = _get_clean_env("MONGO_HOST")
    if _is_production() and not uri and not host:
        raise RuntimeError("MONGO_URI or MONGO_HOST must be set in production.")

    database = _get_clean_env("MONGO_DB") or _mongo_database_from_uri(uri)
    return MongoConfig(
        host=host or "localhost",
        port=_get_int("MONGO_PORT", 27017),
        database=database or "proyecto_lgbti_no_relacional",
        user=_get_env("MONGO_USER"),
        password=_get_env("MONGO_PASSWORD"),
        auth_source=_get_env("MONGO_AUTH_SOURCE"),
        tls=_get_bool("MONGO_TLS", _is_production()),
        uri=uri,
        server_selection_timeout_ms=_get_int("MONGO_SERVER_SELECTION_TIMEOUT_MS", 2500),
    )


def _mongo_database_from_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    path = urlparse(uri).path.strip("/")
    return unquote(path.split("/", 1)[0]) if path else None


def _postgres_ssl_mode(database_url: str) -> str | None:
    values = parse_qs(urlsplit(database_url).query).get("sslmode", [])
    return values[-1].casefold() if values else None


def _secure_mongo_uri(uri: str | None) -> str | None:
    if not uri or not _is_production():
        return uri
    parsed = urlsplit(uri)
    query = parse_qs(parsed.query)
    tls_values = [value.casefold() for key in ("tls", "ssl") for value in query.get(key, [])]
    if any(value in {"0", "false", "no", "off"} for value in tls_values):
        raise RuntimeError("MONGO_URI cannot disable TLS in production.")
    if parsed.scheme == "mongodb" and not tls_values:
        separator = "&" if parsed.query else ""
        parsed = parsed._replace(query=f"{parsed.query}{separator}tls=true")
        return urlunsplit(parsed)
    return uri
