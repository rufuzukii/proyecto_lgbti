from __future__ import annotations

from app.analytics.statistics_normalizers import normalize_text_key
from app.reports.models import ReportRecommendation


NEGATIVE_INDICATOR_TERMS = {
    "discrimination",
    "discriminacion",
    "discriminación",
    "harassment",
    "acoso",
    "violence",
    "violencia",
    "unsafe",
    "inseguro",
    "insegura",
    "bullying",
    "intimidacion",
    "intimidación",
}

POSITIVE_INDICATOR_TERMS = {
    "openness",
    "apertura",
    "inclusion",
    "inclusion",
    "inclusión",
    "wellbeing",
    "bienestar",
    "confidence",
    "confianza",
    "safety",
    "seguridad",
    "equal opportunities",
    "igualdad de oportunidades",
}

HR_RELEVANT_TERMS = NEGATIVE_INDICATOR_TERMS | POSITIVE_INDICATOR_TERMS | {
    "work",
    "workplace",
    "employment",
    "empleo",
    "laboral",
    "job",
    "denuncia",
    "reporting",
    "promotion",
    "promocion",
    "promoción",
    "recruitment",
    "seleccion",
    "selección",
}


def is_hr_relevant_indicator(indicator: str) -> bool:
    normalized = normalize_text_key(indicator)
    return any(term in normalized for term in HR_RELEVANT_TERMS)


def indicator_direction(indicator: str) -> str:
    normalized = normalize_text_key(indicator)
    if any(term in normalized for term in NEGATIVE_INDICATOR_TERMS):
        return "negative"
    if any(term in normalized for term in POSITIVE_INDICATOR_TERMS):
        return "positive"
    return "neutral"


def build_recommendations(
    *,
    indicator: str,
    country_value: float | None,
    eu_average: float | None,
    language: str,
    threshold: float = 5.0,
) -> list[ReportRecommendation]:
    direction = indicator_direction(indicator)
    relevant = is_hr_relevant_indicator(indicator)
    recommendations: list[ReportRecommendation] = []
    gap = (
        country_value - eu_average
        if country_value is not None and eu_average is not None
        else None
    )

    if relevant and gap is not None:
        if direction == "negative" and gap > threshold:
            recommendations.extend(
                _derived_negative_recommendations(language)
            )
        elif direction == "positive" and gap < -threshold:
            recommendations.extend(
                _derived_positive_recommendations(language)
            )

    recommendations.extend(_general_recommendations(language))
    deduplicated: list[ReportRecommendation] = []
    for item in recommendations:
        if item.text not in {current.text for current in deduplicated}:
            deduplicated.append(item)
    return deduplicated[:6]


def _derived_negative_recommendations(language: str) -> list[ReportRecommendation]:
    texts = (
        [
            "Review and reinforce internal prevention and response protocols for LGBTIQ+ discrimination.",
            "Provide confidential reporting channels with clear response times and safeguards against retaliation.",
            "Deliver recurring diversity training for managers, recruitment teams and people managers.",
        ]
        if language == "en"
        else [
            "Revisar y reforzar los protocolos internos de prevención y actuación frente a la discriminación LGTBIQ+.",
            "Habilitar canales confidenciales de denuncia con plazos de respuesta y garantías frente a represalias.",
            "Realizar formación periódica en diversidad para responsables, selección y gestión de personas.",
        ]
    )
    return [ReportRecommendation(text, True) for text in texts]


def _derived_positive_recommendations(language: str) -> list[ReportRecommendation]:
    texts = (
        [
            "Measure workplace inclusion periodically and analyse differences between demographic groups.",
            "Review recruitment, promotion and internal communication for barriers to equal opportunity.",
            "Strengthen employee support networks and visible leadership commitment to LGBTIQ+ inclusion.",
        ]
        if language == "en"
        else [
            "Medir periódicamente la inclusión laboral y analizar diferencias entre grupos sociodemográficos.",
            "Revisar selección, promoción y comunicación interna para detectar barreras a la igualdad de oportunidades.",
            "Reforzar las redes internas de apoyo y el compromiso visible del liderazgo con la inclusión LGTBIQ+.",
        ]
    )
    return [ReportRecommendation(text, True) for text in texts]


def _general_recommendations(language: str) -> list[ReportRecommendation]:
    texts = (
        [
            "Maintain an updated LGBTIQ+ inclusion policy and communicate it to the whole organisation.",
            "Review gender-transition support protocols, inclusive language and people-management documentation.",
            "Track workplace climate regularly using anonymous, privacy-preserving measures.",
        ]
        if language == "en"
        else [
            "Mantener una política de inclusión LGTBIQ+ actualizada y comunicarla a toda la organización.",
            "Revisar los protocolos de transición de género, el lenguaje inclusivo y la documentación de gestión de personas.",
            "Medir periódicamente el clima laboral con mecanismos anónimos que preserven la privacidad.",
        ]
    )
    return [ReportRecommendation(text, False) for text in texts]
