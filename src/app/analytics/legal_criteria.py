from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from app.taxonomy import taxonomy_label

SUPPORTED_LANGUAGES = {"es", "en"}

logger = logging.getLogger(__name__)


LEGAL_STATUS_ICONS = {
    "fully_met": "OK",
    "partially_met": "1/2",
    "not_met": "X",
    "not_available": "-",
}


LEGAL_CRITERIA_TRANSLATIONS: dict[str, dict[str, str]] = {}
_CRITERION_ALIASES: dict[str, str] = {}


def get_criterion_metadata(
    criterion: dict[str, Any] | str,
    language: str = "es",
) -> dict[str, str]:
    lang = _language(language)
    source_label = (
        str(criterion.get("indicator") or "").strip()
        if isinstance(criterion, dict)
        else str(criterion or "").strip()
    )
    category = str(criterion.get("category") or "").strip() if isinstance(criterion, dict) else ""
    criterion_id = get_criterion_id(source_label, category)
    record = LEGAL_CRITERIA_TRANSLATIONS.get(criterion_id or "")
    if record:
        display_title = record[f"title_{lang}"]
        return {
            "id": record["id"],
            "source_label": source_label or record["source_label"],
            "category": record["category"],
            "category_label": translate_legal_category(category or record["category"], lang),
            "display_title": display_title,
            "title": display_title,
            "summary": record[f"summary_{lang}"],
            "known": "true",
        }

    criterion_id = stable_criterion_id(source_label, category)
    if source_label:
        logger.debug(
            "legal_criterion_metadata_missing",
            extra={
                "criterion_id": criterion_id,
                "source_label": source_label,
                "category": category,
            },
        )
    title = _fallback_title(lang)
    return {
        "id": criterion_id,
        "source_label": source_label,
        "category": category,
        "category_label": translate_legal_category(category, lang),
        "display_title": title,
        "title": title,
        "summary": _fallback_summary(lang),
        "known": "false",
    }


def get_criterion_id(source_label: str, category: str | None = None) -> str | None:
    clean_label = _normalize_key(source_label)
    clean_category = _normalize_key(category or "")
    if clean_category:
        mapped = _CRITERION_ALIASES.get(f"{clean_category}|{clean_label}")
        if mapped:
            return mapped
    return _CRITERION_ALIASES.get(clean_label)


def stable_criterion_id(source_label: str, category: str | None = None) -> str:
    mapped = get_criterion_id(source_label, category)
    if mapped:
        return mapped
    raw = f"{category or ''} {source_label or 'criterion'}"
    slug = re.sub(r"[^a-z0-9]+", "_", _strip_accents(raw).lower()).strip("_")
    return slug or "criterion"


def get_criterion_status(
    value: float | str | None,
    maximum_value: float | str | None = None,
    language: str = "es",
) -> dict[str, str]:
    numeric_value = _to_float(value)
    numeric_maximum = _to_float(maximum_value)

    if numeric_value is None:
        status_id = "not_available"
    elif numeric_value <= 0:
        status_id = "not_met"
    elif (
        numeric_maximum is not None and numeric_maximum > 0 and numeric_value >= numeric_maximum
    ) or (numeric_maximum is None and numeric_value >= 1):
        status_id = "fully_met"
    else:
        status_id = "partially_met"

    lang = _language(language)
    return {
        "id": status_id,
        "label": taxonomy_label("legal_status", status_id, lang),
        "icon": LEGAL_STATUS_ICONS[status_id],
    }


def get_criterion_score_label(
    value: float | str | None,
    maximum_value: float | str | None,
    language: str = "es",
) -> str:
    numeric_value = _to_float(value)
    numeric_maximum = _to_float(maximum_value)
    if numeric_value is None:
        return ""
    lang = _language(language)
    label = "Puntuación" if lang == "es" else "Score"
    if numeric_maximum is not None and numeric_maximum > 0:
        return f"{label}: {_format_number(numeric_value)} / {_format_number(numeric_maximum)}"
    return f"{label}: {_format_number(numeric_value)}"


def translate_legal_category(category: str, language: str = "es") -> str:
    lang = _language(language)
    clean = str(category or "").strip()
    if clean:
        return taxonomy_label("ilga_category", clean, lang)
    return clean or ("Sin categoría" if lang == "es" else "Uncategorised")


def _add_criterion(
    criterion_id: str,
    source_label: str,
    category: str,
    title_es: str,
    title_en: str,
    summary_es: str,
    summary_en: str,
    *aliases: str,
) -> None:
    LEGAL_CRITERIA_TRANSLATIONS[criterion_id] = {
        "id": criterion_id,
        "source_label": source_label,
        "category": category,
        "title_es": title_es,
        "title_en": title_en,
        "summary_es": summary_es,
        "summary_en": summary_en,
    }

    for label in {source_label, title_en, *aliases}:
        _register_alias(label, criterion_id)
        _register_alias(label, criterion_id, category)


