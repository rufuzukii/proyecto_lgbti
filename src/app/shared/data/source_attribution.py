from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from app.shared.data.fra_surveys import FRA_SURVEYS as FRA_SURVEY_CONFIGS

SourceKey = Literal["fra", "ilga", "felgtbi"]

PROCESSED_BY = "RainbowLens Datahub"
REUSE_CONDITIONS_ES = "Consultar condiciones de reutilización de la fuente original"
REUSE_CONDITIONS_EN = "Consult the reuse terms of the original source"

FRA_ORGANIZATION = "European Union Agency for Fundamental Rights (FRA)"
ILGA_ORGANIZATION = "ILGA-Europe"
FELGTBI_ORGANIZATION = (
    "Federación Estatal de Lesbianas, Gais, Trans, Bisexuales, Intersexuales y más — FELGTBI+"
)

FRA_SURVEYS: dict[int, tuple[str, str]] = {
    survey.year: (survey.source_name, survey.source_url) for survey in FRA_SURVEY_CONFIGS
}

FRA_ORGANIZATION_URL = "https://fra.europa.eu/en"
FRA_URL = FRA_SURVEYS[2023][1]
ILGA_URL = "https://www.ilga-europe.org/"
ILGA_RAINBOW_MAP_URL = "https://rainbowmap.ilga-europe.org"
ILGA_ANNUAL_REVIEW_URL = "https://www.ilga-europe.org/report/annual-review-2026/"
ILGA_ANNUAL_REVIEW_2026_PDF_URL = (
    "https://www.ilga-europe.org/files/uploads/2026/02/2026-ILGA-EUROPE-ANNUAL-REVIEW.pdf"
)
FELGTBI_URL = "https://felgtbi.org/"
FELGTBI_REPORTS_URL = "https://felgtbi.org/que-hacemos/investigacion/estado-lgtbi/"


@dataclass(frozen=True)
class SourceLink:
    label_es: str
    label_en: str
    url: str


