from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_ROOT = Path(__file__).resolve().parent / "data"


@lru_cache(maxsize=8)
def load_json(name: str) -> Any:
    if name not in {"glossary", "lessons", "games", "teacher_resources"}:
        raise ValueError("unsupported_educational_dataset")
    with (DATA_ROOT / f"{name}.json").open(encoding="utf-8") as source:
        return json.load(source)
