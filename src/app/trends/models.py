from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ForecastModelName(StrEnum):
    LINEAR = "linear"
    HOLT = "holt"
    QUADRATIC = "quadratic"


class TrendDirection(StrEnum):
    UPWARD = "upward"
    DOWNWARD = "downward"
    STABLE = "stable"


@dataclass(frozen=True)
class TrendFilters:
    start_year: int | None = None
    end_year: int | None = None


@dataclass(frozen=True)
class HistoricalPoint:
    year: int | None
    value: float | None
    country_code: str
    country_name: str
    source: str = "ILGA-Europe"
    unit: str = "percentage_score"
    scale_min: float = 0.0
    scale_max: float = 100.0
    methodology: str = "ilga_rainbow_map"
    normalization_applied: bool = False
    normalization_method: str = ""
    original_scale_min: float | None = None
    original_scale_max: float | None = None
    target_scale_min: float | None = None
    target_scale_max: float | None = None


@dataclass(frozen=True)
class ForecastPoint:
    year: int
    value: float
    raw_value: float
    lower: float | None = None
    upper: float | None = None


@dataclass(frozen=True)
class ValidationFold:
    train_end_year: int
    target_year: int
    actual: float
    predicted: float
    raw_predicted: float


@dataclass(frozen=True)
class ModelValidation:
    model: ForecastModelName
    mae: float
    rmse: float
    folds: tuple[ValidationFold, ...]
    r_squared: float | None = None


@dataclass(frozen=True)
class TrendSummary:
    observations: int
    start_year: int
    end_year: int
    initial_value: float
    final_value: float
    absolute_change: float
    minimum: float
    maximum: float
    mean: float
    robust_slope: float
    direction: TrendDirection
    missing_years: tuple[int, ...] = ()


@dataclass(frozen=True)
class ForecastResult:
    status: str
    country_code: str
    country_name: str
    historical: tuple[HistoricalPoint, ...] = ()
    forecast: tuple[ForecastPoint, ...] = ()
    summary: TrendSummary | None = None
    selected_model: ForecastModelName | None = None
    validation: tuple[ModelValidation, ...] = ()
    selection_reason: str = ""
    uncertainty_method: str = ""
    exploratory: bool = False
    requested_horizon: int = 0
    forecast_horizon: int = 0
    reason: str = ""

    @property
    def selected_validation(self) -> ModelValidation | None:
        return next(
            (item for item in self.validation if item.model == self.selected_model),
            None,
        )

    @property
    def normalization_years(self) -> tuple[int, ...]:
        return tuple(
            point.year
            for point in self.historical
            if point.normalization_applied and point.year is not None
        )


@dataclass(frozen=True)
class TrendScope:
    countries: tuple[tuple[str, str], ...]
    years: tuple[int, ...]


@dataclass(frozen=True)
class CountryCoverage:
    country_code: str
    country_name: str
    start_year: int
    end_year: int
    observations: int
    missing_years: tuple[int, ...]
