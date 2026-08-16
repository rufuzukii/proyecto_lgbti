from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import app.import_to_db.fra.indicators as indicator_catalog
from app.import_to_db.fra.payload import parse_fra_csv

FRA_2019_CSV = """sep=\t
"Question:"\t"Civil status"
"‡ = small sample size"\t
"[1]: = not available due to small sample size"\t
"Source of Data:"\t"Placeholder"
"Last update:"\t"4/1/2020"
"Hyperlink to the variable:"\t"https://example.test/survey-ii"
"General Disclaimer of the FRA website:"\t"https://example.test/terms"
"Code:"\t"DEXh4"
"Subset Value:"\t"All"
""
"CountryCode"\t"question_code"\t"question_label"\t"target_group"\t"subset"\t"answer"\t"percentage"\t"notes"
"Spain"\t"DEXh4"\t"Civil status"\t"All"\t"All"\t"Single"\t"42,3"\t""
"Germany"\t"DEXh4"\t"Civil status"\t"All"\t"All"\t"Single"\t"0"\t""
"United Kingdom"\t"DEXh4"\t"Civil status"\t"All"\t"All"\t"Single"\t":"\t" [1] "
"EU-28"\t"DEXh4"\t"Civil status"\t"All"\t"All"\t"Single"\t"42.3 %"\t""
"""


def _write_fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "Datos_FRA_2019"
    path = root / "Socio-demographics (10)" / "Civil status" / "Single" / "All" / "All"
    path.mkdir(parents=True)
    csv_path = path / "No-filters.csv"
    csv_path.write_bytes(FRA_2019_CSV.encode("cp1252"))
    return root, csv_path


def test_survey_ii_parser_preserves_metadata_codes_nulls_and_all_scope(tmp_path: Path) -> None:
    root, csv_path = _write_fixture(tmp_path)

    payload = parse_fra_csv(csv_path, root=root, survey_year=2019)

    assert isinstance(payload, dict)
    assert payload["survey_year"] == 2019
    assert payload["survey_id"] == "fra_survey_ii"
    assert payload["dataset"] == "eu_lgbti_survey_ii"
    assert payload["category"] == "Socio-demographics"
    assert payload["question_code"] == payload["indicator_id"] == "DEXh4"
    assert [answer["country_code"] for answer in payload["answers"]] == [
        "ES",
        "DE",
        "GB",
        "EU28",
    ]
    assert [answer["percentage"] for answer in payload["answers"]] == [42.3, 0, None, 42.3]
    assert {tuple(item.items()) for answer in payload["answers"] for item in answer["filters"]} == {
        (("type", "All"), ("value", "All"))
    }
    metadata = payload["metadata"]
    assert metadata["question_code"] == "DEXh4"
    assert metadata["survey_year_source"] == "explicit_survey_configuration"
    assert metadata["date"] == "4/1/2020"
    assert metadata["source"] != "Placeholder"


class _Connection:
    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def _payload(code: str, question: str) -> dict[str, Any]:
    return {
        "code": code,
        "question_code": code,
        "question": question,
        "category": "Discrimination",
        "specific_category": "Discrimination",
        "survey_year": 2019,
        "answers": [
            {
                "country": "Spain",
                "country_code": "ES",
                "answer": "Yes",
                "percentage": 42,
                "filters": [{"type": "All", "value": "All"}],
            }
        ],
    }


def test_catalog_reuses_safe_equivalence_creates_new_and_is_idempotent(monkeypatch) -> None:
    catalog = {
        "C20": {
            "code": "C20",
            "question": "Same canonical question",
            "category": "Discrimination",
        }
    }

    @contextmanager
    def connection(**_kwargs) -> Iterator[_Connection]:
        yield _Connection()

    def by_code(_conn, code: str):
        return catalog.get(code)

    def by_question(_conn, question: str, category: str):
        return [
            row
            for row in catalog.values()
            if row["question"].casefold() == question.casefold()
            and row["category"].casefold() == category.casefold()
        ]

    def upsert(_conn, document: dict[str, Any], **_kwargs) -> None:
        catalog.setdefault(
            document["code"],
            {
                "code": document["code"],
                "question": document["question"],
                "category": document["category"],
            },
        )

    monkeypatch.setattr(indicator_catalog, "postgres_connection", connection)
    monkeypatch.setattr(indicator_catalog, "_catalog_row_by_code", by_code)
    monkeypatch.setattr(indicator_catalog, "_catalog_rows_by_question", by_question)
    monkeypatch.setattr(indicator_catalog, "_upsert_indicator", upsert)

    reused, reuse_resolutions = indicator_catalog.resolve_and_upsert_indicators_from_json(
        _payload("DEXsame", "Same canonical question")
    )
    created, create_resolutions = indicator_catalog.resolve_and_upsert_indicators_from_json(
        _payload("DEXnew", "A genuinely new question")
    )
    repeated, repeat_resolutions = indicator_catalog.resolve_and_upsert_indicators_from_json(
        _payload("DEXnew", "A genuinely new question")
    )

    assert isinstance(reused, dict)
    assert isinstance(created, dict)
    assert isinstance(repeated, dict)
    assert reused["code"] == "C20"
    assert reuse_resolutions[0].action == "reused"
    assert create_resolutions[0].action == "created"
    assert repeat_resolutions[0].action == "reused"
    assert created["code"] == repeated["code"] == "DEXnew"
    assert list(catalog).count("DEXnew") == 1
