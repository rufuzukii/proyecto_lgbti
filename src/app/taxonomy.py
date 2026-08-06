from __future__ import annotations

import logging
import unicodedata
from collections.abc import Sequence
from threading import Lock
from typing import Literal

Language = Literal["es", "en"]
TaxonomyLabels = dict[str, dict[str, dict[Language, str]]]

logger = logging.getLogger(__name__)
_missing_labels: set[tuple[str, str]] = set()
_missing_lock = Lock()

TAXONOMY_LABELS: TaxonomyLabels = {
    "role": {
        "comun": {"es": "Usuario", "en": "User"},
        "admin": {"es": "Administrador", "en": "Administrator"},
        "docente": {"es": "Docente", "en": "Educator"},
        "rrhh": {"es": "RRHH", "en": "HR"},
        "politico": {"es": "Pol\u00edtico", "en": "Policy maker"},
        "ong": {"es": "ONG", "en": "NGO"},
        "sociologo": {"es": "Soci\u00f3logo", "en": "Sociologist"},
    },
    "data_type": {
        "fra": {"es": "Sociodemogr\u00e1ficos", "en": "Sociodemographic"},
        "ilga": {"es": "Legales", "en": "Legal"},
        "felgtbi": {"es": "Estado LGBTIQ+ en Espa\u00f1a", "en": "LGBTIQ+ situation in Spain"},
    },
    "data_source": {
        "fra": {"es": "Encuesta europea LGBTIQ+", "en": "European LGBTIQ+ survey"},
        "ilga": {"es": "Mapa legal europeo", "en": "European legal map"},
        "felgtbi": {"es": "Estado LGBTIQ+ en Espa\u00f1a", "en": "LGBTIQ+ situation in Spain"},
    },
    "fra_filter": {
        "All": {"es": "Todos", "en": "All"},
        "Age": {"es": "Edad", "en": "Age"},
        "Sexual Orientation": {"es": "Orientaci\u00f3n sexual", "en": "Sexual orientation"},
        "Education": {"es": "Educaci\u00f3n", "en": "Education"},
        "Employment status": {"es": "Situaci\u00f3n laboral", "en": "Employment status"},
        "Belonging to a minority group": {"es": "Pertenencia a una minor\u00eda", "en": "Minority status"},
        "Openness about being LGBTIQ+": {"es": "Apertura sobre ser LGBTIQ+", "en": "Openness about being LGBTIQ+"},
        "Place of residence": {"es": "Lugar de residencia", "en": "Place of residence"},
        "Activity limitation": {"es": "Limitaci\u00f3n de actividad", "en": "Activity limitation"},
        "Making ends meet": {"es": "Capacidad para llegar a fin de mes", "en": "Making ends meet"},
        "Gender Expression": {"es": "Identidad o expresi\u00f3n de g\u00e9nero", "en": "Gender identity or expression"},
        "Sex Characteristics": {"es": "Caracter\u00edsticas sexuales", "en": "Sex characteristics"},
    },
    "fra_category": {
        "Discrimination": {"es": "Discriminaci\u00f3n", "en": "Discrimination"},
        "Education": {"es": "Educaci\u00f3n", "en": "Education"},
        "Employment": {"es": "Empleo", "en": "Employment"},
        "Health": {"es": "Salud", "en": "Health"},
        "Housing": {"es": "Vivienda", "en": "Housing"},
        "Family": {"es": "Familia", "en": "Family"},
        "Hate crime & hate speech": {"es": "Delitos y discursos de odio", "en": "Hate crime and hate speech"},
        "Political participation": {"es": "Participaci\u00f3n pol\u00edtica", "en": "Political participation"},
        "Territory": {"es": "Territorio", "en": "Territory"},
        "Trans and gender identity": {"es": "Realidad trans e identidad de g\u00e9nero", "en": "Trans and gender identity"},
        "Intersex": {"es": "Intersexualidad", "en": "Intersex"},
    },
    "fra_response": {
        "All": {"es": "Todas", "en": "All"},
        "Yes": {"es": "S\u00ed", "en": "Yes"},
        "No": {"es": "No", "en": "No"},
        "Don't know": {"es": "No lo sabe", "en": "Don't know"},
        "Prefer not to say": {"es": "Prefiere no responder", "en": "Prefer not to say"},
        "Never": {"es": "Nunca", "en": "Never"},
        "Rarely": {"es": "Rara vez", "en": "Rarely"},
        "Sometimes": {"es": "A veces", "en": "Sometimes"},
        "Often": {"es": "A menudo", "en": "Often"},
        "Always": {"es": "Siempre", "en": "Always"},
        "Very good": {"es": "Muy buena", "en": "Very good"},
        "Fairly good": {"es": "Bastante buena", "en": "Fairly good"},
        "Fairly bad": {"es": "Bastante mala", "en": "Fairly bad"},
        "Very bad": {"es": "Muy mala", "en": "Very bad"},
        "Not available": {"es": "Sin datos", "en": "No data"},
    },
    "ilga_category": {
        "Ranking total": {"es": "Ranking total", "en": "Overall ranking"},
        "Equality & non-discrimination": {"es": "Igualdad y no discriminaci\u00f3n", "en": "Equality and non-discrimination"},
        "Family": {"es": "Familia", "en": "Family"},
        "Hate crime & hate speech": {"es": "Delitos y discursos de odio", "en": "Hate crime and hate speech"},
        "Legal gender recognition": {"es": "Reconocimiento legal del g\u00e9nero", "en": "Legal gender recognition"},
        "Intersex bodily integrity": {"es": "Integridad corporal intersex", "en": "Intersex bodily integrity"},
        "Civil society space": {"es": "Espacio de la sociedad civil", "en": "Civil society space"},
        "Asylum": {"es": "Asilo", "en": "Asylum"},
    },
    "legal_status": {
        "fully_met": {"es": "Cumplimiento completo", "en": "Fully met"},
        "partially_met": {"es": "Cumplimiento parcial", "en": "Partially met"},
        "not_met": {"es": "No reconocido", "en": "Not met"},
        "not_available": {"es": "Informaci\u00f3n no disponible", "en": "Information unavailable"},
        "overall_score": {"es": "Puntuaci\u00f3n legal", "en": "Legal score"},
    },
    "felgtbi_topic": {
        "Discrimination": {"es": "Discriminaci\u00f3n", "en": "Discrimination"},
        "Employment": {"es": "Empleo", "en": "Employment"},
        "Health": {"es": "Salud", "en": "Health"},
        "Healthcare": {"es": "Atenci\u00f3n sanitaria", "en": "Healthcare"},
        "Mental health": {"es": "Salud mental", "en": "Mental health"},
        "Education": {"es": "Educaci\u00f3n", "en": "Education"},
        "Housing": {"es": "Vivienda", "en": "Housing"},
        "Family": {"es": "Familia", "en": "Family"},
        "Trans and gender identity": {"es": "Realidad trans e identidad de g\u00e9nero", "en": "Trans and gender identity"},
        "Trans rights": {"es": "Derechos trans", "en": "Trans rights"},
        "Intersex": {"es": "Intersexualidad", "en": "Intersex"},
        "Hate crime & hate speech": {"es": "Delitos y discursos de odio", "en": "Hate crime and hate speech"},
        "Hate crime": {"es": "Delitos de odio", "en": "Hate crime"},
        "Harassment": {"es": "Acoso", "en": "Harassment"},
        "Physical violence": {"es": "Violencia f\u00edsica", "en": "Physical violence"},
        "Sexual violence": {"es": "Violencia sexual", "en": "Sexual violence"},
        "LGBTIQ+ youth": {"es": "Juventud LGBTIQ+", "en": "LGBTIQ+ youth"},
        "Social acceptance": {"es": "Aceptaci\u00f3n social", "en": "Social acceptance"},
        "Political participation": {"es": "Participaci\u00f3n pol\u00edtica", "en": "Political participation"},
        "Territory": {"es": "Territorio", "en": "Territory"},
    },
}

