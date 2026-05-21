from fastapi import FastAPI

from app.api.routers import charts, data_io, edu, reports, users

app = FastAPI(title="LGBTIQ+ API", version="0.1.0")

app.include_router(users.router)
app.include_router(data_io.router)
app.include_router(charts.router)
app.include_router(reports.router)
app.include_router(edu.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

