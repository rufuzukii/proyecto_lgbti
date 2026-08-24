from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, cast

import numpy as np
import pandas as pd

from app.analytics.statistics_normalizers import normalize_country_code

MINIMUM_ANALYSIS_N = 5
NORMAL_ANALYSIS_N = 10

_ADVERSE_QUESTION_TERMS = {
    "abuse",
    "afraid",
    "assault",
    "attack",
    "avoid",
    "bad",
    "bully",
    "discrimin",
    "fear",
    "harass",
    "hate",
    "hide",
    "insult",
    "offensive",
    "problem",
    "threat",
    "victim",
    "violence",
    "acoso",
    "agres",
    "miedo",
    "odio",
    "violencia",
}
_FAVOURABLE_QUESTION_TERMS = {
    "accept",
    "comfortable",
    "fair",
    "good",
    "open",
    "protect",
    "safe",
    "satisf",
    "support",
    "trust",
    "acept",
    "apoyo",
    "comod",
    "proteg",
    "satis",
    "segur",
}
_AFFIRMATIVE_ANSWERS = {
    "yes",
    "often",
    "always",
    "very often",
    "agree",
    "strongly agree",
    "good",
    "very good",
    "si",
    "a menudo",
    "siempre",
    "de acuerdo",
    "bueno",
    "muy bueno",
}
_NEGATIVE_ANSWERS = {
    "no",
    "never",
    "rarely",
    "disagree",
    "strongly disagree",
    "bad",
    "very bad",
    "nunca",
    "raramente",
    "en desacuerdo",
    "malo",
    "muy malo",
}

_YES_NO_ANSWERS = {"yes", "no", "si"}
_QUANTITATIVE_ANSWER_PATTERN = re.compile(
    r"^(?:(?:less than|more than|at least|at most|menos de|mas de|al menos|como maximo)\s*|[<>]=?\s*)?"
    r"\d+(?:[.,]\d+)?(?:\s*(?:%|years?|anos?|times?|veces))?$"
    r"|^\d+(?:[.,]\d+)?\s*(?:-|\u2013|\u2014|to|a)\s*\d+(?:[.,]\d+)?"
    r"(?:\s*(?:%|years?|anos?|times?|veces))?$"
)


def nearest_ilga_year(fra_year: int | None, available_years: list[int]) -> int | None:
    """Return the closest legal-data year; ties prefer the earlier observation."""
    years = sorted({int(year) for year in available_years})
    if not years:
        return None
    if fra_year is None:
        return years[-1]
    return min(years, key=lambda year: (abs(year - int(fra_year)), year > int(fra_year), year))


def infer_indicator_semantics(question: Any, answer: Any) -> dict[str, str]:
    """Conservatively describe what a high selected-response percentage means."""
    question_key = _semantic_key(question)
    answer_key = _semantic_key(answer)
    question_tone = _matching_tone(question_key)
    if answer_key in _AFFIRMATIVE_ANSWERS:
        answer_polarity = "affirmative"
    elif answer_key in _NEGATIVE_ANSWERS:
        answer_polarity = "negative"
    else:
        answer_polarity = "unknown"

    direction = "unknown"
    if question_tone == "adverse" and answer_polarity == "affirmative":
        direction = "adverse"
    elif (
        question_tone == "adverse" and answer_polarity == "negative"
    ) or (
        question_tone == "favourable" and answer_polarity == "affirmative"
    ):
        direction = "favourable"
    elif question_tone == "favourable" and answer_polarity == "negative":
        direction = "adverse"
    return {
        "direction": direction,
        "question_tone": question_tone,
        "answer_polarity": answer_polarity,
    }


def quadrant_eligibility(question: Any, answer: Any) -> dict[str, Any]:
    """Decide whether a selected FRA response supports a quadrant comparison.

    Yes/no answers additionally require question wording with a safely inferred
    favourable/adverse direction. Numeric answers can be compared relative to
    the median, but remain neutral unless their meaning is explicit.
    """
    question_key = _semantic_key(question)
    answer_key = _semantic_key(answer)
    semantics = infer_indicator_semantics(question, answer)
    if not question_key or not answer_key:
        return {
            "eligible": False,
            "response_kind": "missing",
            "reason": "missing_question_or_answer",
        }
    if answer_key in _YES_NO_ANSWERS:
        eligible = semantics["direction"] in {"favourable", "adverse"}
        return {
            "eligible": eligible,
            "response_kind": "yes_no",
            "reason": "" if eligible else "ambiguous_question_semantics",
        }
    if _QUANTITATIVE_ANSWER_PATTERN.fullmatch(answer_key):
        return {
            "eligible": True,
            "response_kind": "quantitative",
            "reason": "",
        }
    return {
        "eligible": False,
        "response_kind": "unsupported",
        "reason": "unsupported_response",
    }