def _register_alias(label: str, criterion_id: str, category: str | None = None) -> None:
    key = _normalize_key(label)
    if not key:
        return
    if category:
        _CRITERION_ALIASES[f"{_normalize_key(category)}|{key}"] = criterion_id
    else:
        _CRITERION_ALIASES[key] = criterion_id


def _criterion_aliases(base: str, ground: str | None = None) -> tuple[str, ...]:
    aliases = {base}
    if ground:
        aliases.add(f"{base} ({ground})")
        aliases.add(f"{base} - {ground}")
        aliases.add(f"{base} — {ground}")
        short = {
            "sexual orientation": "SO",
            "gender identity": "GI",
            "sex characteristics": "SC",
            "gender expression": "GE",
        }.get(ground.lower())
        if short:
            aliases.add(f"{base} ({short})")
            aliases.add(f"{base} - {short}")
    return tuple(sorted(aliases))


def _language(language: str) -> str:
    return language if language in SUPPORTED_LANGUAGES else "es"


def _fallback_summary(language: str) -> str:
    if _language(language) == "en":
        return "View this indicator's compliance level for the selected country."
    return "Consulta el grado de cumplimiento de este indicador en el país seleccionado."


def _fallback_title(language: str) -> str:
    return "Legal criterion" if _language(language) == "en" else "Criterio jurídico"


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace("%", "").replace(",", ".")
        if not value:
            return None
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def _format_number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _normalize_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", _strip_accents(str(value or "").lower()))


def _strip_accents(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char)
    )


EQUALITY = "Equality & non-discrimination"
FAMILY = "Family"
HATE = "Hate crime & hate speech"
LGR = "Legal gender recognition"
INTERSEX = "Intersex bodily integrity"
CIVIL = "Civil society space"
ASYLUM = "Asylum"


_add_criterion(
    "constitution_sexual_orientation",
    "Constitution (sexual orientation)",
    EQUALITY,
    "Protección constitucional por orientación sexual",
    "Constitutional protection based on sexual orientation",
    "Indica si la Constitución u otra norma equivalente protege frente a la discriminación por orientación sexual.",
    "Indicates whether the Constitution or an equivalent legal framework protects against discrimination based on sexual orientation.",
    *_criterion_aliases("Constitution", "sexual orientation"),
)
_add_criterion(
    "employment_sexual_orientation",
    "Employment (sexual orientation)",
    EQUALITY,
    "Protección laboral por orientación sexual",
    "Employment protection based on sexual orientation",
    "Indica si la legislación laboral prohíbe expresamente la discriminación por orientación sexual.",
    "Indicates whether employment legislation explicitly prohibits discrimination based on sexual orientation.",
    *_criterion_aliases("Employment", "sexual orientation"),
)
_add_criterion(
    "goods_services_sexual_orientation",
    "Goods and services (sexual orientation)",
    EQUALITY,
    "Acceso a bienes y servicios por orientación sexual",
    "Goods and services protection based on sexual orientation",
    "Indica si existe protección legal frente a la discriminación por orientación sexual en el acceso a bienes y servicios.",
    "Indicates whether the law protects against discrimination based on sexual orientation when accessing goods and services.",
    *_criterion_aliases("Goods and services", "sexual orientation"),
)
_add_criterion(
    "education_sexual_orientation",
    "Education (sexual orientation)",
    EQUALITY,
    "Protección educativa por orientación sexual",
    "Education protection based on sexual orientation",
    "Indica si la legislación educativa prohíbe expresamente la discriminación por orientación sexual.",
    "Indicates whether education legislation explicitly prohibits discrimination based on sexual orientation.",
    *_criterion_aliases("Education", "sexual orientation"),
)
_add_criterion(
    "health_sexual_orientation",
    "Health (sexual orientation)",
    EQUALITY,
    "Protección sanitaria por orientación sexual",
    "Healthcare protection based on sexual orientation",
    "Indica si existe protección legal frente a la discriminación por orientación sexual en el ámbito sanitario.",
    "Indicates whether the law protects against discrimination based on sexual orientation in healthcare.",
    *_criterion_aliases("Health", "sexual orientation"),
)
_add_criterion(
    "conversion_practices_ban_sexual_orientation",
    "Conversion practices ban (sexual orientation)",
    EQUALITY,
    "Prohibición de prácticas de conversión por orientación sexual",
    "Conversion practices ban based on sexual orientation",
    "Indica si están prohibidas las prácticas que pretenden cambiar o suprimir la orientación sexual de una persona, especialmente cuando afectan a menores.",
    "Indicates whether practices intended to change or suppress a person's sexual orientation are prohibited, particularly when they affect minors.",
    *_criterion_aliases("Conversion practices ban", "sexual orientation"),
    *_criterion_aliases("Conversion practices", "sexual orientation"),
)
_add_criterion(
    "equality_body_mandate_sexual_orientation",
    "Equality body mandate (sexual orientation)",
    EQUALITY,
    "Mandato del organismo de igualdad sobre orientación sexual",
    "Equality body mandate on sexual orientation",
    "Indica si el organismo nacional de igualdad o de derechos humanos tiene el mandato explícito de trabajar sobre discriminación por orientación sexual.",
    "Indicates whether the national equality or human rights body is explicitly mandated to address discrimination based on sexual orientation.",
    *_criterion_aliases("Equality body mandate", "sexual orientation"),
    *_criterion_aliases("Equality body", "sexual orientation"),
)
_add_criterion(
    "equality_action_plan_sexual_orientation",
    "Equality action plan (sexual orientation)",
    EQUALITY,
    "Plan de igualdad sobre orientación sexual",
    "Equality action plan on sexual orientation",
    "Indica si existe un plan de igualdad que incluya medidas concretas, recursos, responsabilidades y seguimiento sobre orientación sexual.",
    "Indicates whether an equality action plan includes specific measures, resources, responsibilities and monitoring related to sexual orientation.",
    *_criterion_aliases("Equality action plan", "sexual orientation"),
)

