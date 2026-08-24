from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.reports.hr_reporting import (
    HR_REPORT_SECTIONS,
    hr_report_charts,
    hr_report_objective,
)
from app.reports.models import ReportConfiguration
from app.reports.service import ReportGenerationError, generate_report_pdf

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportRequest(BaseModel):
    source: Literal["fra", "ilga", "combined"] = "fra"
    objective: str = Field(default="inclusion_context", max_length=80)
    category: str = Field(default="", max_length=180)
    indicator_id: str = Field(default="", max_length=120)
    indicator_label: str = Field(default="", max_length=240)
    answer: str = Field(default="", max_length=120)
    criterion: str = Field(default="", max_length=240)
    year: int | None = Field(default=None, ge=1900, le=2200)
    countries: list[str] = Field(default_factory=list, max_length=49)
    primary_country: str = Field(default="", max_length=3)
    filter_a_name: str = Field(default="All", max_length=120)
    filter_a_value: str = Field(default="All", max_length=160)
    filter_b_name: str = Field(default="All", max_length=120)
    filter_b_value: str = Field(default="All", max_length=160)
    title: str = Field(default="", max_length=180)
    organization: str = Field(default="", max_length=120)
    author: str = Field(default="", max_length=120)
    language: Literal["es", "en"] = "es"

    def to_configuration(self) -> ReportConfiguration:
        objective = hr_report_objective(self.objective)
        return ReportConfiguration.from_mapping(
            {
                **self.model_dump(),
                "objective": objective.id,
                "sections": HR_REPORT_SECTIONS,
                "charts": hr_report_charts(self.source, objective.id),
            }
        )


@router.post("", response_class=Response)
def build_report(request: ReportRequest) -> Response:
    try:
        generated = generate_report_pdf(request.to_configuration())
    except ReportGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="report_generation_failed",
        ) from exc
    return Response(
        content=generated.pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{generated.filename}"'},
    )
