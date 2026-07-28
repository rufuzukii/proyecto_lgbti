from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.config import get_app_config, get_mongo_config, get_postgres_config, get_postgres_dsn


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
    assert cfg.secret_key == "local-dev-secret-key"
    assert cfg.debug is True


def test_get_app_config_requires_secret_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOCAL_MODE", "false")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        get_app_config()


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

