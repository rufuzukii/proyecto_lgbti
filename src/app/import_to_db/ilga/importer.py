from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from io import StringIO
from pathlib import Path
from typing import Any

from bson import ObjectId

from app.import_to_db.utils import clean_cell, parse_float

ILGA_DATASET_CODE = "ilga_rainbow_map"
YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


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
        "countries": countries,
    }


def parse_ilga_json_text(json_text: str) -> dict | list[dict]:
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_ilga_json") from exc

    documents = payload if isinstance(payload, list) else [payload]
    if not documents or not all(isinstance(document, dict) for document in documents):
        raise ValueError("invalid_ilga_json")

    normalized = [_normalize_ilga_document(document) for document in documents]
    return normalized if isinstance(payload, list) else normalized[0]


def generate_ilga_json(
    file_paths: Iterable[Path | str],
) -> list[dict]:
    documents_by_year: dict[int, dict] = {}
    for file_path in file_paths:
        document = parse_ilga_csv(file_path)
        documents_by_year[document["year"]] = document
    return list(documents_by_year.values())


def extract_ilga_year(file_name: str) -> int | None:
    match = YEAR_PATTERN.search(file_name)
    return int(match.group(1)) if match else None


def _normalize_ilga_document(document: dict[str, Any]) -> dict:
    if document.get("dataset") != ILGA_DATASET_CODE:
        raise ValueError("invalid_ilga_payload")

    raw_year = document.get("year")
    if raw_year is None:
        raise ValueError("invalid_ilga_payload")
    try:
        year = int(raw_year)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_ilga_payload") from exc

    countries = document.get("countries")
    if not isinstance(countries, list) or not countries:
        raise ValueError("invalid_ilga_payload")

    normalized_countries = [_normalize_country(country) for country in countries]
    return {
        "id": str(ObjectId()),
        "dataset": ILGA_DATASET_CODE,
        "year": year,
        "countries": normalized_countries,
    }


def _normalize_country(country: Any) -> dict:
    if not isinstance(country, dict):
        # Import callers expose one stable exception for every malformed payload.
        raise ValueError("invalid_ilga_payload")  # noqa: TRY004

    country_name = str(country.get("country") or "").strip()
    country_code = str(country.get("country_code") or "").strip()
    ranking = _ranking_from_country(country)
    if not country_name or ranking is None:
        raise ValueError("invalid_ilga_payload")

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
    if isinstance(ranking, (int, float)):
        return float(ranking)
    parsed_ranking = parse_float(str(ranking)) if ranking is not None else None
    if parsed_ranking is not None:
        return parsed_ranking

    criteria = country.get("criteria")
    if isinstance(criteria, (int, float)):
        return float(criteria)
    if isinstance(criteria, str):
        return parse_float(criteria)
    return None


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
