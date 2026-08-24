from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class FraSurveyConfig:
    survey_id: str
    sequence: str
    year: int
    collection: str
    dataset_code: str
    source_name: str
    source_url: str
    csv_versions: tuple[str, ...]
    enabled: bool = True

    def label(self, language: str = "es") -> str:
        prefix = "Survey" if language == "en" else "Encuesta"
        return f"{prefix} {self.year}"


FRA_SURVEYS: Final[tuple[FraSurveyConfig, ...]] = (
    FraSurveyConfig(
        survey_id="fra_survey_iii",
        sequence="III",
        year=2023,
        collection="Indicator_fra",
        dataset_code="eu_lgbtiq_survey_iii",
        source_name="EU LGBTIQ Survey III",
        source_url=(
            "https://fra.europa.eu/en/publications-and-resources/data-and-maps/2024/"
            "eu-lgbtiq-survey-iii"
        ),
        csv_versions=("current_wide",),
    ),
    FraSurveyConfig(
        survey_id="fra_survey_ii",
        sequence="II",
        year=2019,
        collection="Indicator_fra_2019",
        dataset_code="eu_lgbti_survey_ii",
        source_name="EU LGBTI Survey II",
        source_url="https://fra.europa.eu/en/project/2018/eu-lgbti-survey-ii",
        csv_versions=("legacy_long",),
    ),
)

DEFAULT_FRA_SURVEY_ID: Final[str] = "fra_survey_iii"
FRA_SURVEYS_BY_ID: Final[dict[str, FraSurveyConfig]] = {
    survey.survey_id: survey for survey in FRA_SURVEYS
}
FRA_SURVEYS_BY_YEAR: Final[dict[int, FraSurveyConfig]] = {
    survey.year: survey for survey in FRA_SURVEYS
}


def default_fra_survey() -> FraSurveyConfig:
    return FRA_SURVEYS_BY_ID[DEFAULT_FRA_SURVEY_ID]


def get_fra_survey(survey_id: object) -> FraSurveyConfig | None:
    return FRA_SURVEYS_BY_ID.get(str(survey_id or "").strip())


def get_fra_survey_by_year(year: object) -> FraSurveyConfig | None:
    if isinstance(year, bool) or not isinstance(year, str | int | float):
        return None
    try:
        clean_year = int(year)
    except (TypeError, ValueError):
        return None
    return FRA_SURVEYS_BY_YEAR.get(clean_year)


def fra_collection_for_year(year: object = None) -> str | None:
    survey = default_fra_survey() if year is None else get_fra_survey_by_year(year)
    return survey.collection if survey and survey.enabled else None
