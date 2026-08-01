from __future__ import annotations

from dataclasses import dataclass, field

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


def validate_fra_query(query: FraStatisticsQuery) -> ValidationResult:
    if query.filter_a_name and query.filter_a_name not in FRA_FILTER_GROUP_A:
        return ValidationResult(
            False, "El filtro demográfico seleccionado no pertenece al grupo A."
        )
    if query.filter_b_name and query.filter_b_name not in FRA_FILTER_GROUP_B:
        return ValidationResult(
            False, "El filtro de identidad seleccionado no pertenece al grupo B."
        )
    if query.filter_a_value and not query.filter_a_name:
        return ValidationResult(False, "Selecciona primero el tipo de filtro demográfico.")
    if query.filter_b_value and not query.filter_b_name:
        return ValidationResult(False, "Selecciona primero el tipo de filtro de identidad.")
    invalid_grouping = [item for item in query.group_by if item not in FRA_GROUP_BY_OPTIONS]
    if invalid_grouping:
        return ValidationResult(False, f"Agrupación no admitida: {', '.join(invalid_grouping)}.")
    return ValidationResult(True)
