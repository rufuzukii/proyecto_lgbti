from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.reports.models import DEFAULT_REPORT_CHARTS, DEFAULT_REPORT_SECTIONS
from app.users.schemas import UserRole, UserType


@dataclass(frozen=True, slots=True)
class ReportTemplate:
    id: str
    name_es: str
    name_en: str
    description_es: str
    description_en: str
    title_es: str
    title_en: str
    source: str
    detail_level: str
    sections: tuple[str, ...]
    charts: tuple[str, ...]

    def option(self, language: str) -> dict[str, str]:
        return {
            "label": self.name_en if language == "en" else self.name_es,
            "value": self.id,
        }

    def description(self, language: str) -> str:
        return self.description_en if language == "en" else self.description_es

    def defaults(self, language: str) -> dict[str, Any]:
        return {
            "template_id": self.id,
            "title": self.title_en if language == "en" else self.title_es,
            "source": self.source,
            "mode": "custom",
            "detail_level": self.detail_level,
            "sections": list(self.sections),
            "charts": list(self.charts),
        }


GENERAL_SECTIONS = DEFAULT_REPORT_SECTIONS
GENERAL_CHARTS = DEFAULT_REPORT_CHARTS
LEGAL_SECTIONS = (
    "executive",
    "methodology",
    "metrics",
    "comparison",
    "risks",
    "recommendations",
    "limitations",
    "sources",
)
RESEARCH_SECTIONS = (
    "executive",
    "methodology",
    "metrics",
    "comparison",
    "demographics",
    "limitations",
    "sources",
)


def _template(
    identifier: str,
    names: tuple[str, str],
    descriptions: tuple[str, str],
    titles: tuple[str, str],
    *,
    source: str,
    detail: str = "standard",
    sections: tuple[str, ...] = GENERAL_SECTIONS,
    charts: tuple[str, ...] = GENERAL_CHARTS,
) -> ReportTemplate:
    return ReportTemplate(
        id=identifier,
        name_es=names[0],
        name_en=names[1],
        description_es=descriptions[0],
        description_en=descriptions[1],
        title_es=titles[0],
        title_en=titles[1],
        source=source,
        detail_level=detail,
        sections=sections,
        charts=charts,
    )


