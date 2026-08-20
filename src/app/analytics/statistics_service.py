from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from copy import deepcopy
from dataclasses import replace
from typing import Any, cast

import pandas as pd

from app.analytics.combined_analysis import (
    build_availability_rows,
    build_combined_analysis,
    median_difference_rows,
    nearest_ilga_year,
)
from app.analytics.fra_metadata import (
    RESPONSE_TYPES,
    detect_fra_response_type,
    fra_survey_participant_codes,
    order_fra_responses,
)
from app.analytics.geography_service import europe_country_catalog
from app.analytics.legal_criteria import get_criterion_status
from app.analytics.percentage_display import (
    coerce_percentage,
    normalize_percentage_values,
)
from app.analytics.repository import (
    ANALYTICS_CACHE_TIMEOUT_SECONDS,
    analytics_cache_generation,
    fra_cache_namespace,
    get_fra_indicator_answers,
    get_fra_indicator_control_document,
    get_fra_indicator_documents,
    get_ilga_analysis_rows,
    get_ilga_document_by_year,
    get_ilga_years,
)
from app.analytics.statistics_models import (
    FRA_FILTER_GROUP_A,
    FRA_FILTER_GROUP_B,
    ExperienceLegalRadarQuery,
    FraStatisticsQuery,
    IlgaStatisticsQuery,
    StatisticsFilters,
    normalize_fra_query,
    validate_fra_query,
    validate_statistics_filter_combination,
)
from app.analytics.statistics_normalizers import (
    display_option,
    normalize_country_code,
    normalize_filter_type,
    normalize_filter_value,
    normalize_text_key,
    repair_text_encoding,
)
from app.cache import cache
from app.fra_surveys import FRA_SURVEYS
from app.ilga_metadata import normalized_ilga_source_scale

logger = logging.getLogger(__name__)
NO_DATA_MESSAGE = "No hay datos disponibles para esta selección."
DEFAULT_FRA_ANSWER_PRIORITY = (
    "Yes",
    "Often",
    "Always",
    "Very often",
    "Never",
    "No",
)

RADAR_MAPPING_VERSION = "fra-ilga-v1"
ILGA_RESPONSE_ORDER = {
    "not_met": 0,
    "partially_met": 1,
    "fully_met": 2,
    "not_available": 3,
    "overall_score": 4,
}
RADAR_DIMENSION_MAPPING: dict[str, dict[str, Any]] = {
    "equal_treatment": {
        "label_es": "Igualdad y no discriminación",
        "label_en": "Equality and non-discrimination",
        "fra": ({"code": "D1_1", "answer": "Yes", "invert": True},),
        "ilga": {"category": "Equality & non-discrimination", "prefixes": ()},
    },
    "goods_services": {
        "label_es": "Bienes y servicios",
        "label_en": "Goods and services",
        "fra": ({"code": "D1_2_f", "answer": "Yes", "invert": True},),
        "ilga": {
            "category": "Equality & non-discrimination",
            "prefixes": ("Goods & services",),
        },
    },
    "education": {
        "label_es": "Educación",
        "label_en": "Education",
        "fra": (
            {"code": "C9_E", "answer": "Never", "invert": False},
            {"code": "C9_C", "answer": "Never", "invert": False},
        ),
        "ilga": {
            "category": "Equality & non-discrimination",
            "prefixes": ("Education",),
        },
    },
    "health": {
        "label_es": "Salud",
        "label_en": "Health",
        "fra": ({"code": "G16", "answer": "Very good", "invert": False},),
        "ilga": {
            "category": "Equality & non-discrimination",
            "prefixes": ("Health",),
        },
    },
    "equality_bodies": {
        "label_es": "Acceso a organismos de igualdad",
        "label_en": "Access to equality bodies",
        "fra": ({"code": "C20_Any_EB", "answer": "Yes", "invert": False},),
        "ilga": {
            "category": "Equality & non-discrimination",
            "prefixes": ("Equality body mandate",),
        },
    },
}


