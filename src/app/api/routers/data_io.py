import logging
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.import_to_db import (
    generate_fra_json,
    parse_ilga_csv,
    register_pending_import,
)
from app.import_to_db.fra import upsert_indicators_from_json

router = APIRouter(prefix="/data", tags=["data"])
logger = logging.getLogger(__name__)
IMPORT_BASE_DIR = Path(os.getenv("IMPORT_BASE_DIR", "data/imports")).resolve()


class MongoJsonImportRequest(BaseModel):
    rainbow_csv: str | None = Field(default=None)
    discrimination_dir: str | None = Field(default=None)
    year: int = 2026
    import_to_mongo: bool = False


def _safe_import_path(raw: str | None, *, expect_dir: bool) -> Path | None:
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        return None
    resolved = (IMPORT_BASE_DIR / candidate).resolve()
    if IMPORT_BASE_DIR not in resolved.parents and resolved != IMPORT_BASE_DIR:
        return None
    if expect_dir and not resolved.is_dir():
        return None
    if not expect_dir and not resolved.is_file():
        return None
    return resolved


@router.post("/import")
def import_data(request: MongoJsonImportRequest | None = None) -> dict:
    request_payload = request or MongoJsonImportRequest()
    if request_payload.year < 1990 or request_payload.year > 2100:
        return {"status": "error", "message": "Anio fuera de rango."}

    discrimination_dir = _safe_import_path(
        request_payload.discrimination_dir, expect_dir=True
    )
    rainbow_csv = _safe_import_path(request_payload.rainbow_csv, expect_dir=False)

    if request_payload.discrimination_dir and discrimination_dir is None:
        return {"status": "error", "message": "Ruta de directorio no valida."}
    if request_payload.rainbow_csv and rainbow_csv is None:
        return {"status": "error", "message": "Ruta de CSV no valida."}

    results = []
    if discrimination_dir:
        results.extend(generate_fra_json(str(discrimination_dir)))
    if rainbow_csv:
        results.append(
            (
                rainbow_csv,
                [parse_ilga_csv(rainbow_csv, year=request_payload.year)],
            )
        )

    if not results:
        return {"status": "error", "message": "No se proporcionaron rutas de CSV."}

    try:
        for path, data in results:
            if data and data[0].get("source_type") == "EU_SURVEY":
                upsert_indicators_from_json(data)
            register_pending_import(file_name=str(path), file_json=data)
    except Exception:
        logger.exception("import_log_failed")
        return {"status": "error", "message": "No se pudo registrar la importacion."}

    return {
        "status": "ok",
        "sources": [str(path) for path, _ in results],
        "imported": False,
        "import_to_mongo": bool(request_payload.import_to_mongo),
    }


@router.get("/export")
def export_data() -> dict:
    return {"status": "pending"}
