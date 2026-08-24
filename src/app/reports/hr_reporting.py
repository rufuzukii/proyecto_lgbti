from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HrReportObjective:
    id: str
    label_es: str
    label_en: str
    description_es: str
    description_en: str

    def label(self, language: str) -> str:
        return self.label_en if language == "en" else self.label_es

    def description(self, language: str) -> str:
        return self.description_en if language == "en" else self.description_es


HR_REPORT_OBJECTIVES: tuple[HrReportObjective, ...] = (
    HrReportObjective(
        "inclusion_context",
        "Evaluar el contexto de inclusión",
        "Assess the inclusion context",
        "Resume el contexto social y los principales resultados disponibles.",
        "Summarises the social context and the main available results.",
    ),
    HrReportObjective(
        "discrimination",
        "Analizar discriminación",
        "Analyse discrimination",
        "Prioriza indicadores relacionados con discriminación, acoso y trato desigual.",
        "Prioritises indicators related to discrimination, harassment and unequal treatment.",
    ),
    HrReportObjective(
        "visibility_safety",
        "Analizar visibilidad y seguridad",
        "Analyse visibility and safety",
        "Ayuda a interpretar indicadores de apertura, seguridad y bienestar.",
        "Helps interpret indicators about openness, safety and wellbeing.",
    ),
    HrReportObjective(
        "country_comparison",
        "Comparar países",
        "Compare countries",
        "Compara el contexto del país principal con otros países europeos.",
        "Compares the main country's context with other European countries.",
    ),
    HrReportObjective(
        "legal_context",
        "Comprender el contexto legal",
        "Understand the legal context",
        "Incorpora la protección legal como contexto externo para diversidad e inclusión.",
        "Adds legal protection as external context for diversity and inclusion.",
    ),
    HrReportObjective(
        "action_areas",
        "Identificar posibles áreas de actuación",
        "Identify possible action areas",
        "Relaciona los resultados con orientaciones generales y verificables para RRHH.",
        "Links results to general, verifiable guidance for HR teams.",
    ),
)

DEFAULT_HR_OBJECTIVE = "inclusion_context"
HR_REPORT_SECTIONS: tuple[str, ...] = (
    "executive",
    "context",
    "metrics",
    "analysis",
    "workplace",
    "comparison",
    "demographics",
    "interpretation",
    "recommendations",
    "methodology",
    "limitations",
    "sources",
)


def hr_report_objective(value: str | None) -> HrReportObjective:
    return next(
        (objective for objective in HR_REPORT_OBJECTIVES if objective.id == value),
        HR_REPORT_OBJECTIVES[0],
    )


def hr_report_charts(source: str, objective: str | None) -> tuple[str, ...]:
    selected = hr_report_objective(objective).id
    if source == "combined":
        mapping = {
            "legal_context": ("scatter", "quadrants", "ranking_gap"),
            "country_comparison": ("scatter", "ranking_gap"),
            "action_areas": ("scatter", "quadrants", "ranking_gap"),
        }
        return mapping.get(selected, ("scatter", "ranking_gap"))
    if source == "ilga":
        return ("ranking", "average", "countries", "temporal")
    mapping = {
        "country_comparison": ("ranking", "average", "countries"),
        "visibility_safety": ("average", "countries", "responses"),
    }
    return mapping.get(selected, ("ranking", "average", "countries", "responses"))


def hr_report_focus_label(language: str) -> str:
    return "HR / Diversity and inclusion" if language == "en" else "RRHH / Diversidad e inclusión"