TAXONOMY_ALIASES: dict[str, dict[str, str]] = {
    "role": {
        "common": "comun",
        "user": "comun",
        "usuario": "comun",
        "profesor": "docente",
        "teacher": "docente",
        "politician": "politico",
        "sociologist": "sociologo",
    },
    "data_type": {"sociodemographic": "fra", "legal": "ilga", "felgtb": "felgtbi"},
    "data_source": {"felgtb": "felgtbi"},
    "fra_filter": {
        "sexual_orientation": "Sexual Orientation",
        "gender_identity": "Gender Expression",
        "gender expression": "Gender Expression",
        "sex_characteristics": "Sex Characteristics",
    },
    "ilga_category": {
        "equality and non-discrimination": "Equality & non-discrimination",
        "hate crime and hate speech": "Hate crime & hate speech",
        "intersex rights": "Intersex bodily integrity",
    },
}


def canonical_taxonomy_value(namespace: str, value: object) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    labels = TAXONOMY_LABELS.get(namespace, {})
    normalized = _normalize(clean)
    canonical_by_normalized = {_normalize(key): key for key in labels}
    aliases = {_normalize(key): canonical for key, canonical in TAXONOMY_ALIASES.get(namespace, {}).items()}
    return aliases.get(normalized) or canonical_by_normalized.get(normalized) or clean


def taxonomy_label(namespace: str, value: object, language: str = "es") -> str:
    canonical = canonical_taxonomy_value(namespace, value)
    selected_language: Language = "en" if language == "en" else "es"
    labels = TAXONOMY_LABELS.get(namespace, {}).get(canonical)
    if labels is not None:
        return labels[selected_language]
    _log_missing_label(namespace, canonical)
    return canonical


def taxonomy_pair(namespace: str, value: object) -> tuple[str, str]:
    return (
        taxonomy_label(namespace, value, "es"),
        taxonomy_label(namespace, value, "en"),
    )


def taxonomy_labels(
    namespace: str,
    values: Sequence[object],
    language: str = "es",
) -> list[str]:
    return [taxonomy_label(namespace, value, language) for value in values]


def _log_missing_label(namespace: str, canonical: str) -> None:
    marker = (namespace, canonical)
    with _missing_lock:
        if marker in _missing_labels:
            return
        _missing_labels.add(marker)
    logger.warning(
        "taxonomy_label_missing",
        extra={"taxonomy": namespace, "canonical_value": canonical},
    )


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).casefold().replace("_", " ")
    unaccented = "".join(
        character for character in text if not unicodedata.combining(character)
    )
    return " ".join(unaccented.split())
