from fastapi import Depends, FastAPI

from app.api.routers import charts, data_io, edu, reports, users
from app.api.security import require_api_key


def create_api_app() -> FastAPI:
    app = FastAPI(title="RainbowLens API", version="0.1.0")

    protected = [Depends(require_api_key)]
    app.include_router(users.router, dependencies=protected)
    app.include_router(data_io.router, dependencies=protected)
    app.include_router(charts.router, dependencies=protected)
    app.include_router(reports.router, dependencies=protected)
    app.include_router(edu.router, dependencies=protected)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_api_app()

