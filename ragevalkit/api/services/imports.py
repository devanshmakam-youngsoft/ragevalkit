"""Bulk import of test cases: reading the upload, previewing it and importing it."""
import json
import tempfile
from pathlib import Path

from ragevalkit.config import Config
from ragevalkit.exceptions import InvalidInput, TooLargeError
from ragevalkit.storage.store import EvalStore
from ragevalkit.test_cases.importing.fields import FIELD_LABELS, FIELDS, MAX_BYTES
from ragevalkit.test_cases.importing.row_parser import Problem, parse_rows
from ragevalkit.test_cases.importing.table_reader import clean_mapping, detect_mapping, read_table

PREVIEW_SAMPLE = 10          # rows shown in the preview
PREVIEW_PROBLEMS = 50        # unusable rows described in the preview
MAX_PROBLEM_ROWS = 2000      # unusable rows returned after an import, so they can be fixed and re-imported


def read_upload(cfg: Config, filename: str | None, data: bytes, sheet: str | None, mapping_json: str | None) -> tuple[list[dict], list[Problem], dict]:
    """Read the upload and work out the column mapping. Returns (rows, problems, info about the file)."""
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
    """Import the usable rows; the ones that cannot be used are returned so they can be fixed and re-imported."""
    if info["question_missing"]:
        raise InvalidInput("No question column found. Choose which column holds the questions.")
    ids = json.loads(group_ids_json) if group_ids_json else []
    result = store.import_cases(rows, group_ids=[str(i) for i in ids], new_group_name=new_group_name or None, update_by_slot=update_by_slot)
    result.pop("outcomes")
    return {
        **result,
        "problems": len(problems),
        "problem_rows": [p.as_dict() for p in problems[:MAX_PROBLEM_ROWS]],
        "columns": info["columns"],
    }
