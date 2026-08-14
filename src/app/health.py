from __future__ import annotations

from typing import Literal, TypedDict

import psycopg
from flask import Flask, jsonify
from pymongo.errors import PyMongoError

from app.cache import redis_health_status
from app.config import (
    get_app_config,
    get_mongo_config,
    get_postgres_dsn,
)
from app.mongo import get_mongo_client
from app.postgres import postgres_connection

ServiceStatus = Literal["ok", "degraded", "unavailable"]


class HealthReport(TypedDict):
    status: ServiceStatus
    services: dict[str, ServiceStatus]


def register_health_endpoint(app: Flask) -> None:
    @app.get("/health")
    def health():
        report = build_health_report()
        http_status = 503 if report["status"] == "unavailable" else 200
        return jsonify(report), http_status


def build_health_report() -> HealthReport:
    configuration = _configuration_status()
    services: dict[str, ServiceStatus] = {
        "application": "ok",
        "postgresql": _postgresql_status(),
        "mongodb": _mongodb_status(),
        "redis": _as_service_status(redis_health_status()),
        "configuration": configuration,
    }
    required = (services["postgresql"], services["mongodb"], configuration)
    if "unavailable" in required:
        status: ServiceStatus = "unavailable"
    elif any(value != "ok" for value in services.values()):
        status = "degraded"
    else:
        status = "ok"
    return {"status": status, "services": services}


def _configuration_status() -> ServiceStatus:
    try:
        get_app_config()
        get_postgres_dsn()
        get_mongo_config()
    except (RuntimeError, TypeError, ValueError):
        return "unavailable"
    return "ok"


def _postgresql_status() -> ServiceStatus:
    try:
        with postgres_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return "ok"
    except (psycopg.Error, OSError, RuntimeError, TypeError, ValueError):
        return "unavailable"


def _mongodb_status() -> ServiceStatus:
    try:
        result = get_mongo_client().admin.command("ping")
        return "ok" if result.get("ok") == 1 else "unavailable"
    except (PyMongoError, OSError, RuntimeError, TypeError, ValueError):
        return "unavailable"


def _as_service_status(value: str) -> ServiceStatus:
    if value == "ok":
        return "ok"
    if value == "degraded":
        return "degraded"
    return "unavailable"
