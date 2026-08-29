import pytest

from app.core.config import (
    get_app_config,
    get_mongo_config,
    get_postgres_config,
    get_postgres_dsn,
)


def test_get_postgres_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    monkeypatch.delenv("POSTGRES_PORT", raising=False)
    monkeypatch.delenv("POSTGRES_DB", raising=False)
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    cfg = get_postgres_config()
    assert cfg.host == "localhost"
    assert cfg.port == 5432
    assert cfg.database == "proyecto_lgbti_relacional"
    assert cfg.user == "postgres"
    assert cfg.password == ""


def test_get_app_config_local_default_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_MODE", "true")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    cfg = get_app_config()
    assert len(cfg.secret_key) >= 32
    assert cfg.secret_key == get_app_config().secret_key
    assert cfg.debug is True


def test_get_app_config_requires_secret_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOCAL_MODE", "false")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        get_app_config()


def test_config_representations_do_not_expose_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_MODE", "true")
    monkeypatch.setenv("SECRET_KEY", "secret-key-value")
    monkeypatch.setenv("POSTGRES_PASSWORD", "database-password")
    monkeypatch.setenv("MONGO_URI", "mongodb://user:mongo-password@localhost/app")

    assert "secret-key-value" not in repr(get_app_config())
    assert "database-password" not in repr(get_postgres_config())
    assert "mongo-password" not in repr(get_mongo_config())


def test_production_database_urls_require_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOCAL_MODE", "false")
    monkeypatch.setenv("SECRET_KEY", "s" * 32)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@example.net/app?sslmode=disable",
    )
    with pytest.raises(RuntimeError, match="require TLS"):
        get_postgres_dsn()

    monkeypatch.setenv("MONGO_URI", "mongodb://user:password@example.net/app?tls=false")
    with pytest.raises(RuntimeError, match="cannot disable TLS"):
        get_mongo_config()


def test_production_mongo_uri_enables_tls_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOCAL_MODE", "false")
    monkeypatch.setenv("SECRET_KEY", "s" * 32)
    monkeypatch.setenv("MONGO_URI", "mongodb://user:password@example.net/app")

    assert get_mongo_config().uri == "mongodb://user:password@example.net/app?tls=true"


def test_get_postgres_dsn_requires_database_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOCAL_MODE", "false")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        get_postgres_dsn()


def test_get_mongo_config_reads_database_from_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONGO_DB", raising=False)
    monkeypatch.setenv("MONGO_URI", "mongodb+srv://user:pass@example.net/rainbow_data")

    cfg = get_mongo_config()

    assert cfg.database == "rainbow_data"