def fra_document_to_dataframe(document: dict[str, Any] | None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not isinstance(document, dict):
        return _empty_fra_dataframe()

    answers = [answer for answer in document.get("answers", []) if isinstance(answer, dict)]
    raw_percentages = [_answer_percentage_value(answer) for answer in answers]
    normalized_percentages = normalize_percentage_values(
        raw_percentages,
        logger=logger,
        context={
            "collection": "Indicator_fra",
            "indicator": document.get("code"),
            "field": "answers.percentage",
            "countries": sorted(
                {
                    str(answer.get("country_code") or answer.get("country") or "").strip()
                    for answer in answers
                    if str(answer.get("country_code") or answer.get("country") or "").strip()
                }
            ),
            "years": sorted(
                {
                    year
                    for answer in answers
                    if (
                        year := _extract_year(
                            answer.get("survey_year")
                            or document.get("survey_year")
                            or answer.get("date")
                        )
                    )
                    is not None
                }
            ),
        },
    )
    for answer, percentage in zip(answers, normalized_percentages, strict=True):
        country = repair_text_encoding(answer.get("country")).strip()
        answer_value = repair_text_encoding(answer.get("answer")).strip()
        if not country or not answer_value:
            continue
        filters = _filters_to_dict(answer.get("filters"))
        rows.append(
            {
                "source": "FRA",
                "category": repair_text_encoding(document.get("category")).strip(),
                "specific_category": repair_text_encoding(
                    document.get("specific_category")
                ).strip(),
                "question": repair_text_encoding(document.get("question")).strip(),
                "question_code": repair_text_encoding(document.get("code")).strip(),
                "country": country,
                "iso": normalize_country_code(answer.get("country_code"), country),
                "answer": answer_value,
                "answer_label": normalize_filter_value(answer_value),
                "percentage": percentage,
                "year": _extract_year(
                    answer.get("survey_year") or document.get("survey_year") or answer.get("date")
                ),
                "filters": filters,
                "filter_a": _first_matching_filter(filters, FRA_FILTER_GROUP_A),
                "filter_b": _first_matching_filter(filters, FRA_FILTER_GROUP_B),
            }
        )
    return pd.DataFrame(rows) if rows else _empty_fra_dataframe()


def ilga_document_to_dataframe(document: dict[str, Any] | None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not isinstance(document, dict):
        return _empty_ilga_dataframe()

    year = _safe_int(document.get("year"))
    for country in document.get("countries", []):
        if not isinstance(country, dict):
            continue
        ranking = _safe_float(country.get("ranking"))
        if ranking is None:
            continue
        country_name = repair_text_encoding(country.get("country")).strip()
        iso = normalize_country_code(country.get("country_code"), country_name)
        rows.append(
            {
                "source": "ILGA-Europe",
                "year": year,
                "country": country_name,
                "iso": iso,
                "ranking": ranking,
                "category": "Ranking total",
                "criterion": "",
                "criterion_value": None,
                "criterion_weight": None,
            }
        )
        criteria = country.get("criteria")
        if not isinstance(criteria, list):
            continue
        for criterion in criteria:
            if not isinstance(criterion, dict):
                continue
            value = criterion.get("value")
            criterion_value = _safe_float(value)
            rows.append(
                {
                    "source": "ILGA-Europe",
                    "year": year,
                    "country": country_name,
                    "iso": iso,
                    "ranking": float(ranking),
                    "category": repair_text_encoding(criterion.get("category")).strip(),
                    "criterion": repair_text_encoding(criterion.get("indicator")).strip(),
                    "criterion_value": criterion_value,
                    "criterion_weight": criterion.get("weight"),
                }
            )
    return pd.DataFrame(rows) if rows else _empty_ilga_dataframe()


def ilga_analysis_rows_to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Normalize projected ILGA country rows into one canonical analysis frame.

    Duplicate resolution is deterministic: the newest Mongo document id wins;
    exact duplicates inside that document collapse to one row; conflicting
    values inside the winning document become missing instead of being averaged.
    """
    normalized: list[dict[str, Any]] = []
    discarded: dict[str, int] = {
        "invalid_year": 0,
        "missing_country": 0,
        "invalid_ranking": 0,
        "invalid_criterion_value": 0,
        "invalid_weight": 0,
    }
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            continue
        year = _safe_int(raw_row.get("year"))
        if year is None:
            discarded["invalid_year"] += 1
            continue
        country_name = repair_text_encoding(raw_row.get("country_name")).strip()
        country_code = normalize_country_code(raw_row.get("country_code"), country_name)
        if not country_code or not country_name or re.fullmatch(r"EU\d{2}", country_code):
            discarded["missing_country"] += 1
            continue
        document_id = str(raw_row.get("document_id") or "")
        country_index = _safe_int(raw_row.get("country_index")) or 0
        ranking = coerce_percentage(raw_row.get("ranking"))
        if ranking is None and raw_row.get("ranking") is not None:
            discarded["invalid_ranking"] += 1
        normalization_fields = _ilga_normalization_fields(raw_row.get("normalization"))
        normalized.append(
            {
                "document_id": document_id,
                "country_index": country_index,
                "criterion_index": -1,
                "source": "ILGA-Europe",
                "year": year,
                "country": country_name,
                "country_name": country_name,
                "iso": country_code,
                "country_code": country_code,
                "ranking": ranking,
                "category": "Ranking total",
                "criterion": "",
                "indicator_id": "Ranking total",
                "criterion_value": None,
                "criterion_weight": None,
                "value": ranking,
                "response": "overall_score",
                "response_order": ILGA_RESPONSE_ORDER["overall_score"],
                **normalization_fields,
            }
        )
        criteria = raw_row.get("criteria")
        if not isinstance(criteria, list):
            continue
        for criterion_index, criterion in enumerate(criteria):
            if not isinstance(criterion, dict):
                continue
            category = repair_text_encoding(criterion.get("category")).strip()
            indicator = repair_text_encoding(criterion.get("indicator")).strip()
            if not category or not indicator:
                continue
            raw_value = _safe_unit_score(criterion.get("value"))
            if raw_value is None and criterion.get("value") is not None:
                discarded["invalid_criterion_value"] += 1
            weight = _safe_positive_float(criterion.get("weight"))
            if weight is None and criterion.get("weight") is not None:
                discarded["invalid_weight"] += 1
            response = get_criterion_status(raw_value, 1, "en")["id"]
            normalized.append(
                {
                    "document_id": document_id,
                    "country_index": country_index,
                    "criterion_index": criterion_index,
                    "source": "ILGA-Europe",
                    "year": year,
                    "country": country_name,
                    "country_name": country_name,
                    "iso": country_code,
                    "country_code": country_code,
                    "ranking": ranking,
                    "category": category,
                    "criterion": indicator,
                    "indicator_id": indicator,
                    "criterion_value": raw_value,
                    "criterion_weight": weight,
                    "value": raw_value * 100 if raw_value is not None else None,
                    "response": response,
                    "response_order": ILGA_RESPONSE_ORDER[response],
                    **normalization_fields,
                }
            )
    if not normalized:
        return _empty_ilga_analysis_dataframe()

    dataframe = pd.DataFrame(normalized)
    resolved_rows: list[dict[str, Any]] = []
    duplicate_groups = 0
    conflicting_groups = 0
    group_columns = ["year", "country_code", "indicator_id", "category"]
    for _key, group in dataframe.groupby(group_columns, sort=False, dropna=False):
        latest_document = max(group["document_id"].astype(str).tolist(), default="")
        candidates = group[group["document_id"].astype(str).eq(latest_document)].sort_values(
            ["country_index", "criterion_index"], kind="stable"
        )
        duplicate_groups += int(len(group) > 1)
        numeric_values = {
            float(value)
            for value in candidates["value"].tolist()
            if value is not None and pd.notna(value)
        }
        chosen = cast(dict[str, Any], candidates.iloc[0].to_dict())
        if len(numeric_values) > 1:
            conflicting_groups += 1
            chosen["value"] = None
            chosen["criterion_value"] = None
            chosen["response"] = "not_available"
            chosen["response_order"] = ILGA_RESPONSE_ORDER["not_available"]
        resolved_rows.append(chosen)

    resolved = pd.DataFrame(resolved_rows)
    latest_names = (
        resolved.sort_values(["year", "document_id", "country_index"], kind="stable")
        .groupby("country_code", sort=False)
        .tail(1)
        .set_index("country_code")["country_name"]
        .to_dict()
    )
    resolved["country_name"] = resolved["country_code"].map(latest_names)
    resolved["country"] = resolved["country_name"]
    discarded = {key: value for key, value in discarded.items() if value}
    if discarded or duplicate_groups or conflicting_groups:
        logger.warning(
            "ilga_analysis_quality discarded=%r duplicate_groups=%d conflicting_groups=%d",
            discarded,
            duplicate_groups,
            conflicting_groups,
            extra={
                "discarded": discarded,
                "duplicate_group_count": duplicate_groups,
                "conflicting_group_count": conflicting_groups,
            },
        )
    return resolved[_empty_ilga_analysis_dataframe().columns.tolist()].reset_index(drop=True)


def _ilga_normalization_fields(value: Any) -> dict[str, Any]:
    metadata = normalized_ilga_source_scale(value)
    if metadata is None:
        return {
            "normalization_applied": False,
            "normalization_method": "",
            "original_scale_min": None,
            "original_scale_max": None,
            "target_scale_min": None,
            "target_scale_max": None,
        }
    return {
        "normalization_applied": True,
        "normalization_method": metadata["method"],
        "original_scale_min": metadata["original_min"],
        "original_scale_max": metadata["original_max"],
        "target_scale_min": metadata["target_min"],
        "target_scale_max": metadata["target_max"],
    }


def _ilga_result_normalization(dataframe: pd.DataFrame) -> dict[str, Any]:
    if dataframe.empty or "normalization_applied" not in dataframe:
        return {"applied": False}
    normalized = dataframe[dataframe["normalization_applied"].eq(True)]
    if normalized.empty:
        return {"applied": False}
    row = normalized.iloc[0]
    return {
        "applied": True,
        "method": str(row.get("normalization_method") or ""),
        "original_min": row.get("original_scale_min"),
        "original_max": row.get("original_scale_max"),
        "target_min": row.get("target_scale_min"),
        "target_max": row.get("target_scale_max"),
    }


def build_fra_filter_type_options(
    document: dict[str, Any] | None, group: str
) -> list[dict[str, Any]]:
    allowed = FRA_FILTER_GROUP_A if group == "a" else FRA_FILTER_GROUP_B
    dataframe = fra_document_to_dataframe(document)
    present = _present_filter_types(dataframe)
    options = []
    for filter_type in allowed:
        disabled = (
            not _all_filter_type_available(dataframe, group)
            if filter_type == "All"
            else filter_type not in present
        )
        options.append(display_option(filter_type, filter_type, disabled=disabled))
    return options


def build_fra_filter_value_options(
    document: dict[str, Any] | None,
    filter_type: str | None,
) -> list[dict[str, Any]]:
    clean_type = normalize_filter_type(filter_type)
    if not clean_type or clean_type == "All":
        return [display_option("All", "All")]

    values: dict[str, str] = {}
    for row in fra_document_to_dataframe(document).to_dict("records"):
        filters = row.get("filters")
        if not isinstance(filters, dict):
            continue
        for raw_type, raw_value in filters.items():
            if normalize_filter_type(raw_type) != clean_type:
                continue
            label = normalize_filter_value(raw_value)
            if label:
                values.setdefault(str(raw_value), label)
    return [
        {"label": label, "value": raw_value}
        for raw_value, label in sorted(values.items(), key=lambda item: item[1])
    ] or [display_option("All", "All", disabled=True)]


def build_fra_control_payload(document: dict[str, Any] | None) -> dict[str, Any]:
    """Derive all FRA control options without constructing a pandas DataFrame."""
    if not isinstance(document, dict):
        return {
            "answers": [],
            "segmentations": [],
            "values": {},
            "response_type": "standard",
            "response_help": None,
        }

    answer_values: dict[str, str] = {}
    filter_values: dict[str, dict[str, str]] = {}
    for answer in document.get("answers", []):
        if not isinstance(answer, dict):
            continue
        answer_value = repair_text_encoding(answer.get("answer")).strip()
        country = repair_text_encoding(answer.get("country")).strip()
        if not answer_value or not country:
            continue
        answer_values.setdefault(answer_value, normalize_filter_value(answer_value))
        for raw_type, raw_value in _filters_to_dict(answer.get("filters")).items():
            filter_type = normalize_filter_type(raw_type)
            if not filter_type or filter_type == "All":
                continue
            filter_values.setdefault(filter_type, {}).setdefault(
                str(raw_value), normalize_filter_value(raw_value)
            )

    response_type = detect_fra_response_type(
        answer_values,
        question=document.get("question"),
        specific_category=document.get("specific_category"),
    )
    ordered_answer_values = order_fra_responses(
        sorted(answer_values, key=lambda value: answer_values[value].casefold()),
        response_type=response_type,
    )
    global_answers = _global_answers_from_control_document(document)
    answers = [
        {"label": answer_values[value], "value": value} for value in ordered_answer_values
    ]
    ordered_types = ["All", *FRA_FILTER_GROUP_A[1:], *FRA_FILTER_GROUP_B[1:]]
    segmentations = [
        display_option(filter_type, filter_type)
        for filter_type in ordered_types
        if filter_type == "All" or filter_type in filter_values
    ]
    values: dict[str, list[dict[str, Any]]] = {"All": [display_option("All", "All")]}
    for filter_type in ordered_types[1:]:
        found = filter_values.get(filter_type)
        if not found:
            continue
        values[filter_type] = [
            {"label": label, "value": raw_value}
            for raw_value, label in sorted(found.items(), key=lambda item: item[1].casefold())
        ]
    response_metadata = RESPONSE_TYPES.get(response_type)
    return {
        "answers": answers,
        "default_answer": _preferred_fra_answer(ordered_answer_values, global_answers),
        "global_answers": sorted(global_answers, key=str.casefold),
        "segmentations": segmentations,
        "values": values,
        "response_type": response_type.value,
        "response_help": response_metadata.help_key if response_metadata else None,
    }


def get_fra_control_payload(
    code: str,
    category: str | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    clean_code = str(code or "").strip()
    if not clean_code:
        return {
            "code": "",
            "category": "",
            "answers": [],
            "segmentations": [],
            "values": {},
            "response_type": "standard",
            "response_help": None,
        }
    clean_category = str(category or "").strip()
    clean_year = str(int(year)) if year is not None else "all-years"
    cache_key = (
        f"fra-controls-v5:{analytics_cache_generation(fra_cache_namespace(year))}:"
        f"{clean_code}:{clean_category}:{clean_year}"
    )
    cached = _server_cache_get(cache_key)
    if isinstance(cached, dict):
        return deepcopy(cached)

    document = get_fra_indicator_control_document(clean_code, clean_category or None, year)
    payload = build_fra_control_payload(document)
    payload["code"] = clean_code
    payload["category"] = str((document or {}).get("category") or "").strip()
    if isinstance(document, dict):
        _server_cache_set(cache_key, deepcopy(payload))
    return payload


def get_fra_statistics(query: FraStatisticsQuery) -> dict[str, Any]:
    started_at = time.perf_counter()
    query = normalize_fra_query(query)
    validation = validate_fra_query(query)
    if not validation.ok:
        return _status("invalid", validation.message)

    cache_key = _fra_statistics_cache_key(query)
    cached = _server_cache_get(cache_key)
    if isinstance(cached, dict):
        logger.info(
            "statistics_loaded source=fra indicator=%s total_ms=%.2f cache_hit=true",
            query.question_code,
            (time.perf_counter() - started_at) * 1000,
        )
        return deepcopy(cached)

    result = _build_fra_statistics(query)
    if result.get("status") == "ok":
        _server_cache_set(cache_key, deepcopy(result))
    logger.info(
        "statistics_loaded source=fra indicator=%s status=%s total_ms=%.2f cache_hit=false",
        query.question_code,
        result.get("status"),
        (time.perf_counter() - started_at) * 1000,
    )
    return result


def get_combined_statistics_analysis(
    query: FraStatisticsQuery,
    *,
    fra_result: dict[str, Any] | None = None,
    include_availability: bool = True,
) -> dict[str, Any]:
    """Return one cached FRA/ILGA analytical dataset for all combined visuals."""
    query = normalize_fra_query(query)
    ilga_year = nearest_ilga_year(query.year, get_ilga_years())
    if ilga_year is None:
        return _status("empty", "No hay datos ILGA-Europe comparables.")
    identity = {
        "fra_cache_generations": {
            str(survey.year): analytics_cache_generation(fra_cache_namespace(survey.year))
            for survey in FRA_SURVEYS
            if survey.enabled
        },
        "ilga_cache_generation": analytics_cache_generation("ilga"),
        "year": query.year,
        "category": query.category,
        "question_code": query.question_code,
        "answer": query.answer,
        "filter_a_name": query.filter_a_name,
        "filter_a_value": query.filter_a_value,
        "filter_b_name": query.filter_b_name,
        "filter_b_value": query.filter_b_value,
        "countries": sorted(str(country) for country in query.countries),
        "ilga_year": ilga_year,
        "include_availability": include_availability,
        "analysis_version": 3,
    }
    serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    cache_key = f"fra-ilga-analysis-v3:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"
    cached = _server_cache_get(cache_key)
    if isinstance(cached, dict):
        return deepcopy(cached)

    fra_payload = fra_result if isinstance(fra_result, dict) else get_fra_statistics(query)
    if fra_payload.get("status") != "ok":
        return _status("empty", NO_DATA_MESSAGE)
    legal_payload = get_ilga_statistics(
        IlgaStatisticsQuery(year=ilga_year, category="Ranking total"),
        include_history=False,
    )
    if legal_payload.get("status") != "ok":
        return _status("empty", "No hay datos ILGA-Europe comparables.")
    analysis = build_combined_analysis(fra_payload, legal_payload)
    availability = (
        _combined_availability(query, fra_payload, legal_payload)
        if include_availability
        else None
    )
    result = {
        "status": "ok",
        "message": "",
        **analysis,
        "fra_median_comparison": median_difference_rows(
            [
                {
                    "country": row.get("country"),
                    "iso": row.get("iso"),
                    "fra_value": row.get("value"),
                }
                for row in fra_payload.get("ranking") or []
            ]
        ),
    }
    if availability is not None:
        result["availability"] = availability
    _server_cache_set(cache_key, deepcopy(result))
    return result


def _combined_availability(
    query: FraStatisticsQuery,
    fra_payload: dict[str, Any],
    legal_payload: dict[str, Any],
) -> dict[str, Any]:
    """Resolve historical indicator availability once for the shared payload.

    Only the same canonical question code and selected answer are considered
    comparable. Similar wording is deliberately not inferred.
    """
    years = [survey.year for survey in FRA_SURVEYS if survey.enabled]
    values_by_year: dict[int, set[str]] = {}
    indicator_available: dict[int, bool] = {}
    current_year = _safe_int(fra_payload.get("year"))
    for year in years:
        if year == current_year:
            rows = list(fra_payload.get("ranking") or [])
            indicator_available[year] = bool(rows)
            values_by_year[year] = {
                normalize_country_code(row.get("iso"), row.get("country"))
                for row in rows
                if _safe_float(row.get("value")) is not None
            }
            continue
        dataframe = _fra_dataframe_for_code(
            str(query.question_code or ""), query.category, year
        )
        answer = str(query.answer or "").strip()
        answer_exists = bool(
            not dataframe.empty
            and "answer" in dataframe
            and dataframe["answer"].fillna("").astype(str).str.strip().eq(answer).any()
        )
        year_query = replace(query, year=year, countries=[])
        filters_available = validate_statistics_filter_combination(
            StatisticsFilters.from_raw(
                year_query.filter_a_name,
                year_query.filter_a_value,
                year_query.filter_b_name,
                year_query.filter_b_value,
            ),
            available_values=_available_filter_values(dataframe),
        ).ok
        indicator_available[year] = answer_exists and filters_available
        if not indicator_available[year]:
            values_by_year[year] = set()
            continue
        filtered = filter_fra_dataframe(dataframe, year_query, effective_answer=answer)
        filtered = filtered.copy()
        filtered["percentage"] = pd.to_numeric(filtered["percentage"], errors="coerce")
        values_by_year[year] = {
            normalize_country_code(row.iso, row.country)
            for row in filtered.dropna(subset=["percentage"]).itertuples()
            if normalize_country_code(row.iso, row.country)
        }

    countries = [
        {
            "country": row.get("name_en"),
            "iso": row.get("country_code"),
        }
        for row in europe_country_catalog()
    ]
    rows = build_availability_rows(
        countries,
        fra_values_by_year=values_by_year,
        indicator_available_by_year=indicator_available,
        participant_codes_by_year={
            year: fra_survey_participant_codes(year) for year in years
        },
        ilga_rows=list(legal_payload.get("ranking") or []),
    )
    return {
        "rows": rows,
        "fra_years": years,
        "ilga_year": _safe_int(legal_payload.get("year")),
    }


def _build_fra_statistics(query: FraStatisticsQuery) -> dict[str, Any]:
    pipeline_started_at = time.perf_counter()
    clean_code = str(query.question_code or "").strip()
    logger.info(
        "statistics_query indicator=%s demographic=%s:%s identity=%s:%s",
        clean_code,
        query.filter_a_name,
        query.filter_a_value,
        query.filter_b_name,
        query.filter_b_value,
    )
    dataframe = _fra_dataframe_for_code(clean_code, query.category, query.year)
    load_ms = (time.perf_counter() - pipeline_started_at) * 1000

    if dataframe.empty:
        logger.info(
            "fra_statistics_pipeline status=empty load_ms=%.2f processing_ms=0 total_ms=%.2f",
            load_ms,
            (time.perf_counter() - pipeline_started_at) * 1000,
        )
        return _status("empty", NO_DATA_MESSAGE)
    filter_validation = validate_statistics_filter_combination(
        StatisticsFilters.from_raw(
            query.filter_a_name,
            query.filter_a_value,
            query.filter_b_name,
            query.filter_b_value,
        ),
        available_values=_available_filter_values(dataframe),
    )
    if not filter_validation.ok:
        logger.warning(
            "statistics_query_rejected indicator=%s reason=%s",
            clean_code,
            filter_validation.message,
        )
        return _status("invalid", filter_validation.message)
    processing_started_at = time.perf_counter()
    source_dataframe = dataframe
    effective_answer = query.answer or _default_fra_answer_from_dataframe(dataframe, query)
    dataframe = filter_fra_dataframe(dataframe, query, effective_answer=effective_answer)
    if dataframe.empty:
        processing_ms = (time.perf_counter() - processing_started_at) * 1000
        logger.info(
            "fra_statistics_pipeline status=empty load_ms=%.2f processing_ms=%.2f total_ms=%.2f",
            load_ms,
            processing_ms,
            (time.perf_counter() - pipeline_started_at) * 1000,
        )
        return _status("empty", NO_DATA_MESSAGE)
    detail_dataframe, country_universe, detail_diagnostics = _prepare_fra_response_details(
        source_dataframe,
        query,
        effective_answer=effective_answer,
    )

    ranking = aggregate_fra_data(dataframe, ["country", "iso"], "percentage", "mean")
    ranking = ranking.rename(columns={"percentage": "value"})
    ranking = _complete_country_ranking(
        ranking,
        source_dataframe,
        countries=query.countries,
    )
    question = next(
        (
            str(value)
            for value in source_dataframe["question"].dropna().unique().tolist()
            if str(value).strip()
        ),
        clean_code,
    )
    result = {
        "status": "ok",
        "message": "",
        "source": "FRA",
        "year": query.year,
        "category": query.category,
        "indicator": question,
        "indicator_code": clean_code,
        "answer": effective_answer,
        "response_type": detect_fra_response_type(
            source_dataframe["answer"].dropna().unique().tolist(),
            question=question,
            specific_category=next(
                (
                    str(value)
                    for value in source_dataframe.get(
                        "specific_category", pd.Series(dtype=str)
                    )
                    .dropna()
                    .unique()
                    .tolist()
                    if str(value).strip()
                ),
                "",
            ),
        ).value,
        "filters": StatisticsFilters.from_raw(
            query.filter_a_name,
            query.filter_a_value,
            query.filter_b_name,
            query.filter_b_value,
        ).as_query_fields(),
        "data": dataframe.to_dict("records"),
        "detail_data": detail_dataframe.to_dict("records"),
        "country_universe": country_universe.to_dict("records"),
        "response_details_diagnostics": detail_diagnostics,
        "available_countries": sorted(
            value for value in country_universe["iso"].dropna().astype(str).tolist() if value
        ),
        "ranking": ranking.to_dict("records"),
        "metrics": _metrics_from_values(ranking["value"].tolist()),
        "methodology": (
            "FRA refleja respuestas de personas encuestadas. "
            "La puntuación ILGA mide leyes y políticas. "
            "Las fuentes no son directamente equivalentes."
        ),
    }
    processing_ms = (time.perf_counter() - processing_started_at) * 1000
    logger.info(
        "statistics_query_resolved indicator=%s documents=%d demographic=%s:%s "
        "identity=%s:%s total_ms=%.2f",
        clean_code,
        len(dataframe),
        query.filter_a_name,
        query.filter_a_value,
        query.filter_b_name,
        query.filter_b_value,
        (time.perf_counter() - pipeline_started_at) * 1000,
    )
    logger.debug(
        "fra_statistics_pipeline status=ok load_ms=%.2f processing_ms=%.2f total_ms=%.2f",
        load_ms,
        processing_ms,
        (time.perf_counter() - pipeline_started_at) * 1000,
    )
    return result


def _prepare_fra_response_details(
    source_dataframe: pd.DataFrame,
    query: FraStatisticsQuery,
    *,
    effective_answer: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Build the single canonical dataframe used by response details.

    The country universe is derived from the same year and sociodemographic
    scope as the detail rows. It deliberately ignores map selection and keeps
    rows with a missing percentage so absence is never converted to zero.
    """
    rows_loaded = len(source_dataframe)
    countries_before = int(source_dataframe["iso"].replace("", pd.NA).nunique())
    detail = filter_fra_comparison_dataframe(source_dataframe, query).copy()

    detail["country_code"] = detail["iso"].fillna("").map(normalize_country_code)
    detail["country_name"] = detail["country"].fillna("").astype(str).str.strip()
    detail["response"] = detail["answer"].fillna("").astype(str).str.strip()
    detail["indicator_id"] = detail["question_code"].fillna("").astype(str).str.strip()

    missing_iso_mask = detail["country_code"].eq("")
    missing_country_mask = detail["country_name"].eq("")
    missing_response_mask = detail["response"].eq("")
    aggregate_mask = detail["country_code"].str.upper().str.fullmatch(
        r"EU\d{2}", na=False
    ) | detail["country_name"].str.upper().str.fullmatch(r"EU-?\d{2}", na=False)
    discarded_mask = (
        missing_iso_mask | missing_country_mask | missing_response_mask | aggregate_mask
    )
    discarded_reasons = {
        "missing_country_code": int(missing_iso_mask.sum()),
        "missing_country_name": int(missing_country_mask.sum()),
        "missing_response": int(missing_response_mask.sum()),
        "non_country_aggregate": int(aggregate_mask.sum()),
    }
    detail = detail.loc[~discarded_mask].copy()
    detail["iso"] = detail["country_code"]
    detail["country"] = detail["country_name"]
    detail["answer"] = detail["response"]
    detail["question_code"] = detail["indicator_id"]

    duplicate_mask = detail.duplicated(["country_code", "response"], keep=False)
    duplicate_groups = int(
        detail.loc[duplicate_mask, ["country_code", "response"]].drop_duplicates().shape[0]
    )
    country_universe = _fra_country_universe(detail, None)
    country_codes = set(country_universe["country_code"].astype(str))
    selected_answer_rows = detail[detail["response"].eq(str(effective_answer or ""))]
    countries_with_data = set(
        selected_answer_rows.loc[selected_answer_rows["percentage"].notna(), "country_code"].astype(
            str
        )
    ).intersection(country_codes)
    countries_without_data = country_codes.difference(countries_with_data)
    diagnostics = {
        "records_loaded": rows_loaded,
        "records_after_filters": len(detail),
        "countries_before_filters": countries_before,
        "countries_loaded": len(country_codes),
        "countries_rendered": len(countries_with_data),
        "countries_without_data": len(countries_without_data),
        "duplicate_country_response_groups": duplicate_groups,
        "discarded": discarded_reasons,
    }
    logger.info(
        "response_details countries_loaded=%d countries_rendered=%d countries_without_data=%d",
        diagnostics["countries_loaded"],
        diagnostics["countries_rendered"],
        diagnostics["countries_without_data"],
        extra={"question_code": query.question_code, **diagnostics},
    )
    if any(discarded_reasons.values()) or duplicate_groups:
        logger.debug(
            "response_details_quality discarded=%r duplicate_country_response_groups=%d",
            discarded_reasons,
            duplicate_groups,
            extra={"question_code": query.question_code, **diagnostics},
        )
    return detail, country_universe, diagnostics


def _fra_country_universe(dataframe: pd.DataFrame, year: int | None) -> pd.DataFrame:
    """Canonical country universe represented by the supplied filtered rows."""
    universe = dataframe.copy()
    if year is not None and "year" in universe:
        universe = universe[(universe["year"].isna()) | (universe["year"] == year)]
    universe = universe[
        ~universe["iso"].astype(str).str.upper().str.fullmatch(r"EU\d{2}", na=False)
        & ~universe["country"].astype(str).str.upper().str.fullmatch(r"EU-?\d{2}", na=False)
    ]
    optional_columns = [
        column for column in ("question", "question_code", "indicator_id") if column in universe
    ]
    country_universe = universe[["country", "iso", "year", "source", *optional_columns]].copy()
    country_universe["country_code"] = country_universe["iso"].map(normalize_country_code)
    country_universe["country_name"] = country_universe["country"].astype(str).str.strip()
    return (
        country_universe[
            country_universe["country_code"].ne("") & country_universe["country_name"].ne("")
        ]
        .sort_values(["country_name", "country_code"])
        .drop_duplicates("country_code", keep="first")
        .reset_index(drop=True)
    )


def _fra_dataframe_for_code(
    code: str,
    category: str | None = None,
    year: int | None = None,
) -> pd.DataFrame:
    if not code:
        return _empty_fra_dataframe()
    clean_category = str(category or "").strip()
    cache_key = (
        f"fra-normalized-frame-v5:{analytics_cache_generation(fra_cache_namespace(year))}:"
        f"{code}:{clean_category}:{year if year is not None else 'all-years'}"
    )
    cached = _server_cache_get(cache_key)
    if isinstance(cached, pd.DataFrame):
        logger.info(
            "statistics_frame_loaded indicator=%s query_ms=0 normalization_ms=0 cache_hit=true",
            code,
        )
        return cached.copy(deep=True)

    query_started_at = time.perf_counter()
    document = (
        get_fra_indicator_answers(code, clean_category, year)
        if clean_category
        else get_fra_indicator_answers(code, year=year)
    )
    query_ms = (time.perf_counter() - query_started_at) * 1000
    normalization_started_at = time.perf_counter()
    dataframe = fra_document_to_dataframe(document)
    normalization_ms = (time.perf_counter() - normalization_started_at) * 1000
    logger.info(
        "statistics_frame_loaded indicator=%s rows=%d query_ms=%.2f "
        "normalization_ms=%.2f cache_hit=false",
        code,
        len(dataframe),
        query_ms,
        normalization_ms,
    )
    if not dataframe.empty:
        _server_cache_set(cache_key, dataframe.copy(deep=True))
    return dataframe


def _fra_statistics_cache_key(query: FraStatisticsQuery) -> str:
    identity = {
        "cache_generation": analytics_cache_generation(fra_cache_namespace(query.year)),
        "year": query.year,
        "countries": sorted(str(country) for country in query.countries),
        "category": query.category,
        "question_code": query.question_code,
        "answer": query.answer,
        "filter_a_name": query.filter_a_name,
        "filter_a_value": query.filter_a_value,
        "filter_b_name": query.filter_b_name,
        "filter_b_value": query.filter_b_value,
        "group_by": list(query.group_by),
        "mode": query.mode,
    }
    serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"fra-statistics-v7:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def _server_cache_get(key: str) -> Any:
    if not getattr(cache, "app", None):
        return None
    try:
        return cache.get(key)
    except Exception:
        logger.debug("statistics_cache_read_failed", extra={"cache_key": key}, exc_info=True)
        return None


def _server_cache_set(key: str, value: Any) -> None:
    if not getattr(cache, "app", None):
        return
    try:
        cache.set(key, value, timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
    except Exception:
        logger.debug("statistics_cache_write_failed", extra={"cache_key": key}, exc_info=True)


def get_experience_legal_radar(
    query: ExperienceLegalRadarQuery,
) -> dict[str, Any]:
    """Build comparable FRA/ILGA dimensions without per-country queries.

    FRA scores use the stored final percentages. Only indicators explicitly
    marked ``invert`` are transformed as ``100 - percentage``. ILGA legal
    scores are the awarded criterion points divided by their available maximum
    weight, expressed on a 0-100 scale.
    """
    identity = {
        "mapping_version": RADAR_MAPPING_VERSION,
        "fra_cache_generation": analytics_cache_generation("fra"),
        "ilga_cache_generation": analytics_cache_generation("ilga"),
        "fra_year": query.fra_year,
        "ilga_year": query.ilga_year,
        "countries": sorted(query.countries),
        "filter_a_name": query.filter_a_name,
        "filter_a_value": query.filter_a_value,
        "filter_b_name": query.filter_b_name,
        "filter_b_value": query.filter_b_value,
    }
    serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    cache_key = f"experience-legal-radar:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"
    cached = _server_cache_get(cache_key)
    if isinstance(cached, dict):
        return deepcopy(cached)

    fra_rows = _experience_radar_rows(query)
    legal_rows, effective_ilga_year = _legal_radar_rows(query)
    if fra_rows.empty or legal_rows.empty:
        result = {
            "status": "empty",
            "rows": [],
            "dimensions": _radar_dimension_metadata(),
            "mapping_version": RADAR_MAPPING_VERSION,
            "fra_year": query.fra_year,
            "ilga_year": effective_ilga_year,
        }
        _server_cache_set(cache_key, deepcopy(result))
        return result

    merged = fra_rows.rename(columns={"country": "experience_country"}).merge(
        legal_rows.rename(columns={"country": "legal_country"}),
        on=["iso", "dimension"],
        how="outer",
        validate="one_to_one",
    )
    merged["country"] = merged["experience_country"].combine_first(merged["legal_country"])
    merged = merged.drop(columns=["experience_country", "legal_country"])
    selected = {
        normalize_country_code(country) or str(country).strip().upper()
        for country in query.countries
    }
    if selected:
        merged = merged[merged["iso"].isin(selected)]
    merged = merged.sort_values(["country", "dimension"], kind="stable")
    serialized_rows = merged.astype(object).where(pd.notna(merged), None).to_dict("records")
    result = {
        "status": "ok" if not merged.empty else "empty",
        "rows": serialized_rows,
        "dimensions": _radar_dimension_metadata(),
        "mapping_version": RADAR_MAPPING_VERSION,
        "fra_year": _effective_dataframe_year(fra_rows, query.fra_year),
        "ilga_year": effective_ilga_year,
        "sources": {"experience": "FRA", "legal": "ILGA-Europe"},
        "methodology": (
            "FRA percentages are used as published; only D1_1 and D1_2_f are explicitly "
            "inverted because a higher discrimination percentage means a worse experience. "
            "ILGA criterion points are normalized against their available weights."
        ),
    }
    _server_cache_set(cache_key, deepcopy(result))
    return result


def _radar_dimension_metadata() -> list[dict[str, str]]:
    return [
        {
            "key": key,
            "label_es": str(mapping["label_es"]),
            "label_en": str(mapping["label_en"]),
        }
        for key, mapping in RADAR_DIMENSION_MAPPING.items()
    ]


def _experience_radar_rows(query: ExperienceLegalRadarQuery) -> pd.DataFrame:
    dataframe = _experience_radar_base_dataframe(query.fra_year)
    if dataframe.empty:
        return pd.DataFrame(columns=["iso", "country", "dimension", "experience_score", "fra_year"])

    filter_query = FraStatisticsQuery(
        year=query.fra_year,
        filter_a_name=query.filter_a_name,
        filter_a_value=query.filter_a_value,
        filter_b_name=query.filter_b_name,
        filter_b_value=query.filter_b_value,
    )
    matched = filter_fra_comparison_dataframe(dataframe, filter_query)
    if matched.empty:
        return pd.DataFrame(columns=["iso", "country", "dimension", "experience_score", "fra_year"])

    matched = matched.copy()
    matched["experience_score"] = matched["percentage"].where(
        ~matched["invert"], 100 - matched["percentage"]
    )
    return matched.groupby(["iso", "dimension"], as_index=False, dropna=False).agg(
        country=("country", "first"),
        experience_score=("experience_score", "mean"),
        fra_year=("year", "max"),
    )


def _experience_radar_base_dataframe(year: int | None) -> pd.DataFrame:
    cache_key = (
        f"experience-radar-frame-v2:{RADAR_MAPPING_VERSION}:"
        f"{analytics_cache_generation('fra')}:{year if year is not None else 'all-years'}"
    )
    cached = _server_cache_get(cache_key)
    if isinstance(cached, pd.DataFrame):
        logger.info(
            "statistics_radar_frame_loaded year=%s rows=%d normalization_ms=0 cache_hit=true",
            year,
            len(cached),
        )
        return cached.copy(deep=True)

    started_at = time.perf_counter()
    fra_configs = [
        {"dimension": dimension, **indicator}
        for dimension, mapping in RADAR_DIMENSION_MAPPING.items()
        for indicator in mapping["fra"]
    ]
    codes = tuple(config["code"] for config in fra_configs)
    documents = get_fra_indicator_documents(codes, year)
    frames = [fra_document_to_dataframe(document) for document in documents]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame()

    dataframe = pd.concat(frames, ignore_index=True)
    config_frame = pd.DataFrame(fra_configs)
    config_frame["answer_key"] = config_frame["answer"].map(normalize_text_key)
    dataframe["answer_key"] = dataframe["answer"].map(normalize_text_key)
    matched = dataframe.merge(
        config_frame[["code", "answer_key", "dimension", "invert"]],
        left_on=["question_code", "answer_key"],
        right_on=["code", "answer_key"],
        how="inner",
        validate="many_to_one",
    )
    matched["percentage"] = pd.to_numeric(matched["percentage"], errors="coerce")
    matched = matched[matched["percentage"].between(0, 100, inclusive="both")]
    matched = matched[
        matched["iso"].astype(str).str.strip().ne("")
        & ~matched["iso"].astype(str).str.upper().str.fullmatch(r"EU\d{2}", na=False)
    ]
    compact_columns = [
        "iso",
        "country",
        "dimension",
        "percentage",
        "invert",
        "year",
        "filter_a",
        "filter_b",
    ]
    matched = matched[compact_columns].reset_index(drop=True)
    if not matched.empty:
        _server_cache_set(cache_key, matched.copy(deep=True))
    logger.info(
        "statistics_radar_frame_loaded year=%s rows=%d normalization_ms=%.2f cache_hit=false",
        year,
        len(matched),
        (time.perf_counter() - started_at) * 1000,
    )
    return matched


def _legal_radar_rows(
    query: ExperienceLegalRadarQuery,
) -> tuple[pd.DataFrame, int | None]:
    document = get_ilga_document_by_year(query.ilga_year)
    dataframe = ilga_document_to_dataframe(document)
    effective_year = (
        _safe_int(document.get("year")) if isinstance(document, dict) else query.ilga_year
    )
    if dataframe.empty:
        return (
            pd.DataFrame(columns=["iso", "country", "dimension", "legal_score"]),
            effective_year,
        )

    groups: list[pd.DataFrame] = []
    for dimension, mapping in RADAR_DIMENSION_MAPPING.items():
        legal_mapping = mapping["ilga"]
        rows = dataframe[dataframe["category"].eq(legal_mapping["category"])].copy()
        prefixes = tuple(normalize_text_key(prefix) for prefix in legal_mapping["prefixes"])
        if prefixes:
            criterion_keys = rows["criterion"].map(normalize_text_key)
            rows = rows[criterion_keys.str.startswith(prefixes, na=False)]
        if rows.empty:
            continue
        rows["dimension"] = dimension
        groups.append(rows)
    if not groups:
        return (
            pd.DataFrame(columns=["iso", "country", "dimension", "legal_score"]),
            effective_year,
        )

    criteria = pd.concat(groups, ignore_index=True)
    criteria["criterion_value"] = pd.to_numeric(criteria["criterion_value"], errors="coerce")
    criteria["criterion_weight"] = pd.to_numeric(criteria["criterion_weight"], errors="coerce")
    criteria = criteria[
        criteria["criterion_value"].notna()
        & criteria["criterion_weight"].gt(0)
        & criteria["iso"].astype(str).str.strip().ne("")
    ]
    if criteria.empty:
        return (
            pd.DataFrame(columns=["iso", "country", "dimension", "legal_score"]),
            effective_year,
        )
    criteria["weighted_value"] = criteria["criterion_value"] * criteria["criterion_weight"]
    grouped = criteria.groupby(["iso", "dimension"], as_index=False, dropna=False).agg(
        country=("country", "first"),
        weighted_value=("weighted_value", "sum"),
        available_weight=("criterion_weight", "sum"),
    )
    grouped["legal_score"] = (100 * grouped["weighted_value"] / grouped["available_weight"]).clip(
        0, 100
    )
    return grouped[["iso", "country", "dimension", "legal_score"]], effective_year


def _effective_dataframe_year(dataframe: pd.DataFrame, fallback: int | None) -> int | None:
    years = pd.to_numeric(
        dataframe.get("fra_year", pd.Series(dtype=float)), errors="coerce"
    ).dropna()
    return int(years.max()) if not years.empty else fallback


def get_ilga_statistics(
    query: IlgaStatisticsQuery,
    *,
    include_history: bool = True,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    cache_key = _ilga_statistics_cache_key(query, include_history=include_history)
    cached = _server_cache_get(cache_key)
    if isinstance(cached, dict):
        logger.info(
            "statistics_loaded source=ilga category=%s total_ms=%.2f cache_hit=true",
            query.category,
            (time.perf_counter() - started_at) * 1000,
        )
        return deepcopy(cached)

    result = _build_ilga_statistics(query, include_history=include_history)
    if result.get("status") == "ok":
        _server_cache_set(cache_key, deepcopy(result))
    logger.info(
        "statistics_loaded source=ilga category=%s status=%s total_ms=%.2f cache_hit=false",
        query.category,
        result.get("status"),
        (time.perf_counter() - started_at) * 1000,
    )
    return result


def _build_ilga_statistics(
    query: IlgaStatisticsQuery,
    *,
    include_history: bool,
) -> dict[str, Any]:
    query_started_at = time.perf_counter()
    raw_rows = get_ilga_analysis_rows(query.category, query.criterion)
    query_ms = (time.perf_counter() - query_started_at) * 1000
    normalization_started_at = time.perf_counter()
    source_dataframe = ilga_analysis_rows_to_dataframe(raw_rows)
    normalization_ms = (time.perf_counter() - normalization_started_at) * 1000
    if source_dataframe.empty:
        return _status("empty", "No hay datos ILGA-Europe para el año seleccionado.")

    available_years = sorted(
        int(year) for year in source_dataframe["year"].dropna().unique().tolist()
    )
    effective_year = query.year if query.year is not None else max(available_years, default=None)
    if effective_year not in available_years:
        return _status("empty", "No hay datos ILGA-Europe para el año seleccionado.")

    grouping_started_at = time.perf_counter()
    current_year = source_dataframe[source_dataframe["year"].eq(effective_year)].copy()
    country_universe = _ilga_country_universe(current_year, countries=query.countries)
    current_selection = _ilga_selected_rows(current_year, query)
    ranking = _ilga_ranking_from_analysis(current_selection, query)
    if ranking.empty and current_selection.empty:
        return _status("empty", "No hay datos ILGA-Europe para la combinación seleccionada.")
    ranking = _complete_country_ranking(
        ranking,
        country_universe,
        countries=query.countries,
    )
    history_dataframe = _ilga_history_dataframe(
        source_dataframe,
        category=query.category,
        criterion=query.criterion,
    )
    detail_dataframe, response_diagnostics = _prepare_ilga_response_details(
        current_selection,
        country_universe,
        query,
    )
    grouping_ms = (time.perf_counter() - grouping_started_at) * 1000
    history_records = history_dataframe.to_dict("records") if include_history else []
    logger.info(
        "legal_statistics_pipeline query_ms=%.2f normalization_ms=%.2f grouping_ms=%.2f",
        query_ms,
        normalization_ms,
        grouping_ms,
        extra={
            "query_ms": round(query_ms, 2),
            "normalization_ms": round(normalization_ms, 2),
            "grouping_ms": round(grouping_ms, 2),
            "category": query.category,
            "criterion": query.criterion,
            "year": effective_year,
        },
    )
    logger.info(
        "legal_temporal_evolution countries_loaded=%d years_loaded=%d series_rendered=%d",
        int(history_dataframe["country_code"].nunique()) if not history_dataframe.empty else 0,
        int(history_dataframe["year"].nunique()) if not history_dataframe.empty else 0,
        int(history_dataframe["country_code"].nunique()) if not history_dataframe.empty else 0,
    )
    logger.info(
        "legal_response_details countries_loaded=%d responses_detected=%d rows_rendered=%d",
        response_diagnostics["countries_loaded"],
        len(response_diagnostics["responses_detected"]),
        len(detail_dataframe),
        extra=response_diagnostics,
    )
    return {
        "status": "ok",
        "message": "",
        "source": "ILGA-Europe",
        "year": effective_year,
        "category": query.category,
        "indicator": query.criterion or query.category or "Ranking total",
        "criterion": query.criterion,
        "data": current_selection.to_dict("records"),
        "detail_data": detail_dataframe.to_dict("records"),
        "legal_response_details_diagnostics": response_diagnostics,
        "country_universe": country_universe.to_dict("records"),
        "ranking": ranking.to_dict("records"),
        "available_countries": sorted(
            value
            for value in country_universe["iso"].dropna().astype(str).unique().tolist()
            if value
        ),
        "history": history_records,
        "metrics": _metrics_from_values(ranking["value"].tolist()),
        "normalization": _ilga_result_normalization(current_year),
        "methodology": ("ILGA-Europe Rainbow Map mide leyes, políticas y protecciones jurídicas. "),
    }


def _ilga_statistics_cache_key(
    query: IlgaStatisticsQuery,
    *,
    include_history: bool,
) -> str:
    identity = {
        "cache_generation": analytics_cache_generation("ilga"),
        "dataset_years": get_ilga_years(),
        "year": query.year,
        "countries": sorted(str(country) for country in query.countries),
        "category": query.category,
        "criterion": query.criterion,
        "mode": query.mode,
        "include_history": include_history,
    }
    serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"ilga-statistics-v4:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def filter_fra_dataframe(
    dataframe: pd.DataFrame,
    query: FraStatisticsQuery,
    *,
    effective_answer: str | None = None,
) -> pd.DataFrame:
    filtered = dataframe.copy()
    if query.year is not None and "year" in filtered:
        filtered = filtered[filtered["year"] == query.year]
    if query.countries:
        selected = {normalize_country_code(country) or str(country) for country in query.countries}
        filtered = filtered[filtered["iso"].isin(selected) | filtered["country"].isin(selected)]
    selected_answer = effective_answer if effective_answer is not None else query.answer
    if selected_answer:
        filtered = filtered[filtered["answer"] == selected_answer]
    filtered = _apply_exact_filter_scope(filtered, query)
    return filtered


def filter_fra_detail_dataframe(
    dataframe: pd.DataFrame,
    query: FraStatisticsQuery,
) -> pd.DataFrame:
    filtered = dataframe.copy()
    if query.year is not None and "year" in filtered:
        filtered = filtered[filtered["year"] == query.year]
    filtered = _apply_exact_filter_scope(filtered, query)
    return filtered


def filter_fra_comparison_dataframe(
    dataframe: pd.DataFrame,
    query: FraStatisticsQuery,
) -> pd.DataFrame:
    """Return every response using a comparable scope for each response label.

    Some FRA questions store their aggregate response labels under different
    technical filter scopes. Selecting one response must not hide the others.
    """
    filtered = dataframe.copy()
    if query.year is not None and "year" in filtered:
        filtered = filtered[filtered["year"] == query.year]
    if filtered.empty:
        return filtered

    return _apply_exact_filter_scope(filtered, query)


def get_ilga_history_rows(
    category: str | None,
    criterion: str | None,
) -> list[dict[str, Any]]:
    dataframe = ilga_analysis_rows_to_dataframe(get_ilga_analysis_rows(category, criterion))
    history = _ilga_history_dataframe(dataframe, category=category, criterion=criterion)
    return cast(list[dict[str, Any]], history.to_dict("records"))


def filter_ilga_dataframe(dataframe: pd.DataFrame, query: IlgaStatisticsQuery) -> pd.DataFrame:
    filtered = dataframe.copy()
    if query.countries:
        selected = {normalize_country_code(country) or str(country) for country in query.countries}
        filtered = filtered[filtered["iso"].isin(selected) | filtered["country"].isin(selected)]
    if query.category and query.category != "Ranking total":
        filtered = filtered[filtered["category"] == query.category]
    if query.criterion:
        filtered = filtered[filtered["criterion"] == query.criterion]
    return filtered


def _ilga_country_universe(
    dataframe: pd.DataFrame,
    *,
    countries: list[str] | None = None,
) -> pd.DataFrame:
    columns = [
        "country",
        "country_name",
        "iso",
        "country_code",
        "ranking",
        "year",
        "source",
    ]
    if dataframe.empty:
        return pd.DataFrame(columns=columns)
    universe = dataframe[dataframe["category"].eq("Ranking total")][columns].copy()
    if countries:
        selected = {normalize_country_code(country) or str(country) for country in countries}
        universe = universe[universe["iso"].isin(selected) | universe["country"].isin(selected)]
    return universe.sort_values(["ranking", "country"], ascending=[False, True]).reset_index(
        drop=True
    )


def _ilga_selected_rows(dataframe: pd.DataFrame, query: IlgaStatisticsQuery) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe
    category = str(query.category or "Ranking total")
    if category == "Ranking total":
        selected_rows = dataframe[dataframe["category"].eq("Ranking total")].copy()
    else:
        selected_rows = dataframe[dataframe["category"].eq(category)].copy()
        if query.criterion:
            selected_rows = selected_rows[selected_rows["criterion"].eq(query.criterion)]
    if query.countries:
        selected = {normalize_country_code(country) or str(country) for country in query.countries}
        selected_rows = selected_rows[
            selected_rows["iso"].isin(selected) | selected_rows["country"].isin(selected)
        ]
    return selected_rows.reset_index(drop=True)


def _ilga_ranking_from_analysis(
    dataframe: pd.DataFrame,
    query: IlgaStatisticsQuery,
) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(columns=["country", "iso", "value"])
    category = str(query.category or "Ranking total")
    if category == "Ranking total" or query.criterion:
        return dataframe[["country", "iso", "value"]].copy()
    return _ilga_category_scores(dataframe)


def _ilga_history_dataframe(
    dataframe: pd.DataFrame,
    *,
    category: str | None,
    criterion: str | None,
) -> pd.DataFrame:
    columns = [
        "country_code",
        "country_name",
        "year",
        "value",
        "indicator_id",
        "source",
        "iso",
        "country",
        "normalization_applied",
        "normalization_method",
        "original_scale_min",
        "original_scale_max",
        "target_scale_min",
        "target_scale_max",
    ]
    if dataframe.empty:
        return pd.DataFrame(columns=columns)
    clean_category = str(category or "Ranking total")
    if clean_category == "Ranking total":
        history = dataframe[dataframe["category"].eq("Ranking total")][
            [
                "country_code",
                "country_name",
                "year",
                "value",
                "source",
                "iso",
                "country",
                "normalization_applied",
                "normalization_method",
                "original_scale_min",
                "original_scale_max",
                "target_scale_min",
                "target_scale_max",
            ]
        ].copy()
        history["indicator_id"] = "Ranking total"
    elif criterion:
        history = dataframe[
            dataframe["category"].eq(clean_category) & dataframe["criterion"].eq(criterion)
        ][
            [
                "country_code",
                "country_name",
                "year",
                "value",
                "source",
                "iso",
                "country",
                "normalization_applied",
                "normalization_method",
                "original_scale_min",
                "original_scale_max",
                "target_scale_min",
                "target_scale_max",
            ]
        ].copy()
        history["indicator_id"] = str(criterion)
    else:
        grouped_rows: list[pd.DataFrame] = []
        criteria = dataframe[dataframe["category"].eq(clean_category)]
        for year, year_rows in criteria.groupby("year", sort=True):
            scores = _ilga_category_scores(year_rows)
            if scores.empty:
                continue
            parsed_year = _safe_int(year)
            if parsed_year is None:
                continue
            scores["year"] = parsed_year
            scores["country_code"] = scores["iso"]
            scores["country_name"] = scores["country"]
            scores["indicator_id"] = clean_category
            scores["source"] = "ILGA-Europe"
            normalization = _ilga_result_normalization(year_rows)
            scores["normalization_applied"] = bool(normalization.get("applied"))
            scores["normalization_method"] = str(normalization.get("method") or "")
            scores["original_scale_min"] = normalization.get("original_min")
            scores["original_scale_max"] = normalization.get("original_max")
            scores["target_scale_min"] = normalization.get("target_min")
            scores["target_scale_max"] = normalization.get("target_max")
            grouped_rows.append(scores[columns])
        history = pd.concat(grouped_rows, ignore_index=True) if grouped_rows else pd.DataFrame()
    if history.empty:
        return pd.DataFrame(columns=columns)
    history["value"] = pd.to_numeric(history["value"], errors="coerce")
    history = history[history["value"].notna()]
    return (
        history[columns].sort_values(["country_code", "year"], kind="stable").reset_index(drop=True)
    )


def _prepare_ilga_response_details(
    dataframe: pd.DataFrame,
    country_universe: pd.DataFrame,
    query: IlgaStatisticsQuery,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    columns = [
        "country_code",
        "country_name",
        "year",
        "value",
        "indicator_id",
        "source",
        "response",
        "response_order",
        "category",
        "criterion_weight",
        "criterion_value",
        "iso",
        "country",
    ]
    details = dataframe.copy()
    expected_indicators = details["indicator_id"].dropna().astype(str).unique().tolist()
    represented = {
        (str(row.country_code), str(row.indicator_id))
        for row in details[["country_code", "indicator_id"]].itertuples(index=False)
    }
    missing_rows: list[dict[str, Any]] = []
    for country_row in country_universe.itertuples(index=False):
        for indicator_id in expected_indicators:
            if (str(country_row.country_code), indicator_id) in represented:
                continue
            missing_rows.append(
                {
                    "country_code": country_row.country_code,
                    "country_name": country_row.country_name,
                    "year": country_row.year,
                    "value": None,
                    "indicator_id": indicator_id,
                    "source": country_row.source,
                    "response": "not_available",
                    "response_order": ILGA_RESPONSE_ORDER["not_available"],
                    "category": str(query.category or "Ranking total"),
                    "criterion_weight": None,
                    "criterion_value": None,
                    "iso": country_row.iso,
                    "country": country_row.country,
                }
            )
    if missing_rows:
        details = pd.concat([details, pd.DataFrame(missing_rows)], ignore_index=True)
    if details.empty:
        details = pd.DataFrame(columns=columns)
    else:
        details = details[columns].sort_values(
            ["country_name", "response_order", "indicator_id"], kind="stable"
        )
    responses = (
        details[["response", "response_order"]]
        .dropna(subset=["response"])
        .sort_values("response_order", kind="stable")["response"]
        .astype(str)
        .unique()
        .tolist()
    )
    countries_loaded = int(country_universe["country_code"].nunique())
    countries_with_values = int(details.loc[details["value"].notna(), "country_code"].nunique())
    diagnostics = {
        "countries_loaded": countries_loaded,
        "countries_rendered": countries_with_values,
        "countries_without_data": countries_loaded - countries_with_values,
        "responses_detected": responses,
        "rows_rendered": len(details),
    }
    return details.reset_index(drop=True), diagnostics


def aggregate_fra_data(
    dataframe: pd.DataFrame,
    group_by: list[str],
    value_column: str,
    aggregation: str = "mean",
) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(columns=[*group_by, value_column])
    if value_column not in dataframe.columns:
        raise ValueError("invalid_value_column")
    if aggregation not in {"mean", "median", "max", "min", "count", "sum"}:
        raise ValueError("invalid_aggregation")
    if aggregation == "sum" and value_column == "percentage":
        raise ValueError("cannot_sum_percentages")
    missing = [column for column in group_by if column not in dataframe.columns]
    if missing:
        raise ValueError("invalid_group_by")
    numeric_dataframe = dataframe.copy()
    numeric_dataframe[value_column] = pd.to_numeric(
        numeric_dataframe[value_column], errors="coerce"
    )
    grouped = numeric_dataframe.groupby(group_by, dropna=False)[value_column]
    if aggregation == "mean":
        result = grouped.mean()
    elif aggregation == "median":
        result = grouped.median()
    elif aggregation == "max":
        result = grouped.max()
    elif aggregation == "min":
        result = grouped.min()
    elif aggregation == "count":
        result = grouped.count()
    else:
        result = grouped.sum()
    return result.reset_index()


def classify_external_data_error(payload: Any) -> str:
    if isinstance(payload, dict):
        message = " ".join(str(item) for item in payload.get("message", []))
        error = " ".join(str(item) for item in payload.get("error", []))
        if "No data for this query" in message:
            logger.warning("fra_query_without_data", extra={"technical_error": error})
            return "empty"
        if "500" in error:
            logger.error("fra_internal_error", extra={"technical_error": error})
            return "internal_error"
    return "invalid_response"


def _apply_exact_filter_scope(
    dataframe: pd.DataFrame,
    query: FraStatisticsQuery,
) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe
    if "filter_a" not in dataframe.columns or "filter_b" not in dataframe.columns:
        return dataframe

    expected_a, expected_b = (
        _selected_filter_label(query.filter_a_name, query.filter_a_value),
        _selected_filter_label(query.filter_b_name, query.filter_b_value),
    )
    filter_a = dataframe["filter_a"].fillna("").astype(str)
    filter_b = dataframe["filter_b"].fillna("").astype(str)
    return dataframe[filter_a.eq(expected_a) & filter_b.eq(expected_b)]


def _selected_filter_label(filter_name: str | None, filter_value: str | None) -> str:
    clean_name = normalize_filter_type(filter_name)
    clean_value = repair_text_encoding(filter_value).strip()
    if not clean_name or clean_name == "All" or not clean_value or clean_value == "All":
        return "All"
    return normalize_filter_value(clean_value)


def _filters_to_dict(filters: Any) -> dict[str, str]:
    if not isinstance(filters, list):
        return {"All": "All"}
    output: dict[str, str] = {}
    for item in filters:
        if not isinstance(item, dict):
            continue
        filter_type = normalize_filter_type(item.get("type"))
        filter_value = repair_text_encoding(item.get("value")).strip()
        if filter_type and filter_value:
            output[filter_type] = filter_value
    return output or {"All": "All"}


def _present_filter_types(dataframe: pd.DataFrame) -> set[str]:
    present: set[str] = set()
    if dataframe.empty:
        return present
    for filters in dataframe["filters"]:
        if isinstance(filters, dict):
            present.update(normalize_filter_type(key) for key in filters)
    return present


def _available_filter_values(dataframe: pd.DataFrame) -> dict[str, set[str]]:
    available: dict[str, set[str]] = {"All": {"All"}}
    if dataframe.empty or "filters" not in dataframe:
        return available
    for filters in dataframe["filters"]:
        if not isinstance(filters, dict):
            continue
        for raw_type, raw_value in filters.items():
            filter_type = normalize_filter_type(raw_type)
            filter_value = normalize_filter_value(raw_value)
            if filter_type and filter_value:
                available.setdefault(filter_type, set()).add(filter_value)
    return available


def _all_filter_type_available(dataframe: pd.DataFrame, group: str) -> bool:
    if dataframe.empty or "filters" not in dataframe:
        return True
    allowed = FRA_FILTER_GROUP_A if group == "a" else FRA_FILTER_GROUP_B
    return any(not _row_has_group_filter(filters, allowed) for filters in dataframe["filters"])


def _row_has_group_filter(filters: Any, allowed: tuple[str, ...]) -> bool:
    if not isinstance(filters, dict):
        return False
    allowed_keys = {
        normalize_filter_type(filter_type) for filter_type in allowed if filter_type != "All"
    }
    return any(normalize_filter_type(key) in allowed_keys for key in filters)


def _first_matching_filter(filters: dict[str, str], allowed: tuple[str, ...]) -> str:
    for filter_type, filter_value in filters.items():
        clean_type = normalize_filter_type(filter_type)
        if clean_type in allowed and clean_type != "All" and filter_value != "All":
            return normalize_filter_value(filter_value)
    return "All"


def _ilga_category_scores(dataframe: pd.DataFrame) -> pd.DataFrame:
    criteria = dataframe[dataframe["category"] != "Ranking total"].copy()
    criteria["criterion_value"] = pd.to_numeric(criteria["criterion_value"], errors="coerce")
    criteria["criterion_weight"] = pd.to_numeric(criteria["criterion_weight"], errors="coerce")
    criteria = criteria[
        criteria["criterion_value"].notna()
        & criteria["criterion_weight"].notna()
        & criteria["criterion_weight"].gt(0)
    ]
    if criteria.empty:
        return pd.DataFrame(columns=["country", "iso", "value"])
    criteria["weighted_value"] = criteria["criterion_value"] * criteria["criterion_weight"]
    criteria["weight"] = criteria["criterion_weight"]
    grouped = criteria.groupby(["country", "iso"], dropna=False)[["weighted_value", "weight"]].sum()
    grouped["value"] = 100 * grouped["weighted_value"] / grouped["weight"]
    return grouped.reset_index()[["country", "iso", "value"]]


def _complete_country_ranking(
    ranking: pd.DataFrame,
    source_dataframe: pd.DataFrame,
    *,
    countries: list[str] | None = None,
) -> pd.DataFrame:
    """Enrich one European result set once, retaining countries without values."""
    universe = source_dataframe[["country", "iso"]].copy()
    universe["iso"] = universe["iso"].fillna("").astype(str).str.upper()
    universe = universe[
        universe["country"].notna()
        & universe["country"].astype(str).str.strip().ne("")
        & ~universe["iso"].str.fullmatch(r"EU\d{2}", na=False)
    ].drop_duplicates("iso", keep="first")
    if countries:
        selected = {normalize_country_code(country) or str(country) for country in countries}
        universe = universe[universe["iso"].isin(selected) | universe["country"].isin(selected)]

    values = (
        ranking[["iso", "value"]].copy()
        if not ranking.empty
        else pd.DataFrame(columns=["iso", "value"])
    )
    values["iso"] = values["iso"].fillna("").astype(str).str.upper()
    values["value"] = pd.to_numeric(values["value"], errors="coerce")
    values = values.groupby("iso", as_index=False, dropna=False)["value"].mean()

    completed = universe.merge(values, on="iso", how="left", validate="one_to_one")
    numeric_values = completed["value"].dropna()
    european_mean = float(numeric_values.mean()) if not numeric_values.empty else None
    completed["position"] = completed["value"].rank(
        method="min",
        ascending=False,
        na_option="keep",
    )
    completed["difference"] = (
        completed["value"] - european_mean if european_mean is not None else None
    )
    completed["absolute_difference"] = (
        completed["difference"].abs() if european_mean is not None else None
    )
    completed["percentage_difference"] = (
        completed["difference"] / european_mean * 100 if european_mean not in (None, 0) else None
    )
    completed["european_mean"] = european_mean
    completed = completed.sort_values(
        ["value", "country"],
        ascending=[False, True],
        na_position="last",
    )
    for column in (
        "value",
        "position",
        "difference",
        "absolute_difference",
        "percentage_difference",
        "european_mean",
    ):
        completed[column] = (
            completed[column]
            .astype(object)
            .where(
                pd.notna(completed[column]),
                None,
            )
        )
    completed["position"] = pd.Series(
        [
            int(value) if value is not None and pd.notna(value) else None
            for value in completed["position"].tolist()
        ],
        index=completed.index,
        dtype=object,
    )
    return completed.reset_index(drop=True)


def _metrics_from_values(values: list[float]) -> dict[str, Any]:
    series = pd.Series([value for value in values if pd.notna(value)], dtype="float")
    if series.empty:
        return {}
    return {
        "mean": round(float(series.mean()), 2),
        "median": round(float(series.median()), 2),
        "max": round(float(series.max()), 2),
        "min": round(float(series.min()), 2),
        "countries": int(series.count()),
    }


def _extract_year(value: Any) -> int | None:
    text = str(value or "")
    match = re.search(r"(?<!\d)(20\d{2})(?!\d)", text)
    return int(match.group(1)) if match else None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _safe_float(value: Any) -> float | None:
    return coerce_percentage(value)


def _safe_unit_score(value: Any) -> float | None:
    try:
        numeric = float(value)
    except TypeError, ValueError:
        return None
    return numeric if pd.notna(numeric) and 0 <= numeric <= 1 else None


def _safe_positive_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except TypeError, ValueError:
        return None
    return numeric if pd.notna(numeric) and numeric > 0 else None


def _answer_percentage_value(answer: dict[str, Any]) -> Any:
    if "percentage" in answer:
        return answer.get("percentage")
    return answer.get("value")


def _default_fra_answer_from_dataframe(
    dataframe: pd.DataFrame,
    query: FraStatisticsQuery,
) -> str | None:
    if dataframe.empty or "answer" not in dataframe:
        return None
    scoped = _apply_exact_filter_scope(dataframe, query)
    if scoped.empty:
        return None
    values = {
        str(row.answer): normalize_filter_value(row.answer)
        for row in scoped[["answer"]].drop_duplicates().itertuples()
        if str(row.answer or "").strip()
    }
    if not values:
        return None
    ordered = order_fra_responses(
        sorted(values, key=lambda value: values[value].casefold()),
        response_type=detect_fra_response_type(values),
    )
    return _preferred_fra_answer(ordered, set(ordered))


def _global_answers_from_control_document(document: dict[str, Any]) -> set[str]:
    declared = {
        str(value).strip()
        for value in document.get("global_answers", [])
        if str(value or "").strip()
    }
    if declared:
        return declared
    return {
        repair_text_encoding(answer.get("answer")).strip()
        for answer in document.get("answers", [])
        if isinstance(answer, dict)
        and _filters_to_dict(answer.get("filters")).get("All") == "All"
        and repair_text_encoding(answer.get("answer")).strip()
    }


def _preferred_fra_answer(ordered_answers: list[str], available_answers: set[str]) -> str | None:
    available_by_key = {
        normalize_text_key(answer): answer
        for answer in ordered_answers
        if answer in available_answers
    }
    for preferred in DEFAULT_FRA_ANSWER_PRIORITY:
        found = available_by_key.get(normalize_text_key(preferred))
        if found:
            return found
    return next((answer for answer in ordered_answers if answer in available_answers), None)


def _status(status: str, message: str) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "data": [],
        "ranking": [],
        "metrics": {},
        "methodology": "",
    }


def _empty_fra_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "source",
            "category",
            "specific_category",
            "question",
            "question_code",
            "country",
            "iso",
            "answer",
            "answer_label",
            "percentage",
            "year",
            "filters",
            "filter_a",
            "filter_b",
        ]
    )


def _empty_ilga_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "source",
            "year",
            "country",
            "iso",
            "ranking",
            "category",
            "criterion",
            "criterion_value",
            "criterion_weight",
        ]
    )


def _empty_ilga_analysis_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "document_id",
            "country_index",
            "criterion_index",
            "source",
            "year",
            "country",
            "country_name",
            "iso",
            "country_code",
            "ranking",
            "category",
            "criterion",
            "indicator_id",
            "criterion_value",
            "criterion_weight",
            "value",
            "response",
            "response_order",
            "normalization_applied",
            "normalization_method",
            "original_scale_min",
            "original_scale_max",
            "target_scale_min",
            "target_scale_max",
        ]
    )
