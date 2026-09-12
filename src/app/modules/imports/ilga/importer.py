from __future__ import annotations

import csv
import json
import math
import re
from collections.abc import Iterable
from io import StringIO
from pathlib import Path
from typing import Any, TypeGuard

from bson import ObjectId

from app.modules.imports.utils import clean_cell, parse_float
from app.shared.data.geography import ISO2_TO_ISO3
from app.shared.data.ilga_metadata import ilga_normalization_metadata
from app.shared.data.source_attribution import source_storage_fields

ILGA_DATASET_CODE = "ilga_rainbow_map"
YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


class IlgaValidationError(ValueError):
    """Error estable de importación con detalles estructurados para el resumen del lote."""

    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(str(error) for error in errors)
        super().__init__("invalid_ilga_payload")


def parse_ilga_csv(
    file_path: Path | str,
    *,
    year: int | None = None,
) -> dict:
    path = Path(file_path)
    csv_text = path.read_text(encoding="utf-8-sig")
    return parse_ilga_csv_text(csv_text, file_name=path.name, year=year)


def parse_ilga_csv_text(
    csv_text: str,
    *,
    file_name: Path | str | None = None,
    year: int | None = None,
) -> dict:
    resolved_year = year or extract_ilga_year(str(file_name or ""))
    if resolved_year is None:
        raise ValueError("invalid_ilga_year")

    rows = list(csv.reader(StringIO(csv_text)))
    if len(rows) < 4:
        raise ValueError("invalid_ilga_csv")

    criteria = _parse_criteria(rows[:3])
    countries = _parse_countries(rows[3:], criteria)
    if not criteria or not countries:
        raise ValueError("invalid_ilga_csv")

    return {
        "id": str(ObjectId()),
        "dataset": ILGA_DATASET_CODE,
        "year": resolved_year,
        **source_storage_fields(
            "ilga",
            year=resolved_year,
            source_name="ILGA-Europe Rainbow Map",
        ),
        "normalization": ilga_normalization_metadata(resolved_year),
        "countries": countries,
    }


def parse_ilga_json(
    file_path: Path | str,
) -> dict | list[dict]:
    path = Path(file_path)
    return parse_ilga_json_text(
        path.read_text(encoding="utf-8-sig"),
        file_name=path.name,
    )


def parse_ilga_json_text(
    json_text: str,
    *,
    file_name: Path | str | None = None,
) -> dict | list[dict]:
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_ilga_json") from exc

    documents = payload if isinstance(payload, list) else [payload]
    if not documents or not all(isinstance(document, dict) for document in documents):
        raise ValueError("invalid_ilga_json")

    normalized = [_normalize_ilga_document(document, file_name=file_name) for document in documents]
    return normalized if isinstance(payload, list) else normalized[0]


def extract_ilga_year(file_name: str) -> int | None:
    match = YEAR_PATTERN.search(file_name)
    return int(match.group(1)) if match else None


def _normalize_ilga_document(
    document: dict[str, Any],
    *,
    file_name: Path | str | None = None,
) -> dict:
    errors: list[str] = []
    if document.get("dataset") != ILGA_DATASET_CODE:
        errors.append("invalid_dataset")
    raw_year = document.get("year")
    year: int | None = None
    if not isinstance(raw_year, int) or isinstance(raw_year, bool):
        errors.append("missing_year" if raw_year is None else "invalid_year")
    else:
        year = raw_year
        if not 2011 <= year <= 2100:
            errors.append("incoherent_year")
        file_year = extract_ilga_year(str(file_name or ""))
        if file_year is not None and file_year != year:
            errors.append(f"filename_year_mismatch:{file_year}")

    countries = document.get("countries")
    if not isinstance(countries, list) or not countries:
        errors.append("missing_countries")
        countries = []

    normalized_countries: list[dict[str, Any]] = []
    for index, country in enumerate(countries):
        try:
            normalized_countries.append(_normalize_country(country))
        except IlgaValidationError as exc:
            errors.extend(f"country[{index}].{error}" for error in exc.errors)

    country_codes = [country["country_code"] for country in normalized_countries]
    duplicate_codes = sorted(code for code in set(country_codes) if country_codes.count(code) > 1)
    if duplicate_codes:
        errors.append(f"duplicate_country_codes:{','.join(duplicate_codes)}")
    country_names = [country["country"].casefold() for country in normalized_countries]
    duplicate_names = sorted(name for name in set(country_names) if country_names.count(name) > 1)
    if duplicate_names:
        errors.append(f"duplicate_countries:{','.join(duplicate_names)}")
    if errors or year is None:
        raise IlgaValidationError(errors)

    return {
        "id": str(ObjectId()),
        "dataset": ILGA_DATASET_CODE,
        "year": year,
        **source_storage_fields(
            "ilga",
            year=year,
            source_name="ILGA-Europe Rainbow Map",
        ),
        "normalization": ilga_normalization_metadata(year),
        "countries": normalized_countries,
    }


def _normalize_country(country: Any) -> dict:
    if not isinstance(country, dict):
        raise IlgaValidationError(["not_an_object"])

    errors: list[str] = []
    country_name = str(country.get("country") or "").strip()
    country_code = str(country.get("country_code") or "").strip().upper()
    ranking = _ranking_from_country(country)
    if not country_name:
        errors.append("missing_country")
    if country_code not in ISO2_TO_ISO3:
        errors.append(f"invalid_country_code:{country_code or '<empty>'}")
    if "criteria" not in country:
        errors.append("missing_criteria")
    if ranking is None:
        errors.append("invalid_criteria")
    elif not 0 <= ranking <= 100:
        errors.append("criteria_out_of_range")
    if errors:
        raise IlgaValidationError(errors)

    criteria = country.get("criteria")
    if not isinstance(criteria, list):
        criteria = None

    return {
        "country": country_name,
        "ranking": ranking,
        "criteria": criteria,
        "country_code": country_code,
    }


def _ranking_from_country(country: dict[str, Any]) -> float | None:
    ranking = country.get("ranking")
    if _is_finite_number(ranking):
        return float(ranking)

    criteria = country.get("criteria")
    if _is_finite_number(criteria):
        return float(criteria)
    return None


def _is_finite_number(value: Any) -> TypeGuard[int | float]:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _parse_criteria(header_rows: list[list[str]]) -> list[dict]:
    category_row, indicator_row, weight_row = header_rows
    criteria: list[dict] = []
    current_category = ""

    for index in range(3, len(indicator_row)):
        category = clean_cell(category_row, index)
        if category:
            current_category = category
        indicator = clean_cell(indicator_row, index)
        if not indicator:
            continue
        criteria.append(
            {
                "column_index": index,
                "category": current_category,
                "indicator": indicator,
                "weight": parse_float(clean_cell(weight_row, index)),
            }
        )
    return criteria


def _parse_countries(rows: list[list[str]], criteria: list[dict]) -> list[dict]:
    countries: list[dict] = []
    for row in rows:
        country_code = clean_cell(row, 0)
        if not country_code:
            continue

        criterion_values = [
            {
                "category": criterion["category"],
                "indicator": criterion["indicator"],
                "weight": criterion["weight"],
                "value": parse_float(clean_cell(row, criterion["column_index"])),
            }
            for criterion in criteria
        ]
        countries.append(
            {
                "country_code": country_code,
                "country": clean_cell(row, 1),
                "ranking": parse_float(clean_cell(row, 2)),
                "criteria": criterion_values,
            }
        )
    return countries
