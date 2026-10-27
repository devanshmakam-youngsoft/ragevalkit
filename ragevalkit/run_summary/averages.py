"""Averages that skip missing and not-a-number values."""
import math
import statistics


def is_nan(v) -> bool:
    try:
        return math.isnan(v)
    except (TypeError, ValueError):
        return False


def mean_of(values: list, nd: int = 2) -> float | None:
    vals = [v for v in values if v is not None and not is_nan(v)]
    return round(statistics.fmean(vals), nd) if vals else None


def column_of(rows: list[dict], key: str) -> list:
    return [r.get(key) for r in rows]
