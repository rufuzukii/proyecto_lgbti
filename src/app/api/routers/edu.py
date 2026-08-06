from fastapi import APIRouter
from pydantic import BaseModel

from app.edu.content import list_learning_units

router = APIRouter(prefix="/edu", tags=["edu"])


class LocalizedText(BaseModel):
    es: str
    en: str


class LearningUnitResponse(BaseModel):
    id: str
    title: LocalizedText
    description: LocalizedText
    duration_minutes: int


@router.get("/units")
def list_units() -> list[LearningUnitResponse]:
    return [LearningUnitResponse.model_validate(unit) for unit in list_learning_units()]