_add_criterion(
    "constitution_gender_identity",
    "Constitution (gender identity)",
    EQUALITY,
    "Protección constitucional por identidad de género",
    "Constitutional protection based on gender identity",
    "Indica si la Constitución u otra norma equivalente protege frente a la discriminación por identidad de género.",
    "Indicates whether the Constitution or an equivalent legal framework protects against discrimination based on gender identity.",
    *_criterion_aliases("Constitution", "gender identity"),
)
_add_criterion(
    "employment_gender_identity",
    "Employment (gender identity)",
    EQUALITY,
    "Protección laboral por identidad de género",
    "Employment protection based on gender identity",
    "Indica si la legislación laboral prohíbe expresamente la discriminación por identidad de género o conceptos equivalentes.",
    "Indicates whether employment legislation explicitly prohibits discrimination based on gender identity or equivalent grounds.",
    *_criterion_aliases("Employment", "gender identity"),
)
_add_criterion(
    "goods_services_gender_identity",
    "Goods and services (gender identity)",
    EQUALITY,
    "Acceso a bienes y servicios por identidad de género",
    "Goods and services protection based on gender identity",
    "Indica si existe protección frente a la discriminación por identidad de género en el acceso a bienes y servicios.",
    "Indicates whether the law protects against discrimination based on gender identity when accessing goods and services.",
    *_criterion_aliases("Goods and services", "gender identity"),
)
_add_criterion(
    "education_gender_identity",
    "Education (gender identity)",
    EQUALITY,
    "Protección educativa por identidad de género",
    "Education protection based on gender identity",
    "Indica si la legislación educativa protege frente a la discriminación por identidad de género.",
    "Indicates whether education legislation protects against discrimination based on gender identity.",
    *_criterion_aliases("Education", "gender identity"),
)
_add_criterion(
    "health_gender_identity",
    "Health (gender identity)",
    EQUALITY,
    "Protección sanitaria por identidad de género",
    "Healthcare protection based on gender identity",
    "Indica si existe protección legal frente a la discriminación por identidad de género en la atención sanitaria.",
    "Indicates whether the law protects against discrimination based on gender identity in healthcare.",
    *_criterion_aliases("Health", "gender identity"),
)
_add_criterion(
    "conversion_practices_ban_gender_identity",
    "Conversion practices ban (gender identity)",
    EQUALITY,
    "Prohibición de prácticas de conversión por identidad de género",
    "Conversion practices ban based on gender identity",
    "Indica si están prohibidas las prácticas que pretenden cambiar o suprimir la identidad de género de una persona.",
    "Indicates whether practices intended to change or suppress a person's gender identity are prohibited.",
    *_criterion_aliases("Conversion practices ban", "gender identity"),
    *_criterion_aliases("Conversion practices", "gender identity"),
)
_add_criterion(
    "equality_body_mandate_gender_identity",
    "Equality body mandate (gender identity)",
    EQUALITY,
    "Mandato del organismo de igualdad sobre identidad de género",
    "Equality body mandate on gender identity",
    "Indica si el organismo nacional de igualdad tiene competencias explícitas para abordar cuestiones relacionadas con la identidad de género.",
    "Indicates whether the national equality body has an explicit mandate to address issues related to gender identity.",
    *_criterion_aliases("Equality body mandate", "gender identity"),
    *_criterion_aliases("Equality body", "gender identity"),
)
_add_criterion(
    "equality_action_plan_gender_identity",
    "Equality action plan (gender identity)",
    EQUALITY,
    "Plan de igualdad sobre identidad de género",
    "Equality action plan on gender identity",
    "Indica si existe un plan público con medidas concretas para avanzar en la igualdad de las personas trans y de género diverso.",
    "Indicates whether a public action plan includes specific measures to advance equality for trans and gender-diverse people.",
    *_criterion_aliases("Equality action plan", "gender identity"),
)
_add_criterion(
    "law_gender_expression",
    "Law (gender expression)",
    EQUALITY,
    "Reconocimiento legal de la expresión de género",
    "Legal recognition of gender expression",
    "Indica si la expresión de género está reconocida expresamente como motivo protegido frente a la discriminación.",
    "Indicates whether gender expression is explicitly recognised as a protected ground against discrimination.",
    *_criterion_aliases("Law", "gender expression"),
)

