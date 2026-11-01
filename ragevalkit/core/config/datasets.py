"""Spreadsheet handling for test cases."""
from pathlib import Path

from ragevalkit.core.config.base import Settings


class DatasetSettings(Settings):
    """Options for reading test cases from a spreadsheet: sheet name, default file and column mapping."""

    dataset_sheet: str = "dataset"               # name of the sheet read from an .xlsx workbook
    default_dataset: Path | None = None          # file shown in the dashboard without an upload

    # Map the developer's xlsx column names → internal names.
    # Example: {"user_query": "question", "gold_answer": "expected_answer"}
    column_map: dict[str, str] = {}
    # Extra xlsx columns to carry through into every result receipt.
    extra_columns: list[str] = []
