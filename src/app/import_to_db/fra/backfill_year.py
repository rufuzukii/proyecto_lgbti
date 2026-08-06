from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.import_to_db.fra.payload import FRA_DATASET_CODE, parse_fra_csv
from app.import_to_db.fra.schema import extract_fra_survey_year
from app.logging_config import configure_secure_logging
from app.mongo import get_mongo_collection

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FraYearBackfillReport:
    survey_year: int
    evidence_files: tuple[str, ...]
    matched_documents: int
    matched_answers: int
    updated_documents: int
    updated_answers: int
    unresolved_codes: tuple[str, ...]
    applied: bool


def backfill_fra_survey_year(
    evidence_paths: list[Path],
    *,
    apply: bool = False,
    collection: Any | None = None,
) -> FraYearBackfillReport:
    """Backfill Survey III only when CSV Source metadata proves one survey year."""
    survey_year, source_texts = _validated_evidence(evidence_paths)
    target_collection = collection or get_mongo_collection("Indicator_fra")
    missing_year = {"$or": [{"survey_year": {"$exists": False}}, {"survey_year": None}]}
    eligible_query = {"dataset": FRA_DATASET_CODE, **missing_year}
    candidates = list(
        target_collection.find(eligible_query, {"_id": 1, "code": 1, "answers": 1})
    )
    eligible: list[dict[str, Any]] = []
    conflicting: list[dict[str, Any]] = []
    for document in candidates:
        answer_years = {
            int(answer["survey_year"])
            for answer in document.get("answers") or []
            if isinstance(answer, dict)
            and isinstance(answer.get("survey_year"), int)
            and not isinstance(answer.get("survey_year"), bool)
        }
        if answer_years and answer_years != {survey_year}:
            conflicting.append(document)
        else:
            eligible.append(document)
    unresolved = list(
        target_collection.find(
            {"dataset": {"$ne": FRA_DATASET_CODE}, **missing_year},
            {"_id": 0, "code": 1},
        )
    )
    matched_answers = sum(
        len(document.get("answers") or [])
        for document in eligible
        if isinstance(document.get("answers"), list)
    )
    updated_documents = 0
    updated_answers = 0
    if apply:
        evidence_source = " | ".join(sorted(source_texts))
        for document in eligible:
            answers = document.get("answers")
            prepared_answers: list[Any] = []
            changed_answers = 0
            for answer in answers if isinstance(answers, list) else []:
                if not isinstance(answer, dict) or answer.get("survey_year") is not None:
                    prepared_answers.append(answer)
                    continue
                prepared_answers.append({**answer, "survey_year": survey_year})
                changed_answers += 1
            result = target_collection.update_one(
                {"_id": document["_id"], **missing_year},
                {
                    "$set": {
                        "survey_year": survey_year,
                        "answers": prepared_answers,
                        "metadata.survey_year": survey_year,
                        "metadata.survey_year_source": "csv_source_metadata",
                        "metadata.source": evidence_source,
                    }
                },
            )
            if result.modified_count:
                updated_documents += 1
                updated_answers += changed_answers

    unresolved_codes = tuple(
        sorted(
            {
                str(document.get("code") or "<sin código>")
                for document in [*unresolved, *conflicting]
            }
        )
    )
    report = FraYearBackfillReport(
        survey_year=survey_year,
        evidence_files=tuple(path.name for path in evidence_paths),
        matched_documents=len(eligible),
        matched_answers=matched_answers,
        updated_documents=updated_documents,
        updated_answers=updated_answers,
        unresolved_codes=unresolved_codes,
        applied=apply,
    )
    logger.info("fra_survey_year_backfill", extra=asdict(report))
    return report


def _validated_evidence(evidence_paths: list[Path]) -> tuple[int, set[str]]:
    if not evidence_paths:
        raise ValueError("fra_year_evidence_required")
    years: set[int] = set()
    sources: set[str] = set()
    for path in evidence_paths:
        payload = parse_fra_csv(path)
        documents = payload if isinstance(payload, list) else [payload]
        for document in documents:
            source = str(document.get("source") or "").strip()
            year = document.get("survey_year") or extract_fra_survey_year(source)
            if "survey iii" not in source.casefold() or year is None:
                raise ValueError(f"invalid_fra_year_evidence:{path.name}")
            years.add(int(year))
            sources.add(source)
    if len(years) != 1:
        raise ValueError("conflicting_fra_year_evidence")
    return next(iter(years)), sources


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill FRA Survey III survey_year safely.")
    parser.add_argument("evidence_csv", nargs="+", type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the changes. Without this flag the command is a dry run.",
    )
    args = parser.parse_args()
    configure_secure_logging()
    report = backfill_fra_survey_year(args.evidence_csv, apply=args.apply)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