def build_combined_analysis(
    fra_result: dict[str, Any],
    ilga_result: dict[str, Any],
) -> dict[str, Any]:
    rows = combine_country_rows(
        list(fra_result.get("ranking") or []),
        list(ilga_result.get("ranking") or []),
    )
    metrics = combined_metrics(rows)
    semantics = infer_indicator_semantics(
        fra_result.get("indicator"), fra_result.get("answer")
    )
    eligibility = quadrant_eligibility(
        fra_result.get("indicator"), fra_result.get("answer")
    )
    supported = get_combined_analysis_capabilities(
        question=fra_result.get("indicator"),
        answer=fra_result.get("answer"),
        rows=rows,
        semantics=semantics,
        quadrant=eligibility,
    )
    return {
        "rows": rows,
        "metrics": metrics,
        "semantics": semantics,
        "quadrant_eligibility": eligibility,
        "supported_analyses": supported,
        "ranking_gap": ranking_position_rows(rows, semantics["direction"]),
        "fra_year": _safe_int(fra_result.get("year")),
        "ilga_year": _safe_int(ilga_result.get("year")),
        "indicator": str(fra_result.get("indicator") or "").strip(),
        "indicator_code": str(fra_result.get("indicator_code") or "").strip(),
        "answer": str(fra_result.get("answer") or "").strip(),
        "filters": dict(fra_result.get("filters") or {}),
        "normalization": dict(ilga_result.get("normalization") or {}),
    }


