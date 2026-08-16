from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routers import edu, reports, users
from app.api.security import require_admin_api_key, require_api_key
from app.config import get_app_config
from app.health import build_health_report
from app.http_security import security_headers
from app.logging_config import configure_secure_logging


def create_api_app() -> FastAPI:
    configure_secure_logging()
    config = get_app_config()
    documentation_url = "/docs" if config.local_mode else None
    app = FastAPI(
        title="RainbowLens Datahub API",
        version="0.1.0",
        docs_url=documentation_url,
        redoc_url="/redoc" if config.local_mode else None,
        openapi_url="/openapi.json" if config.local_mode else None,
    )

    protected = [Depends(require_api_key)]
    admin_only = [Depends(require_admin_api_key)]
    app.include_router(users.router, dependencies=admin_only)
    app.include_router(reports.router, dependencies=protected)
    app.include_router(edu.router, dependencies=protected)

    @app.get("/health")
    def health() -> JSONResponse:
        report = build_health_report()
        http_status = 503 if report["status"] == "unavailable" else 200
        return JSONResponse(status_code=http_status, content=report)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _error):
        return JSONResponse(status_code=422, content={"detail": "invalid_request"})

    @app.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        for name, value in security_headers(production=not config.local_mode).items():
            response.headers.setdefault(name, value)
        return response

    return app


app = create_api_app()