_add_criterion(
    "constitution_sex_characteristics",
    "Constitution (sex characteristics)",
    EQUALITY,
    "Protección constitucional por características sexuales",
    "Constitutional protection based on sex characteristics",
    "Indica si existe protección constitucional frente a la discriminación por características sexuales.",
    "Indicates whether constitutional protection exists against discrimination based on sex characteristics.",
    *_criterion_aliases("Constitution", "sex characteristics"),
)
_add_criterion(
    "employment_sex_characteristics",
    "Employment (sex characteristics)",
    EQUALITY,
    "Protección laboral por características sexuales",
    "Employment protection based on sex characteristics",
    "Indica si la legislación laboral protege frente a la discriminación por características sexuales.",
    "Indicates whether employment legislation protects against discrimination based on sex characteristics.",
    *_criterion_aliases("Employment", "sex characteristics"),
)
_add_criterion(
    "goods_services_sex_characteristics",
    "Goods and services (sex characteristics)",
    EQUALITY,
    "Acceso a bienes y servicios por características sexuales",
    "Goods and services protection based on sex characteristics",
    "Indica si existe protección frente a la discriminación por características sexuales al acceder a bienes y servicios.",
    "Indicates whether protection exists against discrimination based on sex characteristics when accessing goods and services.",
    *_criterion_aliases("Goods and services", "sex characteristics"),
)
_add_criterion(
    "education_sex_characteristics",
    "Education (sex characteristics)",
    EQUALITY,
    "Protección educativa por características sexuales",
    "Education protection based on sex characteristics",
    "Indica si la legislación educativa protege frente a la discriminación por características sexuales.",
    "Indicates whether education legislation protects against discrimination based on sex characteristics.",
    *_criterion_aliases("Education", "sex characteristics"),
)
_add_criterion(
    "health_sex_characteristics",
    "Health (sex characteristics)",
    EQUALITY,
    "Protección sanitaria por características sexuales",
    "Healthcare protection based on sex characteristics",
    "Indica si existe protección frente a la discriminación por características sexuales en el ámbito sanitario.",
    "Indicates whether protection exists against discrimination based on sex characteristics in healthcare.",
    *_criterion_aliases("Health", "sex characteristics"),
)
_add_criterion(
    "equality_body_mandate_sex_characteristics",
    "Equality body mandate (sex characteristics)",
    EQUALITY,
    "Mandato del organismo de igualdad sobre características sexuales",
    "Equality body mandate on sex characteristics",
    "Indica si el organismo nacional de igualdad tiene competencias para trabajar sobre discriminación por características sexuales.",
    "Indicates whether the national equality body is mandated to address discrimination based on sex characteristics.",
    *_criterion_aliases("Equality body mandate", "sex characteristics"),
    *_criterion_aliases("Equality body", "sex characteristics"),
)
_add_criterion(
    "equality_action_plan_sex_characteristics",
    "Equality action plan (sex characteristics)",
    EQUALITY,
    "Plan de igualdad sobre características sexuales",
    "Equality action plan on sex characteristics",
    "Indica si existe un plan público con medidas específicas relacionadas con las características sexuales y los derechos de las personas intersex.",
    "Indicates whether a public action plan includes specific measures related to sex characteristics and the rights of intersex people.",
    *_criterion_aliases("Equality action plan", "sex characteristics"),
)
_add_criterion(
    "blood_donation",
    "Blood donation",
    EQUALITY,
    "Donación de sangre sin exclusiones discriminatorias",
    "Blood donation without discriminatory exclusions",
    "Indica si las normas de donación de sangre evitan exclusiones discriminatorias basadas en la orientación sexual o en el tipo de relación sexual.",
    "Indicates whether blood donation rules avoid discriminatory exclusions based on sexual orientation or type of sexual relationship.",
)