def get_combined_analysis_capabilities(
    *,
    question: Any,
    answer: Any,
    rows: list[dict[str, Any]],
    semantics: dict[str, str] | None = None,
    quadrant: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the combined views that are defensible for one FRA selection.

    Compatibility is kept here so UI callbacks never grow answer-specific
    conditions.  A favourable/adverse comparison additionally requires a
    direction that can be inferred safely from the question and answer.
    """
    semantic_result = semantics or infer_indicator_semantics(question, answer)
    quadrant_result = quadrant or quadrant_eligibility(question, answer)
    direction = semantic_result.get("direction", "unknown")
    paired_n = sum(
        1
        for row in rows
        if _finite_float(row.get("fra_value")) is not None
        and _finite_float(row.get("ilga_value")) is not None
    )
    has_direction = direction in {"favourable", "adverse"}
    quadrants = bool(
        quadrant_result.get("eligible")
        and has_direction
        and paired_n >= MINIMUM_ANALYSIS_N
    )
    ranking_gap = bool(
        quadrant_result.get("eligible") and has_direction and paired_n >= 2
    )
    return {
        "scatter": False,
        "quadrants": quadrants,
        "ranking_gap": ranking_gap,
        "download": quadrants or ranking_gap,
        "any_visualization": quadrants or ranking_gap,
        "paired_countries": paired_n,
        "semantic_direction": direction,
        "quadrant_reason": (
            "insufficient_sample"
            if (
                quadrant_result.get("eligible")
                and has_direction
                and paired_n < MINIMUM_ANALYSIS_N
            )
            else str(quadrant_result.get("reason") or "ambiguous_semantic_direction")
            if not (quadrant_result.get("eligible") and has_direction)
            else ""
        ),
        "ranking_gap_reason": (
            str(quadrant_result.get("reason") or "ambiguous_semantic_direction")
            if not (quadrant_result.get("eligible") and has_direction)
            else "insufficient_sample"
            if paired_n < 2
            else ""
        ),
    }


def get_supported_combined_analyses(
    *,
    question: Any,
    answer: Any,
    rows: list[dict[str, Any]],
    semantics: dict[str, str] | None = None,
    quadrant: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backward-compatible name for integrations using the previous helper."""
    return get_combined_analysis_capabilities(
        question=question,
        answer=answer,
        rows=rows,
        semantics=semantics,
        quadrant=quadrant,
    )


def classify_quadrant(
    fra_value: Any,
    ilga_value: Any,
    *,
    fra_median: Any,
    ilga_median: Any,
    semantic_direction: str,
) -> dict[str, str] | None:
    """Classify one paired observation relative to both medians.

    Equality belongs to the ``high`` side. This makes the rule deterministic
    when several countries share the median without treating both scales as
    interchangeable.
    """
    fra = _finite_float(fra_value)
    ilga = _finite_float(ilga_value)
    fra_midpoint = _finite_float(fra_median)
    ilga_midpoint = _finite_float(ilga_median)
    if fra is None or ilga is None or fra_midpoint is None or ilga_midpoint is None:
        return None
    legal_level = "high" if ilga >= ilga_midpoint else "low"
    fra_level = "high" if fra >= fra_midpoint else "low"
    if semantic_direction == "favourable":
        experience = "favourable" if fra_level == "high" else "unfavourable"
    elif semantic_direction == "adverse":
        experience = "unfavourable" if fra_level == "high" else "favourable"
    else:
        experience = "unknown"
    return {
        "legal_level": legal_level,
        "fra_level": fra_level,
        "experience": experience,
        "quadrant": f"{legal_level}_legal_{experience if experience != 'unknown' else fra_level + '_fra'}",
    }


def quadrant_rows(
    rows: list[dict[str, Any]], semantic_direction: str
) -> list[dict[str, Any]]:
    metrics = combined_metrics(rows)
    fra_median = (metrics.get("fra") or {}).get("median")
    ilga_median = (metrics.get("ilga") or {}).get("median")
    classified: list[dict[str, Any]] = []
    for row in rows:
        classification = classify_quadrant(
            row.get("fra_value"),
            row.get("ilga_value"),
            fra_median=fra_median,
            ilga_median=ilga_median,
            semantic_direction=semantic_direction,
        )
        if classification is not None:
            classified.append({**row, **classification})
    return classified


def ranking_position_rows(
    rows: list[dict[str, Any]], semantic_direction: str
) -> dict[str, Any]:
    """Compare dense legal and social ranks without breaking numeric ties.

    Legal scores always rank from high to low. FRA ranks from high to low for
    favourable indicators and from low to high for adverse indicators.
    """
    if semantic_direction not in {"favourable", "adverse"}:
        return {
            "available": False,
            "reason": "ambiguous_semantic_direction",
            "semantic_direction": semantic_direction,
            "rows": [],
        }
    valid: list[dict[str, Any]] = []
    for row in rows:
        fra_value = _finite_float(row.get("fra_value"))
        ilga_value = _finite_float(row.get("ilga_value"))
        if fra_value is None or ilga_value is None:
            continue
        valid.append({**row, "fra_value": fra_value, "ilga_value": ilga_value})
    if len(valid) < 2:
        return {
            "available": False,
            "reason": "insufficient_sample",
            "semantic_direction": semantic_direction,
            "rows": [],
        }

    ilga_ranks = _dense_rank([row["ilga_value"] for row in valid], descending=True)
    fra_ranks = _dense_rank(
        [row["fra_value"] for row in valid],
        descending=semantic_direction == "favourable",
    )
    ranked = []
    for row in valid:
        legal_rank = ilga_ranks[row["ilga_value"]]
        social_rank = fra_ranks[row["fra_value"]]
        difference = social_rank - legal_rank
        ranked.append(
            {
                **row,
                "ilga_rank": legal_rank,
                "fra_rank": social_rank,
                "rank_difference": difference,
                "absolute_rank_difference": abs(difference),
            }
        )
    return {
        "available": True,
        "reason": "",
        "semantic_direction": semantic_direction,
        "rows": sorted(
            ranked,
            key=lambda row: (
                -int(row["absolute_rank_difference"]),
                str(row.get("country") or "").casefold(),
                str(row.get("iso") or ""),
            ),
        ),
    }


def _dense_rank(values: list[float], *, descending: bool) -> dict[float, int]:
    ordered = sorted(set(values), reverse=descending)
    return {value: position for position, value in enumerate(ordered, start=1)}


def combine_country_rows(
    fra_rows: list[dict[str, Any]], ilga_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    legal: dict[str, dict[str, Any]] = {}
    for row in ilga_rows:
        iso = normalize_country_code(row.get("iso"), row.get("country"))
        score = _finite_float(row.get("value"))
        if iso and score is not None:
            legal[iso] = row

    combined: list[dict[str, Any]] = []
    for row in fra_rows:
        iso = normalize_country_code(row.get("iso"), row.get("country"))
        fra_value = _finite_float(row.get("value"))
        match = legal.get(iso)
        ilga_value = _finite_float(match.get("value")) if match is not None else None
        if not iso or fra_value is None or ilga_value is None:
            continue
        legal_country = match.get("country") if match is not None else None
        combined.append(
            {
                "country": str(row.get("country") or legal_country or iso),
                "iso": iso,
                "fra_value": fra_value,
                "ilga_value": ilga_value,
            }
        )
    return sorted(combined, key=lambda row: (str(row["country"]), str(row["iso"])))


def descriptive_metrics(rows: list[dict[str, Any]], key: str = "value") -> dict[str, Any]:
    values = [_finite_float(row.get(key)) for row in rows]
    clean = np.asarray([value for value in values if value is not None], dtype=float)
    if clean.size == 0:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "minimum": None,
            "maximum": None,
            "std": None,
        }
    return {
        "n": int(clean.size),
        "mean": float(np.mean(clean)),
        "median": float(np.median(clean)),
        "minimum": float(np.min(clean)),
        "maximum": float(np.max(clean)),
        "std": float(np.std(clean, ddof=0)),
    }


def combined_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return _empty_combined_metrics()
    for column in ("fra_value", "ilga_value"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["fra_value", "ilga_value"]
    )
    n = len(frame)
    sample_status = "insufficient" if n < MINIMUM_ANALYSIS_N else (
        "exploratory" if n < NORMAL_ANALYSIS_N else "normal"
    )
    pearson = _correlation(frame, method="pearson") if n >= MINIMUM_ANALYSIS_N else None
    spearman = _correlation(frame, method="spearman") if n >= MINIMUM_ANALYSIS_N else None
    preferred = spearman
    strength = correlation_strength(preferred)
    slope: float | None = None
    intercept: float | None = None
    if n >= MINIMUM_ANALYSIS_N and frame["ilga_value"].nunique() >= 2:
        slope_value, intercept_value = np.polyfit(frame["ilga_value"], frame["fra_value"], 1)
        if math.isfinite(float(slope_value)) and math.isfinite(float(intercept_value)):
            slope, intercept = float(slope_value), float(intercept_value)
    return {
        "n": n,
        "sample_status": sample_status,
        "pearson": pearson,
        "spearman": spearman,
        "preferred": "spearman",
        "correlation": preferred,
        "strength": strength,
        "association_direction": (
            "positive" if preferred is not None and preferred > 0 else
            "negative" if preferred is not None and preferred < 0 else "none"
        ),
        "trend_slope": slope,
        "trend_intercept": intercept,
        "fra": descriptive_metrics(
            cast(list[dict[str, Any]], frame.to_dict("records")), "fra_value"
        ),
        "ilga": descriptive_metrics(
            cast(list[dict[str, Any]], frame.to_dict("records")), "ilga_value"
        ),
        "quadrants_available": n >= MINIMUM_ANALYSIS_N,
    }


def correlation_strength(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "unavailable"
    absolute = abs(value)
    if absolute < 0.20:
        return "very_weak"
    if absolute < 0.40:
        return "weak"
    if absolute < 0.60:
        return "moderate"
    if absolute < 0.80:
        return "strong"
    return "very_strong"


def _correlation(frame: pd.DataFrame, *, method: str) -> float | None:
    if frame["fra_value"].nunique() < 2 or frame["ilga_value"].nunique() < 2:
        return None
    first = frame["ilga_value"]
    second = frame["fra_value"]
    if method == "spearman":
        first, second = first.rank(method="average"), second.rank(method="average")
    value = first.corr(second)
    return float(value) if pd.notna(value) and math.isfinite(float(value)) else None


def _empty_combined_metrics() -> dict[str, Any]:
    return {
        "n": 0,
        "sample_status": "insufficient",
        "pearson": None,
        "spearman": None,
        "preferred": "spearman",
        "correlation": None,
        "strength": "unavailable",
        "association_direction": "none",
        "trend_slope": None,
        "trend_intercept": None,
        "fra": descriptive_metrics([]),
        "ilga": descriptive_metrics([]),
        "quadrants_available": False,
    }


def _matching_tone(value: str) -> str:
    adverse = any(term in value for term in _ADVERSE_QUESTION_TERMS)
    favourable = any(term in value for term in _FAVOURABLE_QUESTION_TERMS)
    if adverse and not favourable:
        return "adverse"
    if favourable and not adverse:
        return "favourable"
    return "unknown"


def _semantic_key(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = "".join(character for character in normalized if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", ascii_value.casefold()).strip()


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
