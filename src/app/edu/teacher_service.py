from __future__ import annotations

import re
from functools import lru_cache
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, Paragraph, SimpleDocTemplate, Spacer

from app.edu.models import TeacherResource
from app.edu.repository import load_json
from app.source_attribution import source_metadata


@lru_cache(maxsize=1)
def list_teacher_resources() -> tuple[TeacherResource, ...]:
    return tuple(TeacherResource.from_mapping(item) for item in load_json("teacher_resources"))


def get_teacher_resource(resource_id: str) -> TeacherResource | None:
    return next((item for item in list_teacher_resources() if item.id == resource_id), None)


def generate_teacher_resource_pdf(resource_id: str, language: str) -> tuple[bytes, str]:
    resource = get_teacher_resource(resource_id)
    if resource is None:
        raise ValueError("resource_not_found")
    language = "en" if language == "en" else "es"
    position = 1 if language == "en" else 0
    labels = {
        "level": ("Nivel", "Level"),
        "duration": ("Duración", "Duration"),
        "objectives": ("Objetivos", "Objectives"),
        "instructions": ("Instrucciones", "Instructions"),
        "materials": ("Materiales", "Materials"),
        "guide": ("Guía docente", "Teacher guide"),
        "minutes": ("minutos", "minutes"),
        "sources": ("Fuentes, metodología y atribuciones", "Sources, methodology and attributions"),
    }
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=resource.title.get(language),
        author="RainbowLens Datahub",
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph(resource.title.get(language), styles["Title"]),
        Paragraph(resource.description.get(language), styles["BodyText"]),
        Spacer(1, 8),
        Paragraph(
            f"<b>{labels['level'][position]}:</b> {resource.level.get(language)}",
            styles["BodyText"],
        ),
        Paragraph(
            f"<b>{labels['duration'][position]}:</b> {resource.duration_minutes} {labels['minutes'][position]}",
            styles["BodyText"],
        ),
        Spacer(1, 8),
        Paragraph(labels["objectives"][position], styles["Heading2"]),
        ListFlowable(
            [Paragraph(item.get(language), styles["BodyText"]) for item in resource.objectives]
        ),
        Paragraph(labels["instructions"][position], styles["Heading2"]),
        Paragraph(resource.instructions.get(language), styles["BodyText"]),
        Paragraph(labels["materials"][position], styles["Heading2"]),
        ListFlowable(
            [Paragraph(item.get(language), styles["BodyText"]) for item in resource.materials]
        ),
        Paragraph(labels["guide"][position], styles["Heading2"]),
        Paragraph(resource.teacher_guide.get(language), styles["BodyText"]),
    ]
    source_keys = _resource_source_keys(resource)
    if source_keys:
        story.extend(
            [
                Paragraph(labels["sources"][position], styles["Heading2"]),
                *[
                    Paragraph(
                        source_metadata(source).attribution(language),
                        styles["BodyText"],
                    )
                    for source in source_keys
                ],
                *[
                    Paragraph(source_metadata(source).source_url, styles["BodyText"])
                    for source in source_keys
                ],
            ]
        )
    document.build(story)
    safe_id = re.sub(r"[^a-z0-9_-]+", "-", resource.id.casefold()).strip("-")
    return output.getvalue(), f"rainbowlens-datahub-{safe_id}-{language}.pdf"


def _resource_source_keys(resource: TeacherResource) -> list[str]:
    searchable = " ".join(
        [
            resource.title.es,
            resource.title.en,
            resource.description.es,
            resource.description.en,
            resource.instructions.es,
            resource.instructions.en,
            resource.teacher_guide.es,
            resource.teacher_guide.en,
            *(item.es for item in resource.materials),
            *(item.en for item in resource.materials),
        ]
    ).casefold()
    return [source for source in ("fra", "ilga", "felgtbi") if source in searchable]
