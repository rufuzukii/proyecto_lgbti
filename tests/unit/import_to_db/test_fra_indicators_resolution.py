from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.modules.imports.fra import indicators


def _document(**overrides: Any) -> dict[str, Any]:
    return {
        "code": "E1",
        "question_code": "E1",
        "question": "Workplace discrimination",
        "category": "Employment",
        "specific_category": "Work",
        "survey_year": 2023,
        "answers": [
            {"country": "Spain", "answer": "Yes", "percentage": 0.0},
            {"country": "France", "answer": "No", "percentage": 50.0},
        ],
        **overrides,
    }


def _catalog_row(code: str = "E1") -> dict[str, str]:
    return {
        "code": code,
        "question": "Workplace discrimination",
        "category": "Employment",
    }


def test_resolution_reuses_exact_code_and_rejects_incomplete_payload(monkeypatch) -> None:
    monkeypatch.setattr(indicators, "_catalog_row_by_code", lambda _conn, _code: _catalog_row())
    monkeypatch.setattr(indicators, "_catalog_rows_by_question", lambda *_args: [])

    connection = cast(Any, object())
    resolution = indicators._resolve_indicator(connection, _document())

    assert resolution.canonical_id == "E1"
    assert resolution.action == "reused"
    assert resolution.reason == "canonical_code"
    with pytest.raises(ValueError, match="invalid_indicator_payload"):
        indicators._resolve_indicator(connection, _document(question=""))
    with pytest.raises(ValueError, match="invalid_indicator_payload"):
        indicators._resolve_indicator(connection, _document(survey_year=True))


def test_resolution_uses_reviewed_mapping_and_semantic_match(monkeypatch) -> None:
    rows = {"E1": None, "OLD": _catalog_row("OLD")}
    monkeypatch.setattr(indicators, "_catalog_row_by_code", lambda _conn, code: rows.get(code))
    monkeypatch.setitem(indicators.FRA_INDICATOR_EQUIVALENCE_MAP, (2019, "E1"), "OLD")
    monkeypatch.setattr(indicators, "_catalog_rows_by_question", lambda *_args: [])

    connection = cast(Any, object())
    mapped = indicators._resolve_indicator(connection, _document(survey_year=2019))

    assert (mapped.canonical_id, mapped.reason) == ("OLD", "explicit_mapping")

    monkeypatch.delitem(indicators.FRA_INDICATOR_EQUIVALENCE_MAP, (2019, "E1"))
    monkeypatch.setattr(
        indicators,
        "_catalog_rows_by_question",
        lambda *_args: [_catalog_row("CANONICAL"), {**_catalog_row("wrong"), "category": "Other"}],
    )
    semantic = indicators._resolve_indicator(connection, _document())
    assert (semantic.canonical_id, semantic.reason) == (
        "CANONICAL",
        "exact_normalized_question_category",
    )


def test_resolution_creates_collision_safe_code_or_reuses_existing_canonical(monkeypatch) -> None:
    rows: dict[str, dict[str, str] | None] = {
        "E-1": {**_catalog_row("E-1"), "question": "Different"},
        "fra_2023_E_1": None,
    }
    monkeypatch.setattr(indicators, "_catalog_row_by_code", lambda _conn, code: rows.get(code))
    monkeypatch.setattr(indicators, "_catalog_rows_by_question", lambda *_args: [])

    connection = cast(Any, object())
    created = indicators._resolve_indicator(connection, _document(code="E-1", question_code="E-1"))
    assert (created.canonical_id, created.action, created.reason) == (
        "fra_2023_E_1",
        "created",
        "question_code_collision",
    )

    rows["fra_2023_E_1"] = _catalog_row("fra_2023_E_1")
    reused = indicators._resolve_indicator(connection, _document(code="E-1", question_code="E-1"))
    assert (reused.action, reused.reason) == ("reused", "canonical_code")


class _Connection:
    def __init__(self, indicator_row: dict[str, Any] | None) -> None:
        self.indicator_row = indicator_row
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []

    def execute(self, query: str, params=None):
        self.calls.append((" ".join(query.split()), params))
        if "SELECT answer_type" in query:
            return SimpleNamespace(fetchone=lambda: self.indicator_row)
        return SimpleNamespace(fetchone=lambda: None)


def test_indicator_upsert_inserts_new_catalog_row(monkeypatch) -> None:
    connection = _Connection(None)
    monkeypatch.setattr(indicators, "_get_or_create_category", lambda _conn, _name: "cat-1")

    indicators._upsert_indicator(cast(Any, connection), _document())

    insert = next(call for call in connection.calls if "INSERT INTO public.indicators" in call[0])
    params = insert[1]
    assert params is not None
    assert params[0:3] == ("cat-1", "E1", "Workplace discrimination")
    assert json.loads(params[4]) == ["Yes", "No"]


@pytest.mark.parametrize("preserve_existing", [False, True])
def test_indicator_upsert_merges_answer_types_for_updates(
    monkeypatch, preserve_existing: bool
) -> None:
    connection = _Connection({"answer_type": '["Maybe"]'})
    monkeypatch.setattr(indicators, "_get_or_create_category", lambda _conn, _name: "cat-1")

    indicators._upsert_indicator(
        cast(Any, connection),
        _document(),
        preserve_existing=preserve_existing,
    )

    update = next(call for call in connection.calls if "UPDATE public.indicators" in call[0])
    params = update[1]
    assert params is not None
    serialized = params[0] if preserve_existing else params[3]
    assert json.loads(serialized) == ["Maybe", "Yes", "No"]


def test_indicator_upsert_rejects_non_statistical_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        indicators,
        "_get_or_create_category",
        lambda *_args: pytest.fail("invalid payload must not reach persistence"),
    )
    with pytest.raises(ValueError, match="invalid_indicator_payload"):
        indicators._upsert_indicator(cast(Any, _Connection(None)), _document(answers=[]))


def test_answer_type_and_nested_question_helpers_cover_legacy_shapes() -> None:
    nested = {
        "topic": "Employment",
        "category": "Work",
        "questions": [
            {"question": "One", "answers": [{"answer": " Yes "}, {"answer": "Yes"}]},
            {"question": "Two", "answers": [{"answer": 0}, {"answer": None}, "bad"]},
        ],
    }

    assert indicators._resolve_category(nested) == "Employment"
    assert indicators._resolve_specific_category(nested) == "Work"
    assert indicators._indicator_payload(nested)["question"] == "One"
    assert indicators._extract_answer_types(nested) == ["Yes", "0"]
    assert indicators._parse_answer_type("Yes, No") == ["Yes", "No"]
    assert indicators._parse_answer_type('"Yes"') == ["Yes"]
    assert indicators._parse_answer_type(None) == []
    assert indicators._merge_answer_types('["Yes"]', ["Yes", "No"]) == ["Yes", "No"]


def test_document_normalization_rejects_malformed_question_lists() -> None:
    assert indicators._normalize_documents({"code": "E1", "answers": []}) == [
        {"code": "E1", "answers": []}
    ]
    assert indicators._normalize_documents({"plain": True}) == [{"plain": True}]
    with pytest.raises(ValueError, match="invalid_indicator_payload"):
        indicators._normalize_documents({"questions": [{"code": "E1"}, "bad"]})
    with pytest.raises(ValueError, match="invalid_indicator_payload"):
        indicators._normalize_documents([])
    with pytest.raises(ValueError, match="invalid_indicator_payload"):
        indicators._normalize_documents([{"code": "E1"}, "bad"])
