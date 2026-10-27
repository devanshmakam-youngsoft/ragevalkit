"""How much of a step is kept: displayed values and the material the judge reads."""
import json


LIMITS = {"value": 1000, "material": 20000}


def configure(max_step_value_chars: int | None = None, max_material_chars: int | None = None) -> None:
    """Set how much is kept: shown step inputs/outputs/notes, and the material the judge reads."""
    if max_step_value_chars:
        LIMITS["value"] = int(max_step_value_chars)
    if max_material_chars:
        LIMITS["material"] = int(max_material_chars)


def _clip(text: str, limit: int) -> str:
    """The text, or its first ``limit`` characters followed by a marker saying how much was left out."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\u2026 (+{len(text) - limit} more characters)"


def clip_material(text: str) -> str:
    return _clip(text, LIMITS["material"])


def _is_number_list(v) -> bool:
    return (isinstance(v, (list, tuple)) and len(v) >= 32
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v))


def text_of(v) -> str:
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, default=str, ensure_ascii=False)
    except Exception:
        return str(v)


def display_text(v, max_len: int | None = None) -> str:
    """Stringify any value for storage: cut to the display limit (with a marker), and a long list of numbers
    (an embedding vector, say) is summarised instead of printed."""
    if _is_number_list(v):
        return f"[{len(v)} numbers]"
    return _clip(text_of(v), max_len or LIMITS["value"])
