from __future__ import annotations

from typing import Any

from app.analytics import repository
from app.fra_surveys import (
    DEFAULT_FRA_SURVEY_ID,
    FRA_SURVEYS,
    fra_collection_for_year,
    get_fra_survey,
)


def test_fra_survey_registry_separates_ui_identity_year_and_collection() -> None:
    mapping = {
        survey.survey_id: (survey.sequence, survey.year, survey.collection)
        for survey in FRA_SURVEYS
    }

    assert DEFAULT_FRA_SURVEY_ID == "fra_survey_iii"
    assert mapping == {
        "fra_survey_iii": ("III", 2023, "Indicator_fra"),
        "fra_survey_ii": ("II", 2019, "Indicador_fra_2019"),
        "fra_survey_i": ("I", 2012, "Indicador_fra_2013"),
    }
    assert get_fra_survey("Indicador_fra_2013") is None


def test_unknown_fra_year_has_no_2023_fallback() -> None:
    assert fra_collection_for_year(2023) == "Indicator_fra"
    assert fra_collection_for_year(2019) == "Indicador_fra_2019"
    assert fra_collection_for_year(2012) == "Indicador_fra_2013"
    assert fra_collection_for_year(2013) is None
    assert fra_collection_for_year(2020) is None


def test_repository_queries_only_the_collection_for_the_requested_survey(monkeypatch) -> None:
    requested: list[str] = []

    class EmptyCollection:
        def distinct(self, _field: str, _query: dict[str, Any]) -> list[str]:
            return []

    def collection(name: str) -> EmptyCollection:
        requested.append(name)
        return EmptyCollection()

    monkeypatch.setattr(repository, "_mongo_collection", collection)

    assert repository.get_fra_categories.uncached(2019) == []
    assert requested == ["Indicador_fra_2019"]
    requested.clear()
    assert repository.get_fra_categories.uncached(2012) == []
    assert requested == ["Indicador_fra_2013"]
    requested.clear()
    assert repository.get_fra_categories.uncached(2020) == []
    assert requested == []
