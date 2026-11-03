"""Short tags that say why an answer or its context got its mark: clean what the judge returned, fill in when it gave none,
and describe them for the dashboard and the Excel report."""
from collections.abc import Iterable

from ragevalkit.prompts.answer_judge import ANSWER_TAGS, MATERIAL_TAGS, MAX_TAGS_PER_SCORE


def _clean(values: object, vocabulary: dict) -> list[str]:
    """The known tags in ``values``, once each, in order, at most ``MAX_TAGS_PER_SCORE``. Anything else is dropped."""
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Iterable):
        return []
    kept: list[str] = []
    for value in values:
        key = str(value).strip().lower().replace(" ", "_").replace("-", "_")
        if key in vocabulary and key not in kept:
            kept.append(key)
    return kept[:MAX_TAGS_PER_SCORE]


def clean_answer_tags(values: object) -> list[str]:
    """The valid answer tags among whatever the judge (or a custom ``judge_fn``) returned."""
    return _clean(values, ANSWER_TAGS)


def clean_material_tags(values: object) -> list[str]:
    """The valid context tags among whatever the judge (or a custom ``judge_fn``) returned."""
    return _clean(values, MATERIAL_TAGS)


def _answer_tag_from_marks(marks: int | None, status: str | None, has_answer: bool) -> list[str]:
    if marks is None:
        return []
    if marks >= 10:
        return ["correct"]
    if marks >= 7:
        return ["minor_gaps"]
    if marks >= 4:
        return ["partly_correct"]
    if marks >= 1:
        return ["wrong"]
    return ["no_answer"] if status not in (None, "ok") or not has_answer else ["wrong"]


def _material_tag_from_marks(marks: int | None, has_material: bool) -> list[str]:
    if marks is None:
        return []
    if marks >= 9:
        return ["complete"]
    if marks >= 5:
        return ["partial"]
    if marks >= 1:
        return ["key_missing"]
    return ["key_missing"] if has_material else ["empty"]


def _describe(keys: list[str], vocabulary: dict) -> list[dict]:
    return [{"key": key, "label": vocabulary[key][0], "tone": vocabulary[key][1]} for key in keys]


def tag_keys(row: dict) -> tuple[list[str], list[str]]:
    """The answer and context tags of one saved row: the judge's own when it gave any, else a tag from the mark."""
    has_answer = bool((row.get("generated_answer") or "").strip())
    answer = clean_answer_tags(row.get("answer_tags")) or _answer_tag_from_marks(row.get("answer_marks"), row.get("status"), has_answer)
    material = clean_material_tags(row.get("material_tags")) or _material_tag_from_marks(
        row.get("material_marks"), bool((row.get("material") or "").strip()))
    return answer, material


def add_remark_tags(row: dict) -> dict:
    """A copy of ``row`` whose ``answer_tags`` and ``material_tags`` are lists of ``{key, label, tone}`` for the dashboard."""
    answer, material = tag_keys(row)
    return {**row, "answer_tags": _describe(answer, ANSWER_TAGS), "material_tags": _describe(material, MATERIAL_TAGS)}


def remark_summary(row: dict) -> str:
    """The tags of one row as one line of plain text, for the Excel report: ``Answer: Wrong answer | Context: Key text missing``."""
    answer, material = tag_keys(row)
    parts = []
    if answer:
        parts.append("Answer: " + ", ".join(ANSWER_TAGS[k][0] for k in answer))
    if material:
        parts.append("Context: " + ", ".join(MATERIAL_TAGS[k][0] for k in material))
    return " | ".join(parts)
