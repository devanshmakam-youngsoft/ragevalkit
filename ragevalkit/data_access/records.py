"""Small helpers for ids and values the repositories share."""
import math
import uuid


def new_group_id() -> str:
    return "grp_" + uuid.uuid4().hex[:8]


def dataset_id_for(fingerprint: str) -> str:
    return "ds_" + fingerprint[:8]


def clean_expected_sources(val) -> str:
    """Convert a potential NaN/None expected_sources value to clean empty string."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s
