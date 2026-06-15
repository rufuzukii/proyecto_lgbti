from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from app.import_to_db.utils import clean_cell, parse_float


def _read_csv_rows(handle) -> list[list[str]]:
    return [row for row in csv.reader(handle)]


def _parse_rainbow_rows(rows: list[list[str]], year: int) -> list[dict]:
    if len(rows) < 4:
        return []

    category_row = rows[0]
    indicator_row = rows[1]
    weight_row = rows[2]

    criteria = []
    for index in range(3, len(indicator_row)):
        criteria.append(
            {
                "category": clean_cell(category_row, index),
                "indicator": clean_cell(indicator_row, index),
                "weight": parse_float(clean_cell(weight_row, index)),
            }
        )

    output = []
    for row in rows[3:]:
        if not row or not row[0].strip():
            continue

        country_code = row[0].strip()
        country = row[1].strip() if len(row) > 1 else ""
        ranking = parse_float(row[2]) if len(row) > 2 else None

        criteria_values = []
        for offset, criterion in enumerate(criteria, start=3):
            value = parse_float(row[offset]) if offset < len(row) else None
            criteria_values.append(
                {
                    "category": criterion["category"],
                    "indicator": criterion["indicator"],
                    "weight": criterion["weight"],
                    "value": value,
                }
            )

        output.append(
            {
                "source": "ILGA Europe Rainbow Map",
                "year": year,
                "country_code": country_code,
                "country": country,
                "ranking": ranking,
                "criteria": criteria_values,
            }
        )

    return output


def parse_rainbow_map_csv(file_path: Path, year: int) -> list[dict]:
    with file_path.open("r", encoding="utf-8", newline="") as handle:
        rows = _read_csv_rows(handle)
    return _parse_rainbow_rows(rows, year=year)


def parse_rainbow_map_csv_text(csv_text: str, year: int) -> list[dict]:
    with StringIO(csv_text) as handle:
        rows = _read_csv_rows(handle)
    return _parse_rainbow_rows(rows, year=year)


def convert_rainbow_csv_files(
    file_paths: list[Path], year: int
) -> list[tuple[Path, list[dict]]]:
    results: list[tuple[Path, list[dict]]] = []
    for file_path in file_paths:
        results.append((file_path, parse_rainbow_map_csv(file_path, year=year)))
    return results


def generate_rainbow_json(rainbow_csv: str, year: int) -> list[tuple[Path, list[dict]]]:
    csv_paths = [Path(rainbow_csv)] if rainbow_csv else []
    if not csv_paths:
        return []
    return convert_rainbow_csv_files(csv_paths, year=year)
