"""Reading single header and cell values from a table."""
import re



def normalise_header(header) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(header).strip().lower()).strip("_")


def cell_text(value) -> str:
    """A cell as clean text: empty for blanks and NaN, no stray surrounding space."""
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text
