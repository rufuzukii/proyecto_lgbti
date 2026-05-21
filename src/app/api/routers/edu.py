from fastapi import APIRouter

router = APIRouter(prefix="/edu", tags=["edu"])


@router.get("/units")
def list_units() -> list[dict]:
    return []

