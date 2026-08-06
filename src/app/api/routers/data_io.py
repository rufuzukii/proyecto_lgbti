import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.import_to_db import (
    generate_fra_json,
    parse_ilga_csv,
    register_pending_import,
)

router = APIRouter(prefix="/data", tags=["data"])
logger = logging.getLogger(__name__)
IMPORT_BASE_DIR = Path(os.getenv("IMPORT_BASE_DIR", "data/imports")).resolve()


class MongoJsonImportRequest(BaseModel):
    rainbow_csv: str | None = Field(default=None)
    discrimination_dir: str | None = Field(default=None)
    year: int = Field(default=2026, ge=1990, le=2100)


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


@router.post("/import", status_code=status.HTTP_202_ACCEPTED)
def import_data(request: MongoJsonImportRequest) -> dict[str, object]:
    discrimination_dir = _safe_import_path(request.discrimination_dir, expect_dir=True)
    rainbow_csv = _safe_import_path(request.rainbow_csv, expect_dir=False)

    if request.discrimination_dir and discrimination_dir is None:
        raise HTTPException(status_code=400, detail="invalid_import_directory")
    if request.rainbow_csv and rainbow_csv is None:
        raise HTTPException(status_code=400, detail="invalid_import_csv")
    if not discrimination_dir and not rainbow_csv:
        raise HTTPException(status_code=400, detail="import_source_required")

    try:
        results = []
        if discrimination_dir:
            results.extend(generate_fra_json(str(discrimination_dir)))
        if rainbow_csv:
            results.append(
                (
                    rainbow_csv,
                    [parse_ilga_csv(rainbow_csv, year=request.year)],
                )
            )
        if not results or any(not data for _, data in results):
            raise HTTPException(status_code=422, detail="no_import_records")
        for path, data in results:
            register_pending_import(file_name=str(path), file_json=data)
    except HTTPException:
        raise
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("api_import_validation_failed", exc_info=exc)
        raise HTTPException(status_code=422, detail="invalid_import_source") from exc
    except Exception:
        logger.exception("api_import_registration_failed")
        raise HTTPException(status_code=503, detail="import_queue_unavailable") from None

    return {
        "status": "pending_review",
        "sources": [Path(path).name for path, _ in results],
        "queued": len(results),
    }
