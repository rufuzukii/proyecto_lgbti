from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TrendSource(StrEnum):
    ILGA = "ilga"
    FRA = "fra"


class TrendDirection(StrEnum):
    UPWARD = "upward"
    DOWNWARD = "downward"
    STABLE = "stable"


@dataclass(frozen=True)
class TrendIndicator:
    source: TrendSource
    category: str
    indicator_id: str
    label: str
    criterion: str = ""
    specific_category: str = ""
    question: str = ""

    def to_token(self) -> str:
        return json.dumps(
            {
                "category": self.category,
                "criterion": self.criterion,
                "indicator_id": self.indicator_id,
                "label": self.label,
                "question": self.question,
                "source": self.source.value,
                "specific_category": self.specific_category,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_token(cls, token: str) -> TrendIndicator:
        try:
            payload = json.loads(token)
            source = TrendSource(str(payload["source"]))
            indicator_id = str(payload["indicator_id"]).strip()
            category = str(payload["category"]).strip()
            label = str(payload["label"]).strip()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_trend_indicator") from exc
        if not indicator_id or not category or not label:
            raise ValueError("invalid_trend_indicator")
        return cls(
            source=source,
            category=category,
            indicator_id=indicator_id,
            label=label,
            criterion=str(payload.get("criterion") or "").strip(),
            specific_category=str(payload.get("specific_category") or "").strip(),
            question=str(payload.get("question") or "").strip(),
        )


@dataclass(frozen=True)
class SeriesVariant:
    response: str = ""
    filters: tuple[tuple[str, str], ...] = ()

    def to_token(self) -> str:
        return json.dumps(
            {"filters": list(self.filters), "response": self.response},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_token(cls, token: str | None) -> SeriesVariant:
        if not token or token == "default":
            return cls()
        try:
            payload = json.loads(token)
            raw_filters = payload.get("filters") or []
            filters = tuple(
                sorted(
                    (str(item[0]).strip(), str(item[1]).strip())
                    for item in raw_filters
                    if isinstance(item, list | tuple) and len(item) == 2
                )
            )
            return cls(response=str(payload.get("response") or "").strip(), filters=filters)
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_trend_series_variant") from exc


@dataclass(frozen=True)
class TrendFilters:
    start_year: int | None = None
    end_year: int | None = None
    series_key: str | None = None


@dataclass(frozen=True)
class HistoricalPoint:
    year: int | None
    value: float | None
    source: str
    indicator_id: str
    country_code: str
    country_name: str
    response: str = ""
    filters: tuple[tuple[str, str], ...] = ()
    unit: str = "score"
    scale_min: float | None = None
    scale_max: float | None = None
    methodology: str = ""


@dataclass(frozen=True)
class SeriesMetadata:
    source: TrendSource
    indicator_id: str
    indicator_label: str
    category: str
    country_code: str
    country_name: str
    response: str = ""
    filters: tuple[tuple[str, str], ...] = ()
    unit: str = "score"
    scale_min: float | None = None
    scale_max: float | None = None
    methodology: str = ""
    stable_threshold: float = 0.25

    @property
    def bounded(self) -> bool:
        return self.scale_min is not None and self.scale_max is not None


@dataclass(frozen=True)
class ComparabilityResult:
    comparable: bool
    reason: str = ""


@dataclass(frozen=True)
class ForecastPoint:
    year: int
    value: float


@dataclass(frozen=True)
class TrendMetrics:
    observations: int
    mae: float
    rmse: float
    r_squared: float | None
    slope: float
    intercept: float


@dataclass(frozen=True)
class TrendSummary:
    observations: int
    start_year: int
    end_year: int
    initial_value: float
    final_value: float
    absolute_change: float
    percentage_change: float | None
    minimum: float
    maximum: float
    mean: float
    slope: float
    direction: TrendDirection


@dataclass(frozen=True)
class TrendAnalysis:
    status: str
    points: tuple[HistoricalPoint, ...] = ()
    forecast: tuple[ForecastPoint, ...] = ()
    summary: TrendSummary | None = None
    metrics: TrendMetrics | None = None
    comparability: ComparabilityResult = field(
        default_factory=lambda: ComparabilityResult(comparable=True)
    )
    exploratory: bool = False
    forecast_horizon: int = 0
    reason: str = ""


@dataclass(frozen=True)
class TrendScope:
    countries: tuple[tuple[str, str], ...]
    years: tuple[int, ...]


def filters_from_answer(value: Any) -> tuple[tuple[str, str], ...]:
    if isinstance(value, dict):
        pairs = value.items()
    elif isinstance(value, list):
        pairs = ((item.get("type"), item.get("value")) for item in value if isinstance(item, dict))
    else:
        pairs = ()
    return tuple(
        sorted(
            (str(key).strip(), str(item_value).strip())
            for key, item_value in pairs
            if str(key or "").strip() and str(item_value or "").strip()
        )
    )
