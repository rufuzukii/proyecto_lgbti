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
    objective: str = "overview"

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
            "objective": self.objective,
            "detail_level": self.detail_level,
            "sections": list(self.sections),
            "charts": list(self.charts),
        }


@dataclass(frozen=True, slots=True)
class ReportObjective:
    id: str
    label_es: str
    label_en: str
    description_es: str
    description_en: str

    def option(self, language: str) -> dict[str, str]:
        return {
            "label": self.label_en if language == "en" else self.label_es,
            "value": self.id,
        }

    def label(self, language: str) -> str:
        return self.label_en if language == "en" else self.label_es

    def description(self, language: str) -> str:
        return self.description_en if language == "en" else self.description_es


@dataclass(frozen=True, slots=True)
class ReportProfile:
    key: str
    name_es: str
    name_en: str
    description_es: str
    description_en: str
    objectives: tuple[ReportObjective, ...]
    recommended_sections: tuple[str, ...]
    recommended_charts: tuple[str, ...]
    supports_spanish_context: bool = False

    def name(self, language: str) -> str:
        return self.name_en if language == "en" else self.name_es

    def description(self, language: str) -> str:
        return self.description_en if language == "en" else self.description_es


def _objective(
    identifier: str,
    labels: tuple[str, str],
    descriptions: tuple[str, str],
) -> ReportObjective:
    return ReportObjective(identifier, labels[0], labels[1], descriptions[0], descriptions[1])


