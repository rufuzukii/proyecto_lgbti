from __future__ import annotations

from dataclasses import dataclass, field, replace

from app.shared.data.normalization import (
    normalize_filter_type,
    normalize_filter_value,
    normalize_text_key,
)

FRA_FILTER_GROUP_A: tuple[str, ...] = (
    "All",
    "Age",
    "Belonging to a minority group",
    "Education",
    "Openness about being LGBTIQ+",
    "Employment status",
    "Place of residence",
    "Activity limitation",
    "Making ends meet",
)

FRA_FILTER_GROUP_B: tuple[str, ...] = (
    "All",
    "Sexual Orientation",
    "Gender Expression",
    "Sex Characteristics",
)

FRA_GROUP_BY_OPTIONS: tuple[str, ...] = (
    "country",
    "answer",
    "category",
    "question",
    "year",
    "filter_a",
    "filter_b",
)


@dataclass(frozen=True)
class FraStatisticsQuery:
    year: int | None = None
    countries: list[str] = field(default_factory=list)
    category: str | None = None
    question_code: str | None = None
    answer: str | None = None
    filter_a_name: str | None = None
    filter_a_value: str | None = None
    filter_b_name: str | None = None
    filter_b_value: str | None = None
    group_by: list[str] = field(default_factory=lambda: ["country"])
    mode: str = "all"


@dataclass(frozen=True)
class IlgaStatisticsQuery:
    year: int | None = None
    countries: list[str] = field(default_factory=list)
    category: str | None = None
    criterion: str | None = None
    mode: str = "all"


@dataclass(frozen=True)
class ExperienceLegalRadarQuery:
    fra_year: int | None = None
    ilga_year: int | None = None
    countries: tuple[str, ...] = ()
    filter_a_name: str | None = "All"
    filter_a_value: str | None = "All"
    filter_b_name: str | None = "All"
    filter_b_value: str | None = "All"


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    message: str = ""


@dataclass(frozen=True)
class StatisticsFilters:
    """Canonical FRA segmentation selected by the user.

    ``All`` is the only internal representation for an inactive group. A
    missing value on an active filter remains invalid instead of becoming the
    first available option.
    """

    demographic_type: str = "All"
    demographic_value: str = "All"
    identity_type: str = "All"
    identity_value: str = "All"

    @classmethod
    def from_raw(
        cls,
        demographic_type: object = None,
        demographic_value: object = None,
        identity_type: object = None,
        identity_value: object = None,
    ) -> StatisticsFilters:
        clean_demographic_type = _canonical_filter_type(demographic_type)
        clean_identity_type = _canonical_filter_type(identity_type)
        return cls(
            demographic_type=clean_demographic_type,
            demographic_value=_canonical_filter_value(clean_demographic_type, demographic_value),
            identity_type=clean_identity_type,
            identity_value=_canonical_filter_value(clean_identity_type, identity_value),
        )

    @property
    def demographic_active(self) -> bool:
        return self.demographic_type != "All"

    @property
    def identity_active(self) -> bool:
        return self.identity_type != "All"

    def as_query_fields(self) -> dict[str, str]:
        return {
            "filter_a_name": self.demographic_type,
            "filter_a_value": self.demographic_value,
            "filter_b_name": self.identity_type,
            "filter_b_value": self.identity_value,
        }


def normalize_fra_query(query: FraStatisticsQuery) -> FraStatisticsQuery:
    filters = StatisticsFilters.from_raw(
        query.filter_a_name,
        query.filter_a_value,
        query.filter_b_name,
        query.filter_b_value,
    )
    return replace(query, **filters.as_query_fields())


def validate_statistics_filter_combination(
    filters: StatisticsFilters,
    *,
    available_values: dict[str, set[str]] | None = None,
) -> ValidationResult:
    if filters.demographic_type not in FRA_FILTER_GROUP_A:
        return ValidationResult(
            False, "El filtro demográfico seleccionado no pertenece al grupo A."
        )
    if filters.identity_type not in FRA_FILTER_GROUP_B:
        return ValidationResult(
            False, "El filtro de identidad seleccionado no pertenece al grupo B."
        )
    for filter_type, filter_value, label in (
        (filters.demographic_type, filters.demographic_value, "demográfico"),
        (filters.identity_type, filters.identity_value, "de identidad"),
    ):
        if filter_type == "All" and filter_value != "All":
            return ValidationResult(False, f"El filtro {label} global debe usar All.")
        if filter_type != "All" and (not filter_value or filter_value == "All"):
            return ValidationResult(False, f"Selecciona un valor para el filtro {label}.")
        if available_values is not None:
            allowed = available_values.get(filter_type, set())
            if filter_value not in allowed:
                return ValidationResult(False, f"Valor no disponible para el filtro {label}.")
    if filters.demographic_active and filters.identity_active:
        return ValidationResult(
            False,
            "Los filtros de identidad no pueden combinarse con una segmentación demográfica.",
        )
    return ValidationResult(True)


def validate_fra_query(query: FraStatisticsQuery) -> ValidationResult:
    filters = StatisticsFilters.from_raw(
        query.filter_a_name,
        query.filter_a_value,
        query.filter_b_name,
        query.filter_b_value,
    )
    filter_validation = validate_statistics_filter_combination(filters)
    if not filter_validation.ok:
        return filter_validation
    invalid_grouping = [item for item in query.group_by if item not in FRA_GROUP_BY_OPTIONS]
    if invalid_grouping:
        return ValidationResult(False, f"Agrupación no admitida: {', '.join(invalid_grouping)}.")
    return ValidationResult(True)


def _canonical_filter_type(value: object) -> str:
    normalized = normalize_filter_type(value)
    return "All" if not normalized or normalize_text_key(normalized) == "all" else normalized


def _canonical_filter_value(_filter_type: str, value: object) -> str:
    normalized = normalize_filter_value(value)
    if not normalized or normalize_text_key(normalized) == "all":
        return "All"
    return normalized
