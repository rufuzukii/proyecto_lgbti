from __future__ import annotations

from typing import Any

from app.analytics.combined_analysis import infer_indicator_semantics
from app.analytics.statistics_normalizers import normalize_text_key
from app.reports.models import ReportRecommendation

WORKPLACE_TERMS = {
    "work", "workplace", "employment", "job", "labour", "laboral", "empleo",
    "promotion", "promocion", "recruitment", "seleccion", "colleague", "compañer",
}
DISCRIMINATION_TERMS = {
    "discrimin", "harass", "acoso", "violence", "violencia", "hate", "odio",
    "unsafe", "insegur", "bully", "intimid", "attack", "agres",
}
LEGAL_TERMS = {"legal", "law", "rights", "derecho", "legisl", "protect", "proteccion"}


def _pair(es: tuple[str, ...], en: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    return {"es": es, "en": en}


# Central, reviewable catalogue. Entries are general orientations, never
# individual legal, medical or clinical advice.
RECOMMENDATION_RULES: dict[str, dict[str, dict[str, tuple[str, ...]]]] = {
    "comun": {
        "adverse": _pair(
            (
                "Consultar las fuentes oficiales y recursos especializados para comprender mejor el contexto del indicador.",
                "Comparar el resultado con otros países y segmentos antes de extraer una conclusión general.",
            ),
            (
                "Consult official sources and specialist resources to better understand the indicator's context.",
                "Compare the result with other countries and groups before drawing a general conclusion.",
            ),
        ),
        "general": _pair(
            ("Utilizar el informe como punto de partida y revisar las limitaciones antes de comunicar sus resultados.",),
            ("Use the report as a starting point and review its limitations before communicating the results.",),
        ),
    },
    "docente": {
        "adverse": _pair(
            (
                "Plantear una actividad para identificar qué factores sociales pueden influir en el resultado sin asumir una única causa.",
                "Comparar dos países y pedir al alumnado que diferencie datos, interpretación y opinión.",
            ),
            (
                "Use an activity to identify social factors that may influence the result without assuming a single cause.",
                "Compare two countries and ask students to distinguish data, interpretation and opinion.",
            ),
        ),
        "general": _pair(
            ("Incorporar una pregunta de reflexión sobre las limitaciones y la población representada por la encuesta.",),
            ("Include a reflection question about limitations and the population represented by the survey.",),
        ),
    },
    "rrhh": {
        "adverse": _pair(
            (
                "Considerar el refuerzo de protocolos frente a la discriminación y de canales confidenciales de comunicación.",
                "Valorar formación preventiva en diversidad e inclusión para equipos y responsables de personas.",
                "Realizar seguimiento periódico del clima laboral mediante mecanismos anónimos que protejan la privacidad.",
            ),
            (
                "Consider strengthening anti-discrimination procedures and confidential communication channels.",
                "Consider preventive diversity and inclusion training for teams and people managers.",
                "Monitor workplace climate periodically through anonymous, privacy-preserving mechanisms.",
            ),
        ),
        "general": _pair(
            (
                "Revisar periódicamente las políticas internas de inclusión, el lenguaje y los procesos de gestión de personas.",
                "Tratar estos datos como contexto europeo: no describen automáticamente la situación interna de una organización concreta.",
            ),
            (
                "Periodically review internal inclusion policies, language and people-management processes.",
                "Treat these data as European context: they do not automatically describe a specific organisation's internal situation.",
            ),
        ),
    },
    "ong": {
        "adverse": _pair(
            (
                "Considerar campañas de sensibilización y apoyo comunitario centradas en la brecha observada.",
                "Documentar la evolución del indicador y colaborar con instituciones y organizaciones especializadas.",
                "Utilizar la evidencia como apoyo para la incidencia, explicando siempre su alcance y limitaciones.",
            ),
            (
                "Consider awareness and community-support initiatives focused on the observed gap.",
                "Document the indicator over time and collaborate with institutions and specialist organisations.",
                "Use the evidence to support advocacy while always explaining its scope and limitations.",
            ),
        ),
        "general": _pair(
            ("Mantener el seguimiento de los grupos y territorios con menor disponibilidad de información.",),
            ("Continue monitoring groups and territories with lower data availability.",),
        ),
    },
    "politico": {
        "adverse": _pair(
            (
                "Considerar medidas públicas de prevención, sensibilización y formación institucional relacionadas con la brecha observada.",
                "Reforzar la recopilación de datos y el seguimiento periódico antes de evaluar nuevas actuaciones.",
                "Valorar la colaboración con organizaciones sociales y organismos de igualdad.",
            ),
            (
                "Consider public prevention, awareness and institutional training measures related to the observed gap.",
                "Strengthen data collection and periodic monitoring before evaluating new actions.",
                "Consider collaboration with civil-society organisations and equality bodies.",
            ),
        ),
        "general": _pair(
            ("Contrastar el resultado con otras fuentes y con el marco territorial antes de priorizar una política pública.",),
            ("Compare the result with other sources and territorial context before prioritising public policy.",),
        ),
    },
    "sociologo": {
        "adverse": _pair(
            (
                "Profundizar en la heterogeneidad entre países y segmentos mediante análisis descriptivos comparables.",
                "Examinar hipótesis alternativas y posibles factores de confusión sin atribuir causalidad a la asociación observada.",
            ),
            (
                "Explore heterogeneity across countries and groups through comparable descriptive analysis.",
                "Examine alternative hypotheses and potential confounders without assigning causality to the observed association.",
            ),
        ),
        "general": _pair(
            ("Documentar la disponibilidad, los cambios de cuestionario y las decisiones de comparabilidad en cualquier análisis posterior.",),
            ("Document availability, questionnaire changes and comparability decisions in any follow-up analysis.",),
        ),
    },
    "admin": {
        "adverse": _pair(
            ("Revisar la cobertura y trazabilidad del indicador antes de publicar o reutilizar el informe.",),
            ("Review indicator coverage and traceability before publishing or reusing the report.",),
        ),
        "general": _pair(
            ("Previsualizar la plantilla del perfil destinatario y comprobar sus atribuciones y limitaciones.",),
            ("Preview the intended audience template and verify its attributions and limitations.",),
        ),
    },
}
RECOMMENDATION_RULES["anonymous"] = RECOMMENDATION_RULES["comun"]


def indicator_semantics(indicator: str, answer: str = "", *, source: str = "fra") -> str:
    if source == "ilga":
        return "favourable"
    return infer_indicator_semantics(indicator, answer).get("direction", "unknown")


def indicator_direction(indicator: str, answer: str = "") -> str:
    """Backward-compatible polarity label used by older callers and tests."""
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
    is_adverse = (semantics == "adverse" and gap > 0) or (
        semantics == "favourable" and gap < 0
    )
    return "adverse" if is_adverse else "favourable"


def build_recommendations(
    *,
    indicator: str,
    country_value: float | None,
    eu_average: float | None = None,
    benchmark: float | None = None,
    language: str,
    profile_key: str = "rrhh",
    objective: str = "overview",
    answer: str = "",
    source: str = "fra",
    threshold: float = 5.0,
    **_unused: Any,
) -> list[ReportRecommendation]:
    del objective  # Objective selection affects report structure; evidence rules stay stable.
    reference = benchmark if benchmark is not None else eu_average
    semantics = indicator_semantics(indicator, answer, source=source)
    level = result_level(
        semantics=semantics,
        country_value=country_value,
        benchmark=reference,
        threshold=threshold,
    )
    profile_rules = RECOMMENDATION_RULES.get(profile_key, RECOMMENDATION_RULES["comun"])
    language_key = "en" if language == "en" else "es"
    recommendations: list[ReportRecommendation] = []
    if level == "adverse":
        recommendations.extend(
            ReportRecommendation(text, True)
            for text in profile_rules["adverse"][language_key]
        )
    recommendations.extend(
        ReportRecommendation(text, False)
        for text in profile_rules["general"][language_key]
    )
    return list(dict.fromkeys(recommendations))[:6]
