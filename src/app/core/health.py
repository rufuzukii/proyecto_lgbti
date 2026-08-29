from __future__ import annotations

from typing import Literal, TypedDict

from flask import Flask, jsonify

from app.infrastructure.cache import local_cache_health_status

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
    """Return a liveness report without querying PostgreSQL, MongoDB or Supabase."""
    cache_status = _as_service_status(local_cache_health_status())
    services: dict[str, ServiceStatus] = {
        "application": "ok",
        "local_cache": cache_status,
    }
    status: ServiceStatus = "ok" if cache_status == "ok" else "degraded"
    return {"status": status, "services": services}


def _as_service_status(value: str) -> ServiceStatus:
    if value == "ok":
        return "ok"
    if value == "degraded":
        return "degraded"
    return "unavailable"
