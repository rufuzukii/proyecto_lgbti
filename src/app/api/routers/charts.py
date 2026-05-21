from fastapi import APIRouter

router = APIRouter(prefix="/charts", tags=["charts"])


@router.get("/export")
def export_chart() -> dict:
    return {"status": "pending"}

