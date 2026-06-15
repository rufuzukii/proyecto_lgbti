from fastapi import Depends, FastAPI

from app.api.routers import charts, data_io, edu, reports, users
from app.api.security import require_api_key

app = FastAPI(title="RainbowLens API", version="0.1.0")

app.include_router(users.router, dependencies=[Depends(require_api_key)])
app.include_router(data_io.router, dependencies=[Depends(require_api_key)])
app.include_router(charts.router, dependencies=[Depends(require_api_key)])
app.include_router(reports.router, dependencies=[Depends(require_api_key)])
app.include_router(edu.router, dependencies=[Depends(require_api_key)])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