PROFILE_TEMPLATES: dict[str, tuple[ReportTemplate, ...]] = {
    "anonymous": (
        _template(
            "public_europe_overview",
            ("Panorama europeo", "European overview"),
            (
                "Resumen público de la situación legal y comparación entre países.",
                "Public overview of the legal situation and comparison between countries.",
            ),
            ("Panorama europeo LGBTIQ+", "European LGBTIQ+ overview"),
            source="ilga",
            sections=LEGAL_SECTIONS,
            charts=("ranking", "average", "countries", "temporal"),
        ),
        _template(
            "public_experiences_overview",
            ("Experiencias y diversidad", "Experiences and diversity"),
            (
                "Informe descriptivo basado en los indicadores de encuesta FRA disponibles.",
                "Descriptive report based on the available FRA survey indicators.",
            ),
            ("Experiencias de la población LGBTIQ+", "LGBTIQ+ population experiences"),
            source="fra",
            sections=RESEARCH_SECTIONS,
            charts=("average", "countries", "responses", "radar"),
        ),
    ),
    "comun": (
        _template(
            "community_country_report",
            ("Informe ciudadano por país", "Citizen country report"),
            (
                "Síntesis accesible de protección legal, comparación y fuentes.",
                "Accessible summary of legal protection, comparison and sources.",
            ),
            ("Informe ciudadano sobre diversidad LGBTIQ+", "Citizen LGBTIQ+ diversity report"),
            source="ilga",
            sections=LEGAL_SECTIONS,
            charts=("ranking", "average", "countries", "temporal"),
        ),
        _template(
            "community_experiences",
            ("Experiencias sociales", "Social experiences"),
            (
                "Lectura descriptiva de las experiencias declaradas en FRA.",
                "Descriptive reading of experiences reported in FRA.",
            ),
            ("Experiencias sociales de la población LGBTIQ+", "LGBTIQ+ social experiences"),
            source="fra",
            sections=RESEARCH_SECTIONS,
            charts=("average", "countries", "responses", "radar"),
        ),
    ),
    "rrhh": (
        _template(
            "rrhh_workplace_diagnostic",
            ("Diagnóstico laboral", "Workplace diagnostic"),
            (
                "Indicadores de discriminación, entorno laboral, riesgos y recomendaciones.",
                "Indicators on discrimination, workplace climate, risks and recommendations.",
            ),
            (
                "Diagnóstico de diversidad y no discriminación laboral",
                "Workplace diversity and non-discrimination diagnostic",
            ),
            source="fra",
            detail="detailed",
            sections=(
                "executive",
                "methodology",
                "metrics",
                "workplace",
                "demographics",
                "risks",
                "recommendations",
                "limitations",
                "sources",
            ),
            charts=("average", "countries", "responses", "radar"),
        ),
        _template(
            "rrhh_compliance_context",
            ("Contexto legal para RRHH", "Legal context for HR"),
            (
                "Comparativa legal para contextualizar políticas internas de igualdad.",
                "Legal comparison to contextualise internal equality policies.",
            ),
            ("Contexto legal para políticas de diversidad", "Legal context for diversity policies"),
            source="ilga",
            sections=LEGAL_SECTIONS,
            charts=("ranking", "average", "countries", "temporal"),
        ),
    ),
    "docente": (
        _template(
            "teacher_classroom_brief",
            ("Dossier para el aula", "Classroom briefing"),
            (
                "Resumen explicativo con metodología, gráficos y fuentes para uso educativo.",
                "Explanatory summary with methodology, charts and sources for educational use.",
            ),
            (
                "Dossier educativo sobre diversidad LGBTIQ+",
                "Educational briefing on LGBTIQ+ diversity",
            ),
            source="ilga",
            sections=(
                "executive",
                "methodology",
                "metrics",
                "comparison",
                "limitations",
                "sources",
            ),
            charts=("ranking", "countries", "temporal"),
        ),
        _template(
            "teacher_experiences_activity",
            ("Datos para una actividad", "Data for a classroom activity"),
            (
                "Selección descriptiva de experiencias FRA para trabajar lectura crítica de datos.",
                "Descriptive FRA experience data for critical data literacy activities.",
            ),
            (
                "Actividad de lectura crítica de datos LGBTIQ+",
                "Critical reading activity with LGBTIQ+ data",
            ),
            source="fra",
            sections=RESEARCH_SECTIONS,
            charts=("average", "countries", "responses"),
        ),
    ),
    "politico": (
        _template(
            "policy_legal_brief",
            ("Informe de política pública", "Public policy brief"),
            (
                "Evolución del ranking legal, brechas comparadas y recomendaciones de política.",
                "Legal ranking evolution, comparative gaps and policy recommendations.",
            ),
            (
                "Informe de situación y política pública LGBTIQ+",
                "LGBTIQ+ situation and public policy brief",
            ),
            source="ilga",
            detail="detailed",
            sections=LEGAL_SECTIONS,
            charts=("ranking", "average", "countries", "temporal"),
        ),
        _template(
            "policy_social_evidence",
            ("Evidencia social para políticas", "Social evidence for policy"),
            (
                "Indicadores FRA para contextualizar necesidades y prioridades públicas.",
                "FRA indicators to contextualise public needs and priorities.",
            ),
            (
                "Evidencia social para políticas de igualdad",
                "Social evidence for equality policies",
            ),
            source="fra",
            detail="detailed",
            sections=(*RESEARCH_SECTIONS, "recommendations"),
            charts=("average", "countries", "responses", "radar"),
        ),
    ),
    "sociologo": (
        _template(
            "sociology_cross_section",
            ("Análisis sociológico transversal", "Cross-sectional sociological analysis"),
            (
                "Comparación de experiencias FRA con segmentación, metodología y limitaciones.",
                "Comparison of FRA experiences with segmentation, methodology and limitations.",
            ),
            (
                "Análisis sociológico de experiencias LGBTIQ+",
                "Sociological analysis of LGBTIQ+ experiences",
            ),
            source="fra",
            detail="detailed",
            sections=RESEARCH_SECTIONS,
            charts=("average", "countries", "responses", "radar"),
        ),
        _template(
            "sociology_legal_longitudinal",
            ("Serie legal longitudinal", "Longitudinal legal series"),
            (
                "Análisis histórico del ranking ILGA-Europe, comparabilidad y límites del modelo.",
                "Historical ILGA-Europe ranking analysis, comparability and model limitations.",
            ),
            (
                "Evolución longitudinal de la protección legal LGBTIQ+",
                "Longitudinal evolution of LGBTIQ+ legal protection",
            ),
            source="ilga",
            detail="detailed",
            sections=RESEARCH_SECTIONS,
            charts=("ranking", "average", "countries", "temporal"),
        ),
    ),
    "ong": (
        _template(
            "ngo_advocacy_dossier",
            ("Dossier de incidencia", "Advocacy dossier"),
            (
                "Evidencia legal comparada, riesgos, recomendaciones y atribución de fuentes.",
                "Comparative legal evidence, risks, recommendations and source attribution.",
            ),
            ("Dossier de incidencia por los derechos LGBTIQ+", "LGBTIQ+ rights advocacy dossier"),
            source="ilga",
            detail="detailed",
            sections=LEGAL_SECTIONS,
            charts=("ranking", "average", "countries", "temporal"),
        ),
        _template(
            "ngo_lived_experiences",
            ("Evidencia de experiencias vividas", "Lived-experience evidence"),
            (
                "Indicadores FRA para documentar desigualdades y apoyar acciones de incidencia.",
                "FRA indicators to document inequalities and support advocacy actions.",
            ),
            (
                "Evidencia sobre experiencias vividas LGBTIQ+",
                "Evidence on LGBTIQ+ lived experiences",
            ),
            source="fra",
            detail="detailed",
            sections=(*RESEARCH_SECTIONS, "risks", "recommendations"),
            charts=("average", "countries", "responses", "radar"),
        ),
    ),
    "admin": (
        _template(
            "admin_source_coverage",
            ("Cobertura de fuentes", "Source coverage"),
            (
                "Informe de control sobre cobertura temporal, países, metodología y fuentes.",
                "Control report on temporal coverage, countries, methodology and sources.",
            ),
            ("Control de cobertura de fuentes RainbowLens", "RainbowLens source coverage control"),
            source="ilga",
            detail="detailed",
            sections=RESEARCH_SECTIONS,
            charts=("ranking", "countries", "temporal"),
        ),
        _template(
            "admin_data_review",
            ("Revisión descriptiva de datos", "Descriptive data review"),
            (
                "Plantilla para revisar indicadores FRA, segmentaciones y limitaciones.",
                "Template for reviewing FRA indicators, segmentations and limitations.",
            ),
            ("Revisión de datos y calidad descriptiva", "Data and descriptive quality review"),
            source="fra",
            detail="detailed",
            sections=RESEARCH_SECTIONS,
            charts=("average", "countries", "responses", "radar"),
        ),
    ),
}


def report_profile_key(user: object) -> str:
    if not bool(getattr(user, "is_authenticated", False)):
        return "anonymous"
    role = getattr(user, "role", None)
    role_value = role.value if isinstance(role, UserRole) else str(role or "")
    if role_value.casefold() == UserRole.ADMIN.value:
        return "admin"
    user_type = getattr(user, "user_type", None)
    type_value = user_type.value if isinstance(user_type, UserType) else str(user_type or "")
    clean = type_value.strip().casefold()
    if clean == "profesor":
        clean = UserType.DOCENTE.value
    return clean if clean in PROFILE_TEMPLATES else "comun"


def report_templates_for_user(user: object) -> tuple[ReportTemplate, ...]:
    return PROFILE_TEMPLATES[report_profile_key(user)]


def find_report_template(user: object, template_id: str | None) -> ReportTemplate:
    templates = report_templates_for_user(user)
    return next((item for item in templates if item.id == template_id), templates[0])


def apply_template_defaults(
    values: dict[str, Any] | None,
    template: ReportTemplate,
    *,
    language: str,
) -> dict[str, Any]:
    payload = dict(values or {})
    for key, value in template.defaults(language).items():
        payload.setdefault(key, value)
    return payload
