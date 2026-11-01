"""Small helpers for ids and values stored records share."""
import math
import uuid


def new_group_id() -> str:
    """Return a new random test case group ID such as ``grp_1a2b3c4d``."""
    return "grp_" + uuid.uuid4().hex[:8]


def clean_expected_sources(val) -> str:
    """Convert a potential NaN/None expected_sources value to clean empty string."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s
