from fastapi import APIRouter

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/")
def build_report() -> dict:
    return {
        "status": "available",
        "ui_paths": ["/informes", "/reports"],
        "format": "pdf",
    }