GENERAL_SECTIONS = DEFAULT_REPORT_SECTIONS
GENERAL_CHARTS = DEFAULT_REPORT_CHARTS
LEGAL_SECTIONS = (
    "executive",
    "context",
    "metrics",
    "analysis",
    "comparison",
    "interpretation",
    "recommendations",
    "methodology",
    "limitations",
    "sources",
)
RESEARCH_SECTIONS = (
    "executive",
    "context",
    "metrics",
    "analysis",
    "comparison",
    "demographics",
    "data_quality",
    "interpretation",
    "methodology",
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
    objective: str = "overview",
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
        objective=objective,
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
                "interpretation",
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
            sections=(*RESEARCH_SECTIONS, "recommendations"),
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


COMMON_SECTIONS = (
    "executive", "context", "metrics", "analysis", "comparison",
    "interpretation", "recommendations", "methodology", "limitations", "sources",
)
PROFESSIONAL_SECTIONS = (
    "executive", "context", "metrics", "analysis", "workplace", "comparison",
    "demographics", "interpretation", "recommendations", "methodology", "limitations", "sources",
)
RESEARCH_PROFILE_SECTIONS = (
    "executive", "context", "metrics", "analysis", "comparison", "demographics",
    "data_quality", "interpretation", "recommendations", "methodology", "limitations", "sources",
)

REPORT_PROFILES: dict[str, ReportProfile] = {
    "anonymous": ReportProfile(
        "anonymous", "Usuario", "User",
        "Un informe introductorio, breve y comprensible.",
        "A short, understandable introductory report.",
        (
            _objective("overview", ("Obtener un resumen general", "Get a general overview"), ("Síntesis de los datos y sus fuentes.", "Summary of the data and its sources.")),
            _objective("country", ("Comprender la situación de un país", "Understand one country"), ("Sitúa un país frente al conjunto europeo.", "Places one country in the European context.")),
            _objective("compare", ("Comparar varios países", "Compare countries"), ("Destaca semejanzas y diferencias descriptivas.", "Highlights descriptive similarities and differences.")),
        ),
        COMMON_SECTIONS,
        ("ranking", "average", "countries", "median_difference"),
    ),
    "comun": ReportProfile(
        "comun", "Usuario común", "General user",
        "Prioriza explicaciones sencillas, pocas métricas y comparaciones claras.",
        "Prioritises plain explanations, a small set of metrics and clear comparisons.",
        (
            _objective("country", ("Comprender la situación de un país", "Understand one country"), ("Explica los resultados de un territorio y su contexto.", "Explains a territory's results and context.")),
            _objective("compare", ("Comparar varios países", "Compare countries"), ("Compara países sin convertir la diferencia en una valoración automática.", "Compares countries without turning differences into automatic judgements.")),
            _objective("topic", ("Conocer una realidad concreta", "Explore a specific issue"), ("Se centra en el indicador y la respuesta elegidos.", "Focuses on the chosen indicator and answer.")),
            _objective("overview", ("Obtener un resumen general", "Get a general overview"), ("Resume resultados, límites y fuentes.", "Summarises results, limitations and sources.")),
        ),
        COMMON_SECTIONS,
        ("ranking", "average", "countries", "median_difference"),
    ),
    "docente": ReportProfile(
        "docente", "Docente", "Teacher",
        "Añade contexto, conceptos y propuestas para trabajar los datos en el aula.",
        "Adds context, concepts and ideas for using the data in class.",
        (
            _objective("class_material", ("Preparar material para clase", "Prepare class material"), ("Crea una explicación guiada con conceptos clave.", "Creates a guided explanation with key concepts.")),
            _objective("country_debate", ("Explicar diferencias entre países", "Explain country differences"), ("Incluye preguntas para interpretar las comparaciones.", "Includes questions for interpreting comparisons.")),
            _objective("discrimination", ("Trabajar discriminación", "Explore discrimination"), ("Orienta una actividad de análisis y reflexión.", "Supports an analysis and reflection activity.")),
            _objective("legal_rights", ("Trabajar derechos legales", "Explore legal rights"), ("Relaciona criterios legales y contexto europeo.", "Connects legal criteria and European context.")),
            _objective("debate", ("Crear una actividad de debate", "Create a debate activity"), ("Propone preguntas abiertas basadas en la evidencia.", "Suggests evidence-based open questions.")),
        ),
        (*COMMON_SECTIONS, "education"),
        ("ranking", "average", "countries", "responses", "median_difference"),
        True,
    ),
    "rrhh": ReportProfile(
        "rrhh", "RRHH", "Human Resources",
        "Contextualiza inclusión laboral sin atribuir los datos europeos a una empresa concreta.",
        "Provides workplace inclusion context without treating European data as company data.",
        (
            _objective("workplace_discrimination", ("Discriminación en el trabajo", "Workplace discrimination"), ("Prioriza indicadores de discriminación y prevención.", "Prioritises discrimination and prevention indicators.")),
            _objective("inclusion_visibility", ("Inclusión y visibilidad", "Inclusion and visibility"), ("Analiza seguridad, apertura y barreras percibidas.", "Analyses safety, openness and perceived barriers.")),
            _objective("country_compare", ("Comparación europea", "European comparison"), ("Compara el contexto de varios países.", "Compares the context of several countries.")),
            _objective("internal_policies", ("Políticas internas", "Internal policies"), ("Orienta posibles medidas generales de diversidad e inclusión.", "Supports possible general diversity and inclusion measures.")),
        ),
        PROFESSIONAL_SECTIONS,
        ("average", "countries", "responses", "median_difference", "scatter"),
        True,
    ),
    "ong": ReportProfile(
        "ong", "Organización / ONG", "Organisation / NGO",
        "Prioriza brechas, grupos afectados e incidencia basada en datos.",
        "Prioritises gaps, affected groups and data-informed advocacy.",
        (
            _objective("advocacy", ("Preparar incidencia", "Prepare advocacy"), ("Organiza evidencia, límites y áreas prioritarias.", "Organises evidence, limitations and priority areas.")),
            _objective("social_needs", ("Analizar necesidades sociales", "Analyse social needs"), ("Destaca indicadores y segmentos con resultados desfavorables.", "Highlights indicators and segments with unfavourable results.")),
            _objective("territorial", ("Comparar territorios", "Compare territories"), ("Contrasta países y disponibilidad de datos.", "Contrasts countries and data availability.")),
            _objective("pending_rights", ("Examinar derechos pendientes", "Examine pending rights"), ("Se centra en protección y criterios legales.", "Focuses on legal protection and criteria.")),
        ),
        PROFESSIONAL_SECTIONS,
        ("ranking", "countries", "responses", "median_difference", "quadrants"),
        True,
    ),
    "politico": ReportProfile(
        "politico", "Responsable público", "Public policy",
        "Presenta evidencia territorial, brechas y posibles medidas públicas con lenguaje neutral.",
        "Presents territorial evidence, gaps and possible public measures in neutral language.",
        (
            _objective("public_policy", ("Definir prioridades públicas", "Define public priorities"), ("Resume brechas observadas y áreas para seguimiento.", "Summarises observed gaps and areas to monitor.")),
            _objective("territorial", ("Comparar territorios", "Compare territories"), ("Sitúa el territorio frente a países comparables.", "Places the territory alongside comparable countries.")),
            _objective("rights", ("Analizar derechos y protección", "Analyse rights and protection"), ("Describe el marco legal y su evolución.", "Describes the legal framework and its evolution.")),
            _objective("discrimination", ("Analizar discriminación", "Analyse discrimination"), ("Presenta indicadores sociales y limitaciones relevantes.", "Presents social indicators and relevant limitations.")),
        ),
        PROFESSIONAL_SECTIONS,
        ("ranking", "average", "countries", "temporal", "median_difference", "scatter"),
    ),
    "sociologo": ReportProfile(
        "sociologo", "Sociólogo / investigador", "Sociologist / researcher",
        "Incluye mayor detalle descriptivo, comparabilidad, disponibilidad y método.",
        "Includes more descriptive detail, comparability, availability and methodology.",
        (
            _objective("descriptive", ("Análisis descriptivo", "Descriptive analysis"), ("Resume media, mediana, dispersión y cobertura.", "Summarises mean, median, spread and coverage.")),
            _objective("country_compare", ("Comparación entre países", "Country comparison"), ("Examina diferencias con la misma selección analítica.", "Examines differences using the same analytical selection.")),
            _objective("segmentation", ("Segmentación sociodemográfica", "Sociodemographic segmentation"), ("Documenta filtros y alcance de la subpoblación.", "Documents filters and subpopulation scope.")),
            _objective("combined", ("Análisis social + legal", "Social + legal analysis"), ("Explora asociación, cuadrantes y calidad de datos sin inferir causalidad.", "Explores association, quadrants and data quality without inferring causality.")),
            _objective("availability", ("Disponibilidad de datos", "Data availability"), ("Distingue dato ausente, no participación y comparabilidad.", "Distinguishes missing data, non-participation and comparability.")),
        ),
        RESEARCH_PROFILE_SECTIONS,
        ("ranking", "responses", "scatter", "quadrants", "median_difference", "availability"),
    ),
    "admin": ReportProfile(
        "admin", "Administrador", "Administrator",
        "Permite supervisar y previsualizar las plantillas sin crear un informe técnico de administración.",
        "Allows templates to be reviewed and previewed without creating a technical administration report.",
        (
            _objective("overview", ("Supervisar una plantilla", "Review a template"), ("Previsualiza la salida profesional seleccionada.", "Previews the selected professional output.")),
            _objective("data_quality", ("Revisar cobertura de datos", "Review data coverage"), ("Prioriza fuentes, disponibilidad y limitaciones.", "Prioritises sources, availability and limitations.")),
        ),
        RESEARCH_PROFILE_SECTIONS,
        DEFAULT_REPORT_CHARTS,
        True,
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
    profile_key = report_profile_key(user)
    if profile_key != "admin":
        return PROFILE_TEMPLATES[profile_key]
    # Administrators may preview every professional template. This changes the
    # report audience, not the authenticated user's permissions.
    return tuple(
        template
        for key, templates in PROFILE_TEMPLATES.items()
        if key != "anonymous"
        for template in templates
    )


def find_report_template(user: object, template_id: str | None) -> ReportTemplate:
    templates = report_templates_for_user(user)
    return next((item for item in templates if item.id == template_id), templates[0])


def report_profile_for_user(user: object) -> ReportProfile:
    return REPORT_PROFILES[report_profile_key(user)]


def report_profile_for_template(template_id: str | None) -> ReportProfile | None:
    for profile_key, templates in PROFILE_TEMPLATES.items():
        if any(template.id == template_id for template in templates):
            return REPORT_PROFILES[profile_key]
    return None


def report_objective(profile_key: str, objective_id: str | None) -> ReportObjective:
    profile = REPORT_PROFILES.get(profile_key, REPORT_PROFILES["comun"])
    return next(
        (objective for objective in profile.objectives if objective.id == objective_id),
        profile.objectives[0],
    )


def report_profile(profile_key: str) -> ReportProfile:
    return REPORT_PROFILES.get(profile_key, REPORT_PROFILES["comun"])


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
