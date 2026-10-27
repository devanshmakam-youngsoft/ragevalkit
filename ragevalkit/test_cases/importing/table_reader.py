"""Finding the data in a file or pasted text and working out which column is which."""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from ragevalkit.datasets.exceptions import DatasetError
from ragevalkit.test_cases.importing.cell_values import cell_text, normalise_header
from ragevalkit.test_cases.importing.fields import ALIASES, FIELDS, MAX_ROWS


_TEXT_SUFFIXES = {".csv", ".tsv", ".txt"}


_EXCEL_SUFFIXES = {".xlsx", ".xlsm"}


SUPPORTED_SUFFIXES = _TEXT_SUFFIXES | _EXCEL_SUFFIXES


def read_table(path: Path, sheet: str | None = None) -> tuple[pd.DataFrame, list[str], str | None]:
    """Read a spreadsheet or delimited text file with every cell as text.

    Returns ``(table, sheet_names, sheet_used)``; the last two are empty / None for text files.
    Raises DatasetError for a file that cannot be read.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise DatasetError(f"Unsupported file type '{suffix or 'unknown'}'. Use .xlsx, .csv or .tsv.")
    try:
        if suffix in _TEXT_SUFFIXES:
            sample = path.read_text(encoding="utf-8-sig", errors="replace")[:8192]
            try:
                sep = csv.Sniffer().sniff(sample, delimiters=",;	|").delimiter
            except csv.Error:
                sep = ","  # e.g. a single column of questions
            df = pd.read_csv(path, dtype=str, keep_default_na=False, sep=sep, encoding="utf-8-sig")
            sheets, used = [], None
        else:
            with pd.ExcelFile(path, engine="openpyxl") as xl:
                sheets = list(xl.sheet_names)
                used = sheet if sheet in sheets else ("dataset" if "dataset" in sheets else sheets[0])
                df = xl.parse(used, dtype=str, keep_default_na=False)
    except DatasetError:
        raise
    except Exception as e:
        raise DatasetError(f"Could not read file: {e}") from e

    df.columns = [str(c).strip() for c in df.columns]
    # drop spreadsheet filler: columns with no header and no data
    keep = [c for c in df.columns if not (c.lower().startswith("unnamed:") and not df[c].map(cell_text).any())]
    df = df[keep]
    if len(df) > MAX_ROWS:
        raise DatasetError(f"The file has {len(df):,} rows; the limit is {MAX_ROWS:,}. Split it into smaller files.")
    return df, sheets, used


def detect_mapping(columns: list[str], column_map: dict[str, str] | None = None) -> dict[str, str | None]:
    """Which file column holds each field: ``{field: column or None}``.

    Order of trust: the developer's ``serve(column_map=...)``, then well-known header names.
    """
    by_norm: dict[str, str] = {}
    for col in columns:
        by_norm.setdefault(normalise_header(col), col)
    mapping: dict[str, str | None] = {f: None for f in FIELDS}

    for source, target in (column_map or {}).items():
        field, col = str(target).strip().lower(), by_norm.get(normalise_header(source))
        if field in mapping and col and mapping[field] is None and col not in mapping.values():
            mapping[field] = col

    for field in FIELDS:
        if mapping[field] is not None:
            continue
        for alias in ALIASES[field]:
            col = by_norm.get(alias)
            if col and col not in mapping.values():
                mapping[field] = col
                break
    return mapping


def clean_mapping(columns: list[str], requested: dict | None, detected: dict[str, str | None]) -> dict[str, str | None]:
    """Apply the user's choices from the dialog on top of the detected mapping (unknown columns ignored)."""
    if not requested:
        return detected
    mapping = dict(detected)
    for field in FIELDS:
        if field in requested:
            col = requested[field]
            mapping[field] = col if col in columns else None
    return mapping
