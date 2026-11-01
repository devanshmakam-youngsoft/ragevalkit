"""Averages that skip missing and not-a-number values."""
import math
import statistics


def is_nan(v) -> bool:
    """Return whether ``v`` is a float NaN. Anything that is not a number (``None``, strings) gives ``False``."""
    try:
        return math.isnan(v)
    except (TypeError, ValueError):
        return False


def mean_of(values: list, nd: int = 2) -> float | None:
    """Return the mean of ``values`` rounded to ``nd`` decimals, ignoring ``None`` and NaN.

    Returns ``None`` when no usable value is left, so a missing score is not shown as 0.
    """
    vals = [v for v in values if v is not None and not is_nan(v)]
    return round(statistics.fmean(vals), nd) if vals else None


def column_of(rows: list[dict], key: str) -> list:
    """Return ``key`` from every row, with ``None`` where a row lacks it."""
    return [r.get(key) for r in rows]
