from __future__ import annotations

import json
from pathlib import Path

from app.import_to_db.ilga import historical
from app.import_to_db.ilga.mongo import IlgaWriteOutcome, IlgaWriteSummary


def _write_payload(
    path: Path,
    *,
    year: int,
    code: str = "ES",
    value: float = 75,
) -> None:
    path.write_text(
        json.dumps(
            {
                "year": year,
                "dataset": "ilga_rainbow_map",
                "countries": [
                    {"country": "Spain", "country_code": code, "criteria": value}
                ],
            }
        ),
        encoding="utf-8",
    )


def test_historical_loader_uses_importer_and_never_passes_2026_to_persistence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_payload(tmp_path / "rainbow-map-2011.json", year=2011, value=79.17)
    _write_payload(tmp_path / "rainbow-map-2026.json", year=2026, value=77)
    parsed_files: list[str] = []
    real_parser = historical.parse_ilga_json

    def tracked_parser(path: Path):
        parsed_files.append(path.name)
        return real_parser(path)

    captured_documents: list[dict] = []

    def fake_write(documents):
        captured_documents.extend(documents)
        return IlgaWriteSummary((IlgaWriteOutcome(2011, 1, "inserted"),))

    monkeypatch.setattr(historical, "parse_ilga_json", tracked_parser)
    monkeypatch.setattr(historical, "ensure_ilga_unique_index", lambda: None)
    monkeypatch.setattr(historical, "write_indicator_ilga_json", fake_write)
    monkeypatch.setattr(historical, "_invalidate_ilga_caches", lambda: True)

    summary = historical.import_ilga_historical_directory(tmp_path)

    assert parsed_files == ["rainbow-map-2011.json"]
    assert [document["year"] for document in captured_documents] == [2011]
    assert captured_documents[0]["countries"][0]["ranking"] == 79.17
    assert summary.cache_invalidated is True
    rows = {row.year: row for row in summary.rows}
    assert rows[2011].inserted == 1
    assert rows[2011].normalized is True
    assert rows[2026].status == "Omitido"
    assert rows[2026].skipped == 1


def test_historical_loader_reports_validation_error_without_writing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_payload(tmp_path / "rainbow-map-2019.json", year=2019, code="ZZ")
    writes: list[object] = []
    monkeypatch.setattr(historical, "write_indicator_ilga_json", writes.append)

    summary = historical.import_ilga_historical_directory(tmp_path)

    assert writes == []
    assert summary.rows[0].status == "Error"
    assert "country[0].invalid_country_code:ZZ" in summary.rows[0].errors


def test_ilga_cache_invalidation_covers_analytics_and_trends(monkeypatch) -> None:
    events: list[str] = []
    monkeypatch.setattr(historical.cache, "app", object(), raising=False)
    monkeypatch.setattr(
        historical,
        "invalidate_analytics_cache",
        lambda source: events.append(f"analytics:{source}"),
    )

    assert historical._invalidate_ilga_caches() is True
    assert events == ["analytics:ilga"]