_add_criterion(
    "marriage_equality",
    "Marriage equality",
    FAMILY,
    "Matrimonio igualitario",
    "Marriage equality",
    "Indica si las parejas del mismo sexo pueden contraer matrimonio con los mismos derechos que las parejas de distinto sexo.",
    "Indicates whether same-sex couples can marry with the same rights as different-sex couples.",
)
_add_criterion(
    "registered_partnership_similar_rights",
    "Registered partnership (similar rights to marriage)",
    FAMILY,
    "Unión registrada con derechos similares al matrimonio",
    "Registered partnership with similar rights to marriage",
    "Indica si existe una unión registrada para parejas del mismo sexo con derechos similares a los del matrimonio.",
    "Indicates whether registered partnerships for same-sex couples provide rights similar to marriage.",
    "Registered partnership - similar rights to marriage",
)
_add_criterion(
    "registered_partnership_limited_rights",
    "Registered partnership (limited rights)",
    FAMILY,
    "Unión registrada con derechos limitados",
    "Registered partnership with limited rights",
    "Indica si existe una unión registrada para parejas del mismo sexo, aunque con derechos más limitados que el matrimonio.",
    "Indicates whether registered partnerships for same-sex couples exist but provide more limited rights than marriage.",
    "Registered partnership - limited rights",
)
_add_criterion(
    "cohabitation",
    "Cohabitation",
    FAMILY,
    "Reconocimiento de la convivencia",
    "Cohabitation recognition",
    "Indica si las parejas del mismo sexo que conviven disponen de algún reconocimiento o protección legal.",
    "Indicates whether cohabiting same-sex couples receive any legal recognition or protection.",
)
_add_criterion(
    "no_constitutional_limitation_on_marriage",
    "No constitutional limitation on marriage",
    FAMILY,
    "Sin limitación constitucional al matrimonio",
    "No constitutional limitation on marriage",
    "Indica que la Constitución no define el matrimonio de una forma que impida legalizar el matrimonio entre personas del mismo sexo.",
    "Indicates that the Constitution does not define marriage in a way that prevents legal recognition of same-sex marriage.",
)
_add_criterion(
    "joint_adoption",
    "Joint adoption",
    FAMILY,
    "Adopción conjunta",
    "Joint adoption",
    "Indica si una pareja del mismo sexo puede adoptar conjuntamente.",
    "Indicates whether a same-sex couple can adopt a child jointly.",
)
_add_criterion(
    "second_parent_adoption",
    "Second-parent adoption",
    FAMILY,
    "Adopción del hijo o hija de la pareja",
    "Second-parent adoption",
    "Indica si una persona puede adoptar legalmente a los hijos de su pareja del mismo sexo.",
    "Indicates whether a person can legally adopt the children of their same-sex partner.",
)
_add_criterion(
    "automatic_co_parent_recognition",
    "Automatic co-parent recognition",
    FAMILY,
    "Reconocimiento automático de la coparentalidad",
    "Automatic co-parent recognition",
    "Indica si ambas personas de una pareja son reconocidas automáticamente como progenitoras sin tener que iniciar un proceso de adopción.",
    "Indicates whether both members of a couple are automatically recognised as parents without requiring an adoption procedure.",
)
_add_criterion(
    "medically_assisted_insemination_couples",
    "Medically assisted insemination (couples)",
    FAMILY,
    "Reproducción asistida para parejas de mujeres",
    "Medically assisted reproduction for female couples",
    "Indica si las parejas formadas por mujeres pueden acceder legalmente a técnicas de reproducción asistida.",
    "Indicates whether female couples can legally access medically assisted reproduction.",
)
_add_criterion(
    "medically_assisted_insemination_singles",
    "Medically assisted insemination (singles)",
    FAMILY,
    "Reproducción asistida para mujeres sin pareja",
    "Medically assisted reproduction for single women",
    "Indica si las mujeres sin pareja pueden acceder legalmente a técnicas de reproducción asistida.",
    "Indicates whether single women can legally access medically assisted reproduction.",
)
_add_criterion(
    "recognition_of_trans_parenthood",
    "Recognition of trans parenthood",
    FAMILY,
    "Reconocimiento de la parentalidad trans",
    "Recognition of trans parenthood",
    "Indica si la documentación y la legislación reconocen correctamente la identidad de género de las personas trans que son madres, padres o progenitores.",
    "Indicates whether legislation and official documents correctly recognise the gender identity of trans parents.",
)

