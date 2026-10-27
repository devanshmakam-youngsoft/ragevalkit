"""Load and validate a test case spreadsheet (xlsx or csv)."""
import hashlib
from pathlib import Path

import pandas as pd

from ragevalkit.datasets.exceptions import DatasetError


REQUIRED_COLUMNS = ["chat_id", "turn_no", "type", "question", "expected_answer"]


# Optional: kept automatically if present in the file (no extra_columns config needed).
OPTIONAL_COLUMNS = ["expected_sources"]


def compute_fingerprint(df: pd.DataFrame) -> str:
    """12-char SHA-256 fingerprint of the question set (stable across identical uploads)."""
    content = "\n".join(
        sorted(
            f"{r.chat_id}:{r.turn_no}:{r.question}:{r.expected_answer}"
            for r in df.itertuples(index=False)
        )
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


def load_dataset(
    path: Path,
    sheet: str = "dataset",
    column_map: dict[str, str] | None = None,
    extra_columns: list[str] | None = None,
) -> pd.DataFrame:
    """
    Load a dataset file into a normalised DataFrame.

    The returned DataFrame always contains REQUIRED_COLUMNS, plus any
    OPTIONAL_COLUMNS present in the file (e.g. ``expected_sources``), plus
    any columns the developer listed in ``extra_columns``.

    A fingerprint of the question set is stored in ``df.attrs["fingerprint"]``
    so the runner can detect when questions changed between versions.

    Args:
        path: Path to an .xlsx or .csv file.
        sheet: Sheet name (xlsx only). Falls back to the first sheet if not found.
        column_map: Rename columns before validation, e.g.
            ``{"user_query": "question", "gold_answer": "expected_answer"}``.
            Keys are matched case-insensitively after stripping whitespace.
        extra_columns: Additional columns to carry through (e.g. ``["difficulty", "topic"]``).
            Missing ones are silently ignored.
    """
    path = Path(path)
    try:
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path)
        else:
            with pd.ExcelFile(path, engine="openpyxl") as xl:
                name = sheet if sheet in xl.sheet_names else xl.sheet_names[0]
                df = xl.parse(name)
    except Exception as e:
        raise DatasetError(f"Could not read file: {e}") from e

    # Normalise column names
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Apply developer's column renames before required-column check
    if column_map:
        rename = {k.strip().lower(): v.strip().lower() for k, v in column_map.items()}
        df.rename(columns=rename, inplace=True)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DatasetError(
            f"Missing required column(s): {', '.join(missing)}. "
            f"Required: {', '.join(REQUIRED_COLUMNS)}. "
            f"Use column_map={{\"your_col\": \"{missing[0]}\"}} in serve() to remap."
        )

    # Build the keep list: required + optional (if present) + extras
    keep = REQUIRED_COLUMNS[:]
    for col in OPTIONAL_COLUMNS:
        if col in df.columns and col not in keep:
            keep.append(col)
    if extra_columns:
        for col in extra_columns:
            norm = col.strip().lower()
            if norm in df.columns and norm not in keep:
                keep.append(norm)

    df = df[keep].dropna(subset=["chat_id", "question"]).copy()
    if df.empty:
        raise DatasetError("The dataset has no rows with a chat_id and a question")

    df["turn_no"] = pd.to_numeric(df["turn_no"], errors="coerce").fillna(1).astype(int)
    df["chat_id"] = df["chat_id"].astype(str)
    df["type"] = df["type"].fillna("rag").astype(str)
    df["expected_answer"] = df["expected_answer"].fillna("").astype(str)
    if "expected_sources" in df.columns:
        df["expected_sources"] = df["expected_sources"].fillna("").astype(str)

    df = df.sort_values(["chat_id", "turn_no"], kind="stable").reset_index(drop=True)
    df.attrs["fingerprint"] = compute_fingerprint(df)
    return df
