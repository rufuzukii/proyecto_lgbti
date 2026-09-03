from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.modules.reports.models import ReportConfiguration
from app.modules.reports.service import ReportGenerationError, generate_report_pdf

SOCIAL_BASE = {
    "source": "fra",
    "category": "Discrimination",
    "indicator_id": "D1_1",
    "indicator_label": "Felt discriminated in the 12 months before the survey in any of 8 areas of life",
    "answer": "Yes",
    "year": 2023,
    "language": "es",
}
LEGAL_BASE = {
    "source": "ilga",
    "category": "Ranking total",
    "year": 2026,
    "language": "es",
}
COMBINED_BASE = {**SOCIAL_BASE, "source": "combined"}
CASES = {
    "social-selected": {**SOCIAL_BASE, "countries": ["ES"], "primary_country": "ES"},
    "social-all": {**SOCIAL_BASE, "countries": [], "primary_country": ""},
    "legal-selected": {**LEGAL_BASE, "countries": ["ES"], "primary_country": "ES"},
    "legal-all": {**LEGAL_BASE, "countries": [], "primary_country": ""},
    "combined-all": {**COMBINED_BASE, "countries": [], "primary_country": ""},
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=["all", *CASES], default="all")
    parser.add_argument("--output-dir", type=Path)
    arguments = parser.parse_args()
    selected_cases = CASES if arguments.case == "all" else {arguments.case: CASES[arguments.case]}
    failures = 0
    for name, payload in selected_cases.items():
        try:
            generated = generate_report_pdf(ReportConfiguration.from_mapping(payload))
        except ReportGenerationError as exc:
            failures += 1
            print(
                json.dumps({"case": name, "status": "failed", "error": str(exc)}),
                flush=True,
            )
            continue
        output_path = _write_output(arguments.output_dir, name, generated.pdf_bytes)
        result: dict[str, Any] = {
            "case": name,
            "status": "passed",
            "images": generated.image_count,
            "pages": generated.page_count,
            "pdf_bytes": len(generated.pdf_bytes),
            "memory_peak_mb": generated.memory_peak_mb,
            **generated.timings,
        }
        if output_path is not None:
            result["output"] = str(output_path)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return 1 if failures else 0


def _write_output(directory: Path | None, name: str, content: bytes) -> Path | None:
    if directory is None:
        return None
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.pdf"
    path.write_bytes(content)
    return path


if __name__ == "__main__":
    sys.exit(main())