for _ground, _suffix, _es_ground, _en_ground, _people_es, _people_en in (
    (
        "sexual orientation",
        "sexual_orientation",
        "orientación sexual",
        "sexual orientation",
        "personas por su orientación sexual",
        "people because of their sexual orientation",
    ),
    (
        "gender identity",
        "gender_identity",
        "identidad de género",
        "gender identity",
        "personas por su identidad de género",
        "people because of their gender identity",
    ),
    (
        "sex characteristics",
        "sex_characteristics",
        "características sexuales",
        "sex characteristics",
        "personas por sus características sexuales",
        "people because of their sex characteristics",
    ),
):
    _add_criterion(
        f"hate_crime_law_{_suffix}",
        f"Hate crime law ({_ground})",
        HATE,
        f"Delitos de odio por {_es_ground}",
        f"Hate crime law based on {_en_ground}",
        f"Indica si la {_es_ground} está reconocida legalmente como una circunstancia protegida en los delitos de odio."
        if _suffix == "sexual_orientation"
        else f"Indica si la {_es_ground} está protegida expresamente en la legislación sobre delitos de odio.",
        f"Indicates whether {_en_ground} is legally recognised as a protected ground in hate crime legislation.",
        *_criterion_aliases("Hate crime law", _ground),
        *_criterion_aliases("Hate crime", _ground),
    )
    _add_criterion(
        f"hate_speech_law_{_suffix}",
        f"Hate speech law ({_ground})",
        HATE,
        f"Discursos de odio por {_es_ground}",
        f"Hate speech law based on {_en_ground}",
        f"Indica si la ley sanciona los discursos de odio dirigidos contra {_people_es}.",
        f"Indicates whether the law addresses hate speech targeting {_people_en}.",
        *_criterion_aliases("Hate speech law", _ground),
        *_criterion_aliases("Hate speech", _ground),
    )
    _add_criterion(
        f"policy_tackling_hatred_{_suffix}",
        f"Policy tackling hatred ({_ground})",
        HATE,
        f"Políticas contra el odio por {_es_ground}",
        f"Policy tackling hatred based on {_en_ground}",
        (
            "Indica si existen políticas públicas continuadas para prevenir y combatir el odio motivado por la orientación sexual."
            if _suffix == "sexual_orientation"
            else "Indica si existen políticas públicas continuadas para combatir el odio contra personas trans y de género diverso."
            if _suffix == "gender_identity"
            else "Indica si existen políticas públicas continuadas para prevenir el odio y la violencia contra las personas intersex."
        ),
        (
            "Indicates whether sustained public policies exist to prevent and combat hatred based on sexual orientation."
            if _suffix == "sexual_orientation"
            else "Indicates whether sustained public policies exist to combat hatred against trans and gender-diverse people."
            if _suffix == "gender_identity"
            else "Indicates whether sustained public policies exist to prevent hatred and violence against intersex people."
        ),
        *_criterion_aliases("Policy tackling hatred", _ground),
    )

