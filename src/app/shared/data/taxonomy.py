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
        "Belonging to a minority group": {
            "es": "Pertenencia a una minor\u00eda",
            "en": "Minority status",
        },
        "Openness about being LGBTIQ+": {
            "es": "Apertura sobre ser LGBTIQ+",
            "en": "Openness about being LGBTIQ+",
        },
        "Place of residence": {"es": "Lugar de residencia", "en": "Place of residence"},
        "Activity limitation": {"es": "Limitaci\u00f3n de actividad", "en": "Activity limitation"},
        "Making ends meet": {"es": "Capacidad para llegar a fin de mes", "en": "Making ends meet"},
        "Gender Expression": {
            "es": "Identidad o expresi\u00f3n de g\u00e9nero",
            "en": "Gender identity or expression",
        },
        "Sex Characteristics": {"es": "Caracter\u00edsticas sexuales", "en": "Sex characteristics"},
    },
    "fra_filter_value": {
        "All": {"es": "Todos", "en": "All"},
        "15-17": {"es": "15\u201317", "en": "15\u201317"},
        "18-24": {"es": "18\u201324", "en": "18\u201324"},
        "25-39": {"es": "25\u201339", "en": "25\u201339"},
        "40-54": {"es": "40\u201354", "en": "40\u201354"},
        "55+": {"es": "55+", "en": "55+"},
        "Yes": {"es": "Sí", "en": "Yes"},
        "No": {"es": "No", "en": "No"},
        "Limited but not severely": {"es": "Limitación no grave", "en": "Limited but not severely"},
        "Not limited at all": {"es": "Sin limitación", "en": "Not limited at all"},
        "Severely limited": {"es": "Limitación grave", "en": "Severely limited"},
        "Lower education or less (1,2,3)": {
            "es": "Educación inferior o menos (1,2,3)",
            "en": "Lower education or less (1,2,3)",
        },
        "Tertiary education (5,6,7,8)": {
            "es": "Educación terciaria (5,6,7,8)",
            "en": "Tertiary education (5,6,7,8)",
        },
        "Upper secondary education (4)": {
            "es": "Educación secundaria superior (4)",
            "en": "Upper secondary education (4)",
        },
        "In work": {"es": "Con empleo", "en": "In work"},
        "Not in work": {"es": "Sin empleo", "en": "Not in work"},
        "Unemployed": {"es": "En desempleo", "en": "Unemployed"},
        "Cisgender men": {"es": "Hombres cisgénero", "en": "Cisgender men"},
        "Cisgender women": {"es": "Mujeres cisgénero", "en": "Cisgender women"},
        "Non-binary & gender-diverse": {
            "es": "Personas no binarias y de género diverso",
            "en": "Non-binary and gender-diverse",
        },
        "Other": {"es": "Otra categoría", "en": "Other"},
        "Trans men": {"es": "Hombres trans", "en": "Trans men"},
        "Trans women": {"es": "Mujeres trans", "en": "Trans women"},
        "Fairly - very easily": {
            "es": "Con bastante o mucha facilidad",
            "en": "Fairly or very easily",
        },
        "With difficulty": {"es": "Con dificultad", "en": "With difficulty"},
        "With great difficulty": {"es": "Con mucha dificultad", "en": "With great difficulty"},
        "With some difficulty": {"es": "Con alguna dificultad", "en": "With some difficulty"},
        "Fairly open": {"es": "Bastante abierta", "en": "Fairly open"},
        "Never open": {"es": "Nunca abierta", "en": "Never open"},
        "Rarely open": {"es": "Rara vez abierta", "en": "Rarely open"},
        "Very open": {"es": "Muy abierta", "en": "Very open"},
        "A big city": {"es": "Una gran ciudad", "en": "A big city"},
        "A farm or home in the countryside": {
            "es": "Una granja o vivienda rural",
            "en": "A farm or home in the countryside",
        },
        "A town or a small city": {
            "es": "Un pueblo o ciudad pequeña",
            "en": "A town or a small city",
        },
        "A village": {"es": "Una aldea", "en": "A village"},
        "The suburbs or outskirts of a big city": {
            "es": "Los suburbios o afueras de una gran ciudad",
            "en": "The suburbs or outskirts of a big city",
        },
        "Endosex": {"es": "Endosex", "en": "Endosex"},
        "Intersex": {"es": "Intersex", "en": "Intersex"},
        "Asexual": {"es": "Asexual", "en": "Asexual"},
        "Bisexual": {"es": "Bisexual", "en": "Bisexual"},
        "Gay": {"es": "Gay", "en": "Gay"},
        "Heterosexual/Straight": {"es": "Heterosexual", "en": "Heterosexual/Straight"},
        "Lesbian": {"es": "Lesbiana", "en": "Lesbian"},
        "Pansexual": {"es": "Pansexual", "en": "Pansexual"},
    },
    "fra_category": {
        "Discrimination": {"es": "Discriminaci\u00f3n", "en": "Discrimination"},
        "Education": {"es": "Educaci\u00f3n", "en": "Education"},
        "Employment": {"es": "Empleo", "en": "Employment"},
        "Health": {"es": "Salud", "en": "Health"},
        "Health and mental health": {
            "es": "Salud y salud mental",
            "en": "Health and mental health",
        },
        "Housing": {"es": "Vivienda", "en": "Housing"},
        "Family": {"es": "Familia", "en": "Family"},
        "Hate crime & hate speech": {
            "es": "Delitos y discursos de odio",
            "en": "Hate crime and hate speech",
        },
        "Political participation": {
            "es": "Participaci\u00f3n pol\u00edtica",
            "en": "Political participation",
        },
        "Territory": {"es": "Territorio", "en": "Territory"},
        "Trans and gender identity": {
            "es": "Realidad trans e identidad de g\u00e9nero",
            "en": "Trans and gender identity",
        },
        "Intersex": {"es": "Intersexualidad", "en": "Intersex"},
        "Intersex specific questions": {
            "es": "Preguntas específicas sobre intersexualidad",
            "en": "Intersex specific questions",
        },
        "Living openly and daily life": {
            "es": "Vida abierta y vida cotidiana",
            "en": "Living openly and daily life",
        },
        "Living openly as LGBTIQ": {
            "es": "Vivir abiertamente como persona LGBTIQ+",
            "en": "Living openly as LGBTIQ",
        },
        "LGBTIQ-parented families and free movement": {
            "es": "Familias con progenitores LGBTIQ+ y libre circulación",
            "en": "LGBTIQ-parented families and free movement",
        },
        "Social attitudes and government response": {
            "es": "Actitudes sociales y respuesta gubernamental",
            "en": "Social attitudes and government response",
        },
        "Socio-demographics": {
            "es": "Datos sociodemográficos",
            "en": "Socio-demographics",
        },
        "Trans specific questions": {
            "es": "Preguntas específicas sobre personas trans",
            "en": "Trans specific questions",
        },
        "Violence and harassment": {
            "es": "Violencia y acoso",
            "en": "Violence and harassment",
        },
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
        "1st": {"es": "1st — Primera razón", "en": "1st — First reason"},
        "2nd": {"es": "2nd — Segunda razón", "en": "2nd — Second reason"},
        "3rd": {"es": "3rd — Tercera razón", "en": "3rd — Third reason"},
        "Not Selected": {
            "es": "Not selected — No seleccionada",
            "en": "Not selected — Not selected",
        },
        "Not available": {"es": "Sin datos", "en": "No data"},
    },
    "ilga_category": {
        "Ranking total": {"es": "Ranking total", "en": "Overall ranking"},
        "Equality & non-discrimination": {
            "es": "Igualdad y no discriminaci\u00f3n",
            "en": "Equality and non-discrimination",
        },
        "Family": {"es": "Familia", "en": "Family"},
        "Hate crime & hate speech": {
            "es": "Delitos y discursos de odio",
            "en": "Hate crime and hate speech",
        },
        "Legal gender recognition": {
            "es": "Reconocimiento legal del g\u00e9nero",
            "en": "Legal gender recognition",
        },
        "Intersex bodily integrity": {
            "es": "Integridad corporal intersex",
            "en": "Intersex bodily integrity",
        },
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
        "Trans and gender identity": {
            "es": "Realidad trans e identidad de g\u00e9nero",
            "en": "Trans and gender identity",
        },
        "Trans rights": {"es": "Derechos trans", "en": "Trans rights"},
        "Intersex": {"es": "Intersexualidad", "en": "Intersex"},
        "Hate crime & hate speech": {
            "es": "Delitos y discursos de odio",
            "en": "Hate crime and hate speech",
        },
        "Hate crime": {"es": "Delitos de odio", "en": "Hate crime"},
        "Harassment": {"es": "Acoso", "en": "Harassment"},
        "Physical violence": {"es": "Violencia f\u00edsica", "en": "Physical violence"},
        "Sexual violence": {"es": "Violencia sexual", "en": "Sexual violence"},
        "LGBTIQ+ youth": {"es": "Juventud LGBTIQ+", "en": "LGBTIQ+ youth"},
        "Social acceptance": {"es": "Aceptaci\u00f3n social", "en": "Social acceptance"},
        "Political participation": {
            "es": "Participaci\u00f3n pol\u00edtica",
            "en": "Political participation",
        },
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
    aliases = {
        _normalize(key): canonical for key, canonical in TAXONOMY_ALIASES.get(namespace, {}).items()
    }
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
    unaccented = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(unaccented.split())
