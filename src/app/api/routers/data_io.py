from fastapi import APIRouter

router = APIRouter(prefix="/data", tags=["data"])


@router.post("/import")
def import_data() -> dict:
    return {"status": "pending"}


@router.get("/export")
def export_data() -> dict:
    return {"status": "pending"}