_add_criterion(
    "no_legal_framework_making_recognition_impossible",
    "No legal framework making recognition impossible",
    LGR,
    "Marco legal que permite modificar el género registrado",
    "Legal framework allowing gender marker change",
    "Indica si el ordenamiento jurídico permite, al menos, modificar legalmente el género registrado.",
    "Indicates whether the legal framework allows a person to change their legally registered gender.",
)
_add_criterion(
    "existence_of_legal_measures",
    "Existence of legal measures",
    LGR,
    "Existencia de medidas legales",
    "Existence of legal measures",
    "Indica si existe una ley que regula el procedimiento de reconocimiento legal del género.",
    "Indicates whether legislation regulates the legal gender recognition procedure.",
)
_add_criterion(
    "existence_of_administrative_measures",
    "Existence of administrative measures",
    LGR,
    "Existencia de medidas administrativas",
    "Existence of administrative measures",
    "Indica si existen procedimientos administrativos claros para solicitar el reconocimiento legal del género.",
    "Indicates whether clear administrative procedures exist for applying for legal gender recognition.",
)
_add_criterion(
    "name_change",
    "Name change",
    LGR,
    "Cambio de nombre",
    "Name change",
    "Indica si una persona puede cambiar legalmente su nombre para que se corresponda con su identidad de género.",
    "Indicates whether a person can legally change their name to reflect their gender identity.",
)
_add_criterion(
    "no_age_restriction_name_change",
    "No age restriction (name change)",
    LGR,
    "Cambio de nombre sin restricción general de edad",
    "No age restriction for name change",
    "Indica si el cambio de nombre puede solicitarse sin una restricción general basada exclusivamente en la edad.",
    "Indicates whether a legal name change can be requested without a general restriction based solely on age.",
    "No age restriction - name change",
)
_add_criterion(
    "self_determination",
    "Self-determination",
    LGR,
    "Autodeterminación",
    "Self-determination",
    "Indica si el reconocimiento legal del género se basa en la declaración de la propia persona, sin requisitos médicos desproporcionados.",
    "Indicates whether legal gender recognition is based on the individual's self-determination without disproportionate medical requirements.",
)
_add_criterion(
    "non_binary_gender_recognition",
    "Non-binary gender recognition",
    LGR,
    "Reconocimiento de géneros no binarios",
    "Non-binary gender recognition",
    "Indica si el sistema legal permite reconocer identidades de género distintas de hombre y mujer.",
    "Indicates whether the legal system recognises gender identities beyond male and female.",
)
_add_criterion(
    "no_diagnosis_or_psychological_opinion_required",
    "No diagnosis or psychological opinion required",
    LGR,
    "Sin diagnóstico ni informe psicológico obligatorio",
    "No diagnosis or psychological opinion required",
    "Indica si no se exige un diagnóstico médico o informe psicológico para reconocer legalmente el género.",
    "Indicates whether legal gender recognition does not require a medical diagnosis or psychological opinion.",
)
_add_criterion(
    "no_compulsory_medical_intervention",
    "No compulsory medical intervention",
    LGR,
    "Sin intervención médica obligatoria",
    "No compulsory medical intervention",
    "Indica si el procedimiento no obliga a recibir tratamientos o intervenciones médicas.",
    "Indicates whether the procedure does not require medical treatment or intervention.",
)
_add_criterion(
    "no_compulsory_surgical_intervention",
    "No compulsory surgical intervention",
    LGR,
    "Sin intervención quirúrgica obligatoria",
    "No compulsory surgical intervention",
    "Indica si no se exige someterse a una intervención quirúrgica para obtener el reconocimiento legal del género.",
    "Indicates whether surgery is not required to obtain legal gender recognition.",
)
_add_criterion(
    "no_compulsory_sterilisation",
    "No compulsory sterilisation",
    LGR,
    "Sin esterilización obligatoria",
    "No compulsory sterilisation",
    "Indica si el reconocimiento legal del género no exige esterilización ni pérdida de la capacidad reproductiva.",
    "Indicates whether legal gender recognition does not require sterilisation or loss of reproductive capacity.",
)
_add_criterion(
    "no_compulsory_divorce",
    "No compulsory divorce",
    LGR,
    "Sin divorcio obligatorio",
    "No compulsory divorce",
    "Indica si una persona casada puede obtener el reconocimiento legal del género sin tener que divorciarse.",
    "Indicates whether a married person can obtain legal gender recognition without being required to divorce.",
)
_add_criterion(
    "no_age_restriction",
    "No age restriction",
    LGR,
    "Sin restricción general de edad",
    "No age restriction",
    "Indica si el procedimiento no está reservado exclusivamente a personas adultas.",
    "Indicates whether the procedure is not restricted exclusively to adults.",
)
_add_criterion(
    "procedures_for_minors",
    "Procedures for minors",
    LGR,
    "Procedimientos para menores",
    "Procedures for minors",
    "Indica si existen procedimientos de reconocimiento legal del género adaptados a menores.",
    "Indicates whether legal gender recognition procedures are available and adapted for minors.",
)
_add_criterion(
    "depathologisation",
    "Depathologisation",
    LGR,
    "Despatologización",
    "Depathologisation",
    "Indica si el reconocimiento de las identidades trans no se trata legalmente como una enfermedad o trastorno.",
    "Indicates whether trans identities are not legally treated as an illness or disorder.",
)

_add_criterion(
    "prohibition_medical_intervention_without_informed_consent",
    "Prohibition of medical intervention without informed consent",
    INTERSEX,
    "Prohibición de intervenciones médicas sin consentimiento informado",
    "Prohibition of medical intervention without informed consent",
    "Indica si están prohibidas las intervenciones médicas no necesarias sobre menores intersex cuando no existe consentimiento informado de la propia persona.",
    "Indicates whether unnecessary medical interventions on intersex minors are prohibited when the individual has not provided informed consent.",
)
_add_criterion(
    "universality_of_the_prohibition",
    "Universality of the prohibition",
    INTERSEX,
    "Universalidad de la prohibición",
    "Universality of the prohibition",
    "Indica si la prohibición protege de manera amplia a todas las personas intersex y se aplica en todos los entornos sanitarios relevantes.",
    "Indicates whether the prohibition broadly protects all intersex people and applies across relevant healthcare settings.",
)
_add_criterion(
    "effective_monitoring_mechanism",
    "Effective monitoring mechanism",
    INTERSEX,
    "Mecanismo efectivo de supervisión",
    "Effective monitoring mechanism",
    "Indica si existe un sistema efectivo para supervisar el cumplimiento de las normas que protegen la integridad corporal de las personas intersex.",
    "Indicates whether an effective mechanism monitors compliance with rules protecting the bodily integrity of intersex people.",
)
_add_criterion(
    "access_to_justice_and_reparations",
    "Access to justice and reparations",
    INTERSEX,
    "Acceso a la justicia y reparación",
    "Access to justice and reparations",
    "Indica si las víctimas de intervenciones médicas no consentidas pueden acceder a la justicia, recibir reparación y obtener compensación.",
    "Indicates whether victims of non-consensual medical interventions can access justice, remedies and compensation.",
)

