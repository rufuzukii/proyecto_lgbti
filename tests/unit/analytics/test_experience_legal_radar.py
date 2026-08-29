from __future__ import annotations

from typing import Any

from app.modules.statistics.models import ExperienceLegalRadarQuery
from app.modules.statistics.service import (
    RADAR_MAPPING_VERSION,
    get_experience_legal_radar,
)
from app.shared.data import repository


def _fra_document(code: str, answer: str, percentage: float) -> dict[str, Any]:
    return {
        "code": code,
        "category": "Radar",
        "question": code,
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": answer,
                "percentage": percentage,
                "date": "2024",
                "filters": [{"type": "All", "value": "All"}],
            }
        ],
    }


def test_radar_fra_repository_uses_one_in_query_and_merges_duplicate_documents(
    monkeypatch,
) -> None:
    calls: list[tuple[dict[str, Any], dict[str, int]]] = []

    class Collection:
        def find(self, query: dict[str, Any], projection: dict[str, int]):
            calls.append((query, projection))
            return [
                _fra_document("D1_1", "Yes", 20),
                _fra_document("D1_1", "No", 80),
                _fra_document("G16", "Very good", 65),
            ]

    monkeypatch.setattr(repository, "_mongo_collection", lambda _name: Collection())

    documents = repository.get_fra_indicator_documents.__wrapped__(("G16", "D1_1"), 2023)

    assert len(calls) == 1
    assert calls[0][0] == {
        "code": {"$in": ["D1_1", "G16"]},
        "survey_year": 2023,
    }
    assert [document["code"] for document in documents] == ["D1_1", "G16"]
    assert len(documents[0]["answers"]) == 2


def test_radar_service_batches_queries_and_applies_only_explicit_inversions(
    monkeypatch,
) -> None:
    calls = {"fra": 0, "ilga": 0}
    documents = [
        _fra_document("D1_1", "YES", 80),
        _fra_document("D1_2_f", "yes", 70),
        _fra_document("C9_E", "Never", 60),
        _fra_document("C9_C", "never", 80),
        _fra_document("G16", "Very good", 65),
        _fra_document("C20_Any_EB", "Yes", 55),
    ]

    def load_fra(codes: tuple[str, ...], year: int | None) -> list[dict[str, Any]]:
        calls["fra"] += 1
        assert year == 2024
        assert set(codes) == {"D1_1", "D1_2_f", "C9_E", "C9_C", "G16", "C20_Any_EB"}
        return documents

    def load_ilga(_year: int | None) -> dict[str, Any]:
        calls["ilga"] += 1
        return {
            "year": 2026,
            "countries": [
                {
                    "country": "Spain",
                    "country_code": "ES",
                    "ranking": 75,
                    "criteria": [
                        {
                            "category": "Equality & non-discrimination",
                            "indicator": indicator,
                            "value": value,
                            "weight": 1,
                        }
                        for indicator, value in (
                            ("Employment coverage", 0.8),
                            ("Goods & services coverage", 0.7),
                            ("Education coverage", 0.6),
                            ("Health coverage", 0.5),
                            ("Equality body mandate coverage", 0.9),
                        )
                    ],
                }
            ],
        }

    monkeypatch.setattr("app.modules.statistics.service.get_fra_indicator_documents", load_fra)
    monkeypatch.setattr("app.modules.statistics.service.get_ilga_document_by_year", load_ilga)
    monkeypatch.setattr("app.modules.statistics.service._server_cache_get", lambda _key: None)
    monkeypatch.setattr(
        "app.modules.statistics.service._server_cache_set", lambda _key, _value: None
    )

    result = get_experience_legal_radar(ExperienceLegalRadarQuery(fra_year=2024, ilga_year=2026))
    rows = {row["dimension"]: row for row in result["rows"]}

    assert calls == {"fra": 1, "ilga": 1}
    assert result["mapping_version"] == RADAR_MAPPING_VERSION
    assert rows["equal_treatment"]["experience_score"] == 20
    assert rows["goods_services"]["experience_score"] == 30
    assert rows["education"]["experience_score"] == 70
    assert rows["health"]["experience_score"] == 65
    assert rows["equality_bodies"]["experience_score"] == 55
    assert rows["health"]["legal_score"] == 50
    assert result["fra_year"] == 2024
    assert result["ilga_year"] == 2026


def test_radar_service_does_not_turn_missing_scores_into_zero(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.statistics.service.get_fra_indicator_documents",
        lambda _codes, _year: [_fra_document("D1_1", "Yes", 20)],
    )
    monkeypatch.setattr(
        "app.modules.statistics.service.get_ilga_document_by_year",
        lambda _year: {
            "year": 2026,
            "countries": [
                {
                    "country": "Spain",
                    "country_code": "ES",
                    "ranking": 75,
                    "criteria": [],
                }
            ],
        },
    )
    monkeypatch.setattr("app.modules.statistics.service._server_cache_get", lambda _key: None)
    monkeypatch.setattr(
        "app.modules.statistics.service._server_cache_set", lambda _key, _value: None
    )

    result = get_experience_legal_radar(ExperienceLegalRadarQuery())

    assert result["status"] == "empty"
    assert result["rows"] == []
