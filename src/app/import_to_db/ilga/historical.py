from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from flask import Flask

from app.analytics.repository import invalidate_analytics_cache
from app.cache import cache, init_cache
from app.import_to_db.ilga.importer import (
    IlgaValidationError,
    extract_ilga_year,
    parse_ilga_json,
)
from app.import_to_db.ilga.mongo import IlgaWriteOutcome, write_indicator_ilga_json
from app.mongo_indexes import ensure_ilga_unique_index

logger = logging.getLogger(__name__)
PROTECTED_ILGA_YEAR = 2026


@dataclass(frozen=True)
class HistoricalImportRow:
    year: int | None
    file_name: str
    countries: int
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    normalized: bool = False
    status: str = "pending"
    errors: tuple[str, ...] = ()
    differences: tuple[str, ...] = ()


@dataclass(frozen=True)
class HistoricalImportSummary:
    source_directory: Path
    rows: tuple[HistoricalImportRow, ...]
    cache_invalidated: bool = False

    @property
    def inserted_documents(self) -> int:
        return sum(row.status == "OK" and row.inserted > 0 for row in self.rows)


def import_ilga_historical_directory(
    source_directory: Path | str,
    *,
    dry_run: bool = False,
) -> HistoricalImportSummary:
    """Validate each source JSON through the ILGA importer and persist one bulk batch."""
    directory = Path(source_directory).expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"ilga_source_directory_not_found:{directory}")
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise ValueError("ilga_json_files_not_found")

    rows: list[HistoricalImportRow] = []
    documents_by_year: dict[int, dict[str, Any]] = {}
    row_by_year: dict[int, int] = {}
    for path in paths:
        raw_year, raw_countries, detection_errors = _detect_file_identity(path)
        if raw_year == PROTECTED_ILGA_YEAR:
            logger.info(
                "ilga_import_skipped year=2026 reason=already_manually_imported"
            )
            rows.append(
                HistoricalImportRow(
                    year=raw_year,
                    file_name=path.name,
                    countries=raw_countries,
                    skipped=raw_countries,
                    status="Omitido",
                )
            )
            continue
        if detection_errors:
            logger.error(
                "ilga_import_validation_failed file=%s errors=%s",
                path.name,
                ",".join(detection_errors),
            )
            rows.append(
                HistoricalImportRow(
                    year=raw_year,
                    file_name=path.name,
                    countries=raw_countries,
                    status="Error",
                    errors=detection_errors,
                )
            )
            continue
        try:
            parsed = parse_ilga_json(path)
            if not isinstance(parsed, dict):
                raise IlgaValidationError(["annual_file_must_contain_one_document"])
        except IlgaValidationError as exc:
            logger.error(
                "ilga_import_validation_failed file=%s year=%s errors=%s",
                path.name,
                raw_year,
                ",".join(exc.errors),
            )
            rows.append(
                HistoricalImportRow(
                    year=raw_year,
                    file_name=path.name,
                    countries=raw_countries,
                    status="Error",
                    errors=exc.errors,
                )
            )
            continue

        year = int(parsed["year"])
        countries = len(parsed["countries"])
        logger.info("ilga_import_started year=%s countries=%s", year, countries)
        if year in documents_by_year:
            error = (f"duplicate_year_file:{year}",)
            previous_index = row_by_year[year]
            rows[previous_index] = replace(
                rows[previous_index],
                status="Error",
                errors=error,
            )
            rows.append(
                HistoricalImportRow(
                    year=year,
                    file_name=path.name,
                    countries=countries,
                    normalized=bool(parsed["normalization"]["applied"]),
                    status="Error",
                    errors=error,
                )
            )
            documents_by_year.pop(year, None)
            continue
        row_by_year[year] = len(rows)
        documents_by_year[year] = parsed
        rows.append(
            HistoricalImportRow(
                year=year,
                file_name=path.name,
                countries=countries,
                normalized=bool(parsed["normalization"]["applied"]),
                status="Validado" if dry_run else "pending",
            )
        )

    valid_documents = list(documents_by_year.values())
    cache_invalidated = False
    if valid_documents and not dry_run:
        ensure_ilga_unique_index()
        write_summary = write_indicator_ilga_json(valid_documents)
        outcomes = {outcome.year: outcome for outcome in write_summary.outcomes}
        rows = [
            _apply_write_outcome(
                row,
                outcomes.get(row.year) if row.year is not None else None,
            )
            for row in rows
        ]
        if write_summary.inserted_documents:
            cache_invalidated = _invalidate_ilga_caches()

    for row in rows:
        if row.status != "OK":
            continue
        logger.info(
            "ilga_import_completed year=%s countries=%s inserted=%s updated=%s skipped=%s "
            "normalized_source_scale=%s",
            row.year,
            row.countries,
            row.inserted,
            row.updated,
            row.skipped,
            str(row.normalized).lower(),
        )
    return HistoricalImportSummary(
        source_directory=directory,
        rows=tuple(sorted(rows, key=lambda row: (row.year or 0, row.file_name))),
        cache_invalidated=cache_invalidated,
    )