_add_criterion(
    "public_event_held_without_state_obstruction",
    "Public event held without state obstruction",
    CIVIL,
    "Actos públicos sin obstrucción estatal",
    "Public event held without state obstruction",
    "Indica si se han podido celebrar actos públicos LGBTIQ+ durante los últimos tres años sin obstrucciones por parte del Estado.",
    "Indicates whether LGBTIQ+ public events have taken place during the last three years without state obstruction.",
)
_add_criterion(
    "public_event_receives_sufficient_protection",
    "Public event receives sufficient protection",
    CIVIL,
    "Protección suficiente de actos públicos",
    "Public event receives sufficient protection",
    "Indica si las autoridades ofrecen protección suficiente para que los actos públicos LGBTIQ+ puedan celebrarse con seguridad.",
    "Indicates whether authorities provide sufficient protection for LGBTIQ+ public events to take place safely.",
)
_add_criterion(
    "associations_operate_without_obstruction",
    "Associations operate without obstruction",
    CIVIL,
    "Organizaciones sin obstrucción estatal",
    "Associations operate without obstruction",
    "Indica si las organizaciones LGBTIQ+ pueden registrarse, trabajar y desarrollar sus actividades sin interferencias estatales.",
    "Indicates whether LGBTIQ+ organisations can register, operate and carry out their activities without state interference.",
)
_add_criterion(
    "human_rights_defenders_are_not_at_risk",
    "Human rights defenders are not at risk",
    CIVIL,
    "Personas defensoras sin riesgo",
    "Human rights defenders are not at risk",
    "Indica si las personas defensoras de los derechos LGBTIQ+ pueden realizar su trabajo sin sufrir amenazas, violencia o persecución.",
    "Indicates whether LGBTIQ+ human rights defenders can carry out their work without threats, violence or persecution.",
)
_add_criterion(
    "no_laws_limiting_external_funding",
    "No laws limiting external funding",
    CIVIL,
    "Sin leyes que limiten la financiación externa",
    "No laws limiting external funding",
    "Indica si las organizaciones de la sociedad civil pueden recibir financiación internacional sin restricciones discriminatorias.",
    "Indicates whether civil society organisations can receive international funding without discriminatory restrictions.",
)
_add_criterion(
    "no_laws_limiting_freedom_of_expression",
    "No laws limiting freedom of expression",
    CIVIL,
    "Sin leyes que limiten la libertad de expresión",
    "No laws limiting freedom of expression",
    "Indica si no existen leyes nacionales o locales que limiten de forma específica la expresión pública sobre cuestiones LGBTIQ+.",
    "Indicates whether national or local laws avoid specifically restricting public expression concerning LGBTIQ+ issues.",
)

for _ground, _suffix, _es_ground, _en_ground in (
    ("sexual orientation", "sexual_orientation", "orientación sexual", "sexual orientation"),
    ("gender identity", "gender_identity", "identidad de género", "gender identity"),
    (
        "sex characteristics",
        "sex_characteristics",
        "características sexuales",
        "sex characteristics",
    ),
):
    _add_criterion(
        f"asylum_law_{_suffix}",
        f"Asylum law ({_ground})",
        ASYLUM,
        f"Ley de asilo por {_es_ground}",
        f"Asylum law based on {_en_ground}",
        f"Indica si la {_es_ground} está reconocida legalmente como motivo válido para solicitar protección internacional.",
        f"Indicates whether {_en_ground} is legally recognised as a valid ground for seeking international protection.",
        *_criterion_aliases("Asylum law", _ground),
        *_criterion_aliases("Asylum", _ground),
    )
    _add_criterion(
        f"positive_asylum_measures_{_suffix}",
        f"Positive asylum measures ({_ground})",
        ASYLUM,
        f"Medidas positivas de asilo por {_es_ground}",
        f"Positive asylum measures based on {_en_ground}",
        (
            "Indica si existen medidas continuadas para atender las necesidades específicas de las personas solicitantes de asilo por motivos relacionados con su orientación sexual."
            if _suffix == "sexual_orientation"
            else "Indica si existen medidas continuadas para proteger y atender a personas trans o de género diverso durante el proceso de asilo."
            if _suffix == "gender_identity"
            else "Indica si existen políticas o medidas continuadas que atienden las necesidades y derechos específicos de las personas intersex solicitantes de asilo."
        ),
        (
            "Indicates whether sustained measures address the specific needs of asylum seekers whose claims relate to sexual orientation."
            if _suffix == "sexual_orientation"
            else "Indicates whether sustained measures protect and support trans or gender-diverse people during the asylum process."
            if _suffix == "gender_identity"
            else "Indicates whether sustained policies or measures address the specific needs and rights of intersex asylum seekers."
        ),
        *_criterion_aliases("Positive asylum measures", _ground),
    )
