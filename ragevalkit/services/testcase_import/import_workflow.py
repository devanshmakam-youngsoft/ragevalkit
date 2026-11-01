"""Bulk import of test cases: reading the upload, previewing it and importing it."""
import json
import tempfile
from pathlib import Path

from ragevalkit.core.config import Config
from ragevalkit.core.exceptions.base import InvalidInput, TooLargeError
from ragevalkit.data_access.store import EvalStore
from ragevalkit.services.testcase_import.fields import FIELD_LABELS, FIELDS, MAX_BYTES
from ragevalkit.services.testcase_import.row_parser import Problem, parse_rows
from ragevalkit.services.testcase_import.table_reader import (
    clean_mapping,
    detect_mapping,
    read_table,
)

PREVIEW_SAMPLE = 10          # rows shown in the preview
PREVIEW_PROBLEMS = 50        # unusable rows described in the preview
MAX_PROBLEM_ROWS = 2000      # unusable rows returned after an import, so they can be fixed and re-imported


def read_upload(cfg: Config, filename: str | None, data: bytes, sheet: str | None, mapping_json: str | None) -> tuple[list[dict], list[Problem], dict]:
    """Read the upload and work out the column mapping. Returns (rows, problems, info about the file).

    Args:
        cfg: Server configuration; ``column_map`` seeds the automatic column detection.
        filename: Original file name, used for its extension and echoed back in the info.
        data: Raw bytes of the uploaded file.
        sheet: Name of the sheet to read, or None for the default one.
        mapping_json: JSON object choosing which column holds each field, overriding the detected mapping.

    Raises:
        TooLargeError: If the file is larger than the upload limit.
        InvalidInput: If ``mapping_json`` is not valid JSON.
    """
    if len(data) > MAX_BYTES:
        raise TooLargeError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB. Split it into smaller files.")
    suffix = Path(filename or "upload.xlsx").suffix or ".xlsx"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"upload{suffix}"
        path.write_bytes(data)
        df, sheets, used = read_table(path, sheet)

    columns = list(df.columns)
    detected = detect_mapping(columns, cfg.column_map or None)
    try:
        requested = json.loads(mapping_json) if mapping_json else None
    except ValueError as e:
        raise InvalidInput("mapping must be JSON") from e
    mapping = clean_mapping(columns, requested, detected)
    rows, problems = parse_rows(df, mapping)
    info = {
        "filename": filename,
        "sheets": sheets,
        "sheet": used,
        "columns": columns,
        "mapping": mapping,
        "field_labels": FIELD_LABELS,
        "fields": list(FIELDS),
        "ignored_columns": [c for c in columns if c not in mapping.values()],
        "question_missing": mapping.get("question") is None,
        "auto_chat": mapping.get("chat_id") is None,
        "auto_turn": mapping.get("turn_no") is None,
        "total_rows": len(rows) + len(problems),
    }
    return rows, problems, info


def group_names_in(rows: list[dict]) -> list[str]:
    """Return the distinct group names used in ``rows``, sorted case-insensitively.

    Names that differ only in case count as one; the spelling seen first is kept.
    """
    seen: dict[str, str] = {}
    for row in rows:
        for name in row["groups"]:
            seen.setdefault(name.lower(), name)
    return sorted(seen.values(), key=str.lower)


def preview_import(store: EvalStore, rows: list[dict], problems: list[Problem], info: dict) -> dict:
    """What importing these rows would do (new, updated, unchanged, unusable) without saving anything."""
    result = store.import_cases(rows, dry_run=True)
    outcome_of = {o["row"]: o["outcome"] for o in result["outcomes"]}
    return {
        **info,
        "counts": {"new": result["new"], "update": result["updated"], "unchanged": result["unchanged"], "problem": len(problems)},
        "slot_conflicts": result["slot_conflicts"],
        "sample": [{**r, "outcome": outcome_of.get(r["row"])} for r in rows[:PREVIEW_SAMPLE]],
        "problems": [p.as_dict() for p in problems[:PREVIEW_PROBLEMS]],
        "group_names_in_file": group_names_in(rows),
        "new_group_names": result["groups_created"],
    }


def run_import(store: EvalStore, rows: list[dict], problems: list[Problem], info: dict, *, group_ids_json: str | None,
               new_group_name: str | None, update_by_slot: bool) -> dict:
    """Import the usable rows; the ones that cannot be used are returned so they can be fixed and re-imported.

    Args:
        store: The evaluation store to import into.
        rows: Usable rows from ``read_upload``.
        problems: Unusable rows from ``read_upload``; only reported, never imported.
        info: File information from ``read_upload``.
        group_ids_json: JSON list of existing group IDs to label every imported test case with.
        new_group_name: Name of a group to create (if needed) and label every imported test case with.
        update_by_slot: Whether a row whose chat and turn match an existing case with a different question updates
            that case instead of being added as a new one.

    Returns:
        The import counts from ``EvalStore.import_cases``, plus ``problems`` (how many rows were unusable),
        ``problem_rows`` (up to ``MAX_PROBLEM_ROWS`` of them) and the file's ``columns``.

    Raises:
        InvalidInput: If no question column was found.
    """
    if info["question_missing"]:
        raise InvalidInput("No question column found. Choose which column holds the questions.")
    try:
        ids = json.loads(group_ids_json) if group_ids_json else []
    except ValueError as e:
        raise InvalidInput("group_ids must be a JSON list") from e
    result = store.import_cases(rows, group_ids=[str(i) for i in ids], new_group_name=new_group_name or None, update_by_slot=update_by_slot)
    result.pop("outcomes")
    return {
        **result,
        "problems": len(problems),
        "problem_rows": [p.as_dict() for p in problems[:MAX_PROBLEM_ROWS]],
        "columns": info["columns"],
    }
