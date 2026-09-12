from __future__ import annotations

from typing import Any

from app.modules.reports.models import ReportRecommendation
from app.modules.statistics.combined_analysis import infer_indicator_semantics
from app.shared.data.normalization import normalize_text_key

WORKPLACE_TERMS = {
    "work",
    "workplace",
    "employment",
    "job",
    "labour",
    "laboral",
    "empleo",
    "promotion",
    "promocion",
    "recruitment",
    "seleccion",
    "colleague",
    "compañer",
}
DISCRIMINATION_TERMS = {
    "discrimin",
    "harass",
    "acoso",
    "violence",
    "violencia",
    "hate",
    "odio",
    "unsafe",
    "insegur",
    "bully",
    "intimid",
    "attack",
    "agres",
}
LEGAL_TERMS = {"legal", "law", "rights", "derecho", "legisl", "protect", "proteccion"}


def _pair(es: tuple[str, ...], en: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    return {"es": es, "en": en}


# Catálogo central revisable. Son orientaciones generales, sin asesoramiento
# jurídico, médico ni clínico individual.
HR_RECOMMENDATION_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "adverse": _pair(
        (
            "Considerar el refuerzo de protocolos frente a la discriminación y de canales confidenciales de comunicación.",
            "Valorar formación preventiva en diversidad e inclusión para equipos y responsables de personas.",
            "Realizar seguimiento periódico del clima laboral mediante mecanismos anónimos que protejan la privacidad.",
            "Revisar que las políticas de igualdad, beneficios y medidas de apoyo incluyan expresamente a las personas LGBTIQ+.",
        ),
        (
            "Consider strengthening anti-discrimination procedures and confidential communication channels.",
            "Consider preventive diversity and inclusion training for teams and people managers.",
            "Monitor workplace climate periodically through anonymous, privacy-preserving mechanisms.",
            "Review whether equality policies, benefits and support measures explicitly include LGBTIQ+ people.",
        ),
    ),
    "general": _pair(
        (
            "Revisar periódicamente las políticas internas de inclusión, el lenguaje y los procesos de gestión de personas.",
            "Tratar estos datos como contexto europeo: no describen automáticamente la situación interna de una organización concreta.",
            "Considerar redes internas de apoyo y mecanismos periódicos para evaluar la inclusión laboral.",
        ),
        (
            "Periodically review internal inclusion policies, language and people-management processes.",
            "Treat these data as European context: they do not automatically describe a specific organisation's internal situation.",
            "Consider internal support networks and periodic mechanisms for assessing workplace inclusion.",
        ),
    ),
}


def indicator_semantics(indicator: str, answer: str = "", *, source: str = "fra") -> str:
    if source == "ilga":
        return "favourable"
    return infer_indicator_semantics(indicator, answer).get("direction", "unknown")


def indicator_direction(indicator: str, answer: str = "") -> str:
    """Etiqueta de polaridad compatible con consumidores y pruebas anteriores."""
    direction = indicator_semantics(indicator, answer)
    return {"adverse": "negative", "favourable": "positive"}.get(direction, "neutral")


def is_hr_relevant_indicator(indicator: str) -> bool:
    normalized = normalize_text_key(indicator)
    return any(term in normalized for term in WORKPLACE_TERMS | DISCRIMINATION_TERMS)


def indicator_topic(indicator: str) -> str:
    normalized = normalize_text_key(indicator)
    if any(term in normalized for term in WORKPLACE_TERMS):
        return "workplace"
    if any(term in normalized for term in DISCRIMINATION_TERMS):
        return "discrimination"
    if any(term in normalized for term in LEGAL_TERMS):
        return "legal"
    return "general"


def result_level(
    *,
    semantics: str,
    country_value: float | None,
    benchmark: float | None,
    threshold: float = 5.0,
) -> str:
    if country_value is None or benchmark is None:
        return "unknown"
    gap = country_value - benchmark
    if abs(gap) < threshold or semantics == "unknown":
        return "neutral"
    is_adverse = (semantics == "adverse" and gap > 0) or (semantics == "favourable" and gap < 0)
    return "adverse" if is_adverse else "favourable"


def build_recommendations(
    *,
    indicator: str,
    country_value: float | None,
    eu_average: float | None = None,
    benchmark: float | None = None,
    language: str,
    answer: str = "",
    source: str = "fra",
    threshold: float = 5.0,
    **_unused: Any,
) -> list[ReportRecommendation]:
    reference = benchmark if benchmark is not None else eu_average
    semantics = indicator_semantics(indicator, answer, source=source)
    level = result_level(
        semantics=semantics,
        country_value=country_value,
        benchmark=reference,
        threshold=threshold,
    )
    language_key = "en" if language == "en" else "es"
    recommendations: list[ReportRecommendation] = []
    if level == "adverse":
        recommendations.extend(
            ReportRecommendation(text, True)
            for text in HR_RECOMMENDATION_RULES["adverse"][language_key]
        )
    recommendations.extend(
        ReportRecommendation(text, False)
        for text in HR_RECOMMENDATION_RULES["general"][language_key]
    )
    return list(dict.fromkeys(recommendations))[:6]