@dataclass(frozen=True)
class SourceAttributionMetadata:
    key: SourceKey
    source_organization: str
    source_name: str
    source_url: str
    source_document: str = ""
    source_year: int | None = None
    source_figure: str = ""
    source_accessed_at: str = ""
    source_license: str = ""
    source_attribution_es: str = ""
    source_attribution_en: str = ""
    source_disclaimer_es: str = ""
    source_disclaimer_en: str = ""
    compact_attribution_es: str = ""
    compact_attribution_en: str = ""
    processed_by: str = PROCESSED_BY
    last_updated_es: str = ""
    last_updated_en: str = ""
    description_es: str = ""
    description_en: str = ""
    official_links: tuple[SourceLink, ...] = ()

    def attribution(self, language: str = "es", *, compact: bool = False) -> str:
        english = language == "en"
        if compact:
            return self.compact_attribution_en if english else self.compact_attribution_es
        return self.source_attribution_en if english else self.source_attribution_es

    def disclaimer(self, language: str = "es") -> str:
        return self.source_disclaimer_en if language == "en" else self.source_disclaimer_es

    def storage_fields(self) -> dict[str, Any]:
        return {
            "source_organization": self.source_organization,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "source_document": self.source_document,
            "source_year": self.source_year,
            "source_figure": self.source_figure,
            "source_accessed_at": self.source_accessed_at,
            "source_license": self.source_license,
            "source_attribution": self.source_attribution_es,
            "source_disclaimer": self.source_disclaimer_es,
            "processed_by": self.processed_by,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def source_metadata(
    source: str,
    *,
    year: int | None = None,
    source_name: str | None = None,
    source_url: str | None = None,
    source_document: str | None = None,
    source_figure: str | None = None,
    accessed_at: str | None = None,
) -> SourceAttributionMetadata:
    key = normalize_source_key(source)
    metadata = _base_metadata(key, year=year)
    return replace(
        metadata,
        source_name=source_name or metadata.source_name,
        source_url=source_url or metadata.source_url,
        source_document=source_document or metadata.source_document,
        source_figure=source_figure or metadata.source_figure,
        source_accessed_at=accessed_at or metadata.source_accessed_at,
    )


def source_storage_fields(
    source: str,
    *,
    year: int | None = None,
    source_name: str | None = None,
    source_url: str | None = None,
    source_document: str | None = None,
    source_figure: str | None = None,
    accessed_at: str | None = None,
) -> dict[str, Any]:
    return source_metadata(
        source,
        year=year,
        source_name=source_name,
        source_url=source_url,
        source_document=source_document,
        source_figure=source_figure,
        accessed_at=accessed_at,
    ).storage_fields()


def attribution_for_sources(
    sources: list[str] | tuple[str, ...] | set[str],
    *,
    language: str = "es",
    year: int | None = None,
    compact: bool = False,
) -> list[str]:
    ordered: list[SourceKey] = []
    for source in sources:
        key = normalize_source_key(source)
        if key not in ordered:
            ordered.append(key)
    return [
        source_metadata(key, year=year).attribution(language, compact=compact) for key in ordered
    ]


def normalize_source_key(source: str) -> SourceKey:
    value = str(source or "").strip().casefold()
    if "felgtbi" in value or "felgtb" in value:
        return "felgtbi"
    if "ilga" in value or "rainbow map" in value:
        return "ilga"
    if "fra" in value or "lgbtiq survey" in value or "lgbti survey" in value:
        return "fra"
    raise ValueError(f"Unsupported source attribution: {source}")


def _base_metadata(source: SourceKey, *, year: int | None) -> SourceAttributionMetadata:
    if source == "fra":
        return _fra_metadata(year)
    if source == "ilga":
        return _ilga_metadata(year)
    return _felgtbi_metadata(year)


def _fra_metadata(year: int | None) -> SourceAttributionMetadata:
    # Survey III was conducted in 2023 and published in 2024. Analytics uses
    # the publication year, so both values identify the same source document.
    survey_year = 2023 if year == 2024 else year
    survey = FRA_SURVEYS.get(survey_year or 0)
    if survey:
        survey_name, survey_url = survey
        attribution_es = (
            f"Fuente: {FRA_ORGANIZATION}, {survey_name}, {survey_year}. Datos procesados y "
            f"visualizados por {PROCESSED_BY}. La FRA no participa en esta adaptación."
        )
        attribution_en = (
            f"Source: {FRA_ORGANIZATION}, {survey_name}, {survey_year}. Data processed and "
            f"visualised by {PROCESSED_BY}. FRA is not involved in this adaptation."
        )
        source_name = survey_name
        source_document = f"{survey_name}, {survey_year}"
        source_url = survey_url
    else:
        attribution_es = (
            f"Fuente: {FRA_ORGANIZATION}, EU LGBTI/LGBTIQ Surveys 2019 y 2023. "
            f"Datos procesados y visualizados por {PROCESSED_BY}. La FRA no "
            "participa en esta adaptación."
        )
        attribution_en = (
            f"Source: {FRA_ORGANIZATION}, EU LGBTI/LGBTIQ Surveys 2019 and 2023. "
            f"Data processed and visualised by {PROCESSED_BY}. FRA is not involved "
            "in this adaptation."
        )
        source_name = "EU LGBT/LGBTI/LGBTIQ Surveys"
        source_document = "EU LGBTI/LGBTIQ Surveys 2019 and 2023"
        source_url = FRA_URL
    return SourceAttributionMetadata(
        key="fra",
        source_organization=FRA_ORGANIZATION,
        source_name=source_name,
        source_url=source_url,
        source_document=source_document,
        source_year=survey_year if survey else None,
        source_license=REUSE_CONDITIONS_ES,
        source_attribution_es=attribution_es,
        source_attribution_en=attribution_en,
        source_disclaimer_es="La FRA no participa en esta adaptación ni respalda RainbowLens Datahub.",
        source_disclaimer_en="FRA is not involved in this adaptation and does not endorse RainbowLens Datahub.",
        compact_attribution_es=(
            f"Fuente: FRA, {source_name}{f', {survey_year}' if survey else ''}. Datos adaptados y "
            f"visualizados por {PROCESSED_BY}."
        ),
        compact_attribution_en=(
            f"Source: FRA, {source_name}{f', {survey_year}' if survey else ''}. Data adapted and "
            f"visualised by {PROCESSED_BY}."
        ),
        last_updated_es="Encuesta utilizada más reciente: 2023. Resultados publicados en 2024.",
        last_updated_en="Most recent survey used: 2023. Results published in 2024.",
        description_es=(
            "Datos de encuesta sobre experiencias, discriminación, seguridad, condiciones "
            "de vida y derechos de las personas LGBTIQ+ en Europa."
        ),
        description_en=(
            "Survey data on experiences, discrimination, safety, living conditions and "
            "rights of LGBTIQ+ people in Europe."
        ),
        official_links=tuple(
            SourceLink(f"Encuesta FRA {survey_year}", f"FRA Survey {survey_year}", url)
            for survey_year, (_name, url) in FRA_SURVEYS.items()
        ),
    )


def _ilga_metadata(year: int | None) -> SourceAttributionMetadata:
    year_label = f" {year}" if year else ""
    full_es = (
        "Los datos legales y las puntuaciones mostradas en este apartado se basan en "
        "ILGA-Europe's Rainbow Map y en sus publicaciones anuales. Agradecemos a "
        "ILGA-Europe su labor de recopilación, análisis y difusión de información sobre "
        "la situación de los derechos LGBTIQ+ en Europa. Los datos han sido procesados y "
        f"adaptados para su visualización en {PROCESSED_BY}. {PROCESSED_BY} no está "
        "afiliada ni representa oficialmente a ILGA-Europe."
    )
    full_en = (
        "The legal data and scores shown in this section are based on ILGA-Europe's "
        "Rainbow Map and its annual publications. We thank ILGA-Europe for its work "
        "collecting, analysing and sharing information on the situation of LGBTIQ+ rights "
        "in Europe. The data have been processed and adapted for visualisation in "
        f"{PROCESSED_BY}. {PROCESSED_BY} is not affiliated with and does not officially "
        "represent ILGA-Europe."
    )
    return SourceAttributionMetadata(
        key="ilga",
        source_organization=ILGA_ORGANIZATION,
        source_name=f"ILGA-Europe's Rainbow Map{year_label}",
        source_url=ILGA_RAINBOW_MAP_URL,
        source_document=f"Rainbow Map{year_label}",
        source_year=year,
        source_license=REUSE_CONDITIONS_ES,
        source_attribution_es=full_es,
        source_attribution_en=full_en,
        source_disclaimer_es=(
            f"{PROCESSED_BY} no está afiliada ni representa oficialmente a ILGA-Europe."
        ),
        source_disclaimer_en=(
            f"{PROCESSED_BY} is not affiliated with and does not officially represent ILGA-Europe."
        ),
        compact_attribution_es=(
            f"Fuente: ILGA-Europe's Rainbow Map{year_label}. Datos adaptados y visualizados "
            f"por {PROCESSED_BY}."
        ),
        compact_attribution_en=(
            f"Source: ILGA-Europe's Rainbow Map{year_label}. Data adapted and visualised "
            f"by {PROCESSED_BY}."
        ),
        last_updated_es=(
            f"Datos utilizados actualizados a {year}."
            if year
            else "La edición se indica en cada visualización."
        ),
        last_updated_en=(
            f"Data used updated to {year}."
            if year
            else "The edition is identified in each visualisation."
        ),
        description_es=(
            "Puntuaciones, rankings, criterios jurídicos y contexto anual sobre leyes y "
            "políticas que afectan a las personas LGBTIQ+ en Europa."
        ),
        description_en=(
            "Scores, rankings, legal criteria and annual context on laws and policies "
            "affecting LGBTIQ+ people in Europe."
        ),
        official_links=(
            SourceLink("ILGA-Europe", "ILGA-Europe", ILGA_URL),
            SourceLink("Rainbow Map", "Rainbow Map", ILGA_RAINBOW_MAP_URL),
            SourceLink("Annual Review", "Annual Review", ILGA_ANNUAL_REVIEW_URL),
        ),
    )


def _felgtbi_metadata(year: int | None) -> SourceAttributionMetadata:
    year_label = f" {year}" if year else ""
    attribution_es = (
        f"Fuente: {FELGTBI_ORGANIZATION}. Contenido procesado y adaptado para su "
        f"visualización en {PROCESSED_BY}. {PROCESSED_BY} no está afiliada ni representa "
        "oficialmente a FELGTBI+."
    )
    attribution_en = (
        f"Source: {FELGTBI_ORGANIZATION}. Content processed and adapted for visualisation "
        f"in {PROCESSED_BY}. {PROCESSED_BY} is not affiliated with and does not officially "
        "represent FELGTBI+."
    )
    return SourceAttributionMetadata(
        key="felgtbi",
        source_organization=FELGTBI_ORGANIZATION,
        source_name=f"Estado LGTBI+{year_label}".strip(),
        source_url=FELGTBI_REPORTS_URL,
        source_document=f"Estado LGTBI+{year_label}".strip(),
        source_year=year,
        source_license=REUSE_CONDITIONS_ES,
        source_attribution_es=attribution_es,
        source_attribution_en=attribution_en,
        source_disclaimer_es=(
            f"{PROCESSED_BY} no está afiliada ni representa oficialmente a FELGTBI+."
        ),
        source_disclaimer_en=(
            f"{PROCESSED_BY} is not affiliated with and does not officially represent FELGTBI+."
        ),
        compact_attribution_es=(
            f"Fuente: FELGTBI+{f', Estado LGTBI+ {year}' if year else ''}. Contenido "
            f"adaptado por {PROCESSED_BY}."
        ),
        compact_attribution_en=(
            f"Source: FELGTBI+{f', Estado LGTBI+ {year}' if year else ''}. Content adapted "
            f"by {PROCESSED_BY}."
        ),
        last_updated_es=(
            f"Publicaciones utilizadas actualizadas a {year}."
            if year
            else "La fecha se indica en cada informe utilizado."
        ),
        last_updated_en=(
            f"Publications used updated to {year}."
            if year
            else "The date is identified in each report used."
        ),
        description_es=(
            "Informes, textos, cifras y figuras publicados por FELGTBI+ sobre la situación "
            "social de las personas LGTBI+ en España."
        ),
        description_en=(
            "Reports, text, figures and charts published by FELGTBI+ on the social "
            "situation of LGTBI+ people in Spain."
        ),
        official_links=(
            SourceLink("FELGTBI+", "FELGTBI+", FELGTBI_URL),
            SourceLink("Informes Estado LGTBI+", "Estado LGTBI+ reports", FELGTBI_REPORTS_URL),
        ),
    )