def _detect_file_identity(path: Path) -> tuple[int | None, int, tuple[str, ...]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, 0, (f"invalid_json:{exc}",)
    if not isinstance(payload, dict):
        return None, 0, ("annual_file_must_contain_one_document",)
    raw_year = payload.get("year")
    year = raw_year if isinstance(raw_year, int) and not isinstance(raw_year, bool) else None
    countries = payload.get("countries")
    country_count = len(countries) if isinstance(countries, list) else 0
    errors: list[str] = []
    if year is None:
        errors.append("missing_year" if raw_year is None else "invalid_year")
    file_year = extract_ilga_year(path.name)
    if year is not None and file_year is not None and year != file_year:
        errors.append(f"filename_year_mismatch:{file_year}")
    return year, country_count, tuple(errors)


def _apply_write_outcome(
    row: HistoricalImportRow,
    outcome: IlgaWriteOutcome | None,
) -> HistoricalImportRow:
    if row.status != "pending" or outcome is None:
        return row
    if outcome.status == "inserted":
        return replace(row, inserted=outcome.countries, status="OK")
    if outcome.status == "existing_equal":
        return replace(row, skipped=outcome.countries, status="Ya existente")
    return replace(
        row,
        skipped=outcome.countries,
        status="Diferente; no modificado",
        differences=outcome.differences,
    )


def _invalidate_ilga_caches() -> bool:
    temporary_app: Flask | None = None
    if not getattr(cache, "app", None):
        temporary_app = Flask("ilga-historical-import")
        init_cache(temporary_app)
    context = temporary_app.app_context() if temporary_app is not None else None
    try:
        if context is not None:
            context.push()
        invalidate_analytics_cache("ilga")
    except Exception:
        logger.exception("ilga_cache_invalidation_failed")
        return False
    finally:
        if context is not None:
            context.pop()
    logger.info(
        "ilga_cache_invalidated scopes=legal_years,historical_rankings,temporal_evolution,ilga_trends"
    )
    return True


def format_import_summary(summary: HistoricalImportSummary) -> str:
    headers = (
        "Año",
        "Archivo",
        "Países",
        "Insertados",
        "Actualizados",
        "Omitidos",
        "Normalizado",
        "Estado",
    )
    records = [
        (
            str(row.year or "—"),
            row.file_name,
            str(row.countries),
            str(row.inserted),
            str(row.updated),
            str(row.skipped),
            "Sí" if row.normalized else "No",
            row.status,
        )
        for row in summary.rows
    ]
    widths = [
        max(len(headers[index]), *(len(record[index]) for record in records))
        for index in range(len(headers))
    ]
    lines = ["  ".join(value.ljust(widths[index]) for index, value in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(record))
        for record in records
    )
    for row in summary.rows:
        details = (*row.errors, *(f"difference:{item}" for item in row.differences))
        if details:
            lines.append(f"{row.file_name}: {', '.join(details)}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import validated historical ILGA-Europe Rainbow Map JSON files."
    )
    parser.add_argument("source_directory", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    summary = import_ilga_historical_directory(
        args.source_directory,
        dry_run=args.dry_run,
    )
    print(format_import_summary(summary))
    if any(row.status == "Error" for row in summary.rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
