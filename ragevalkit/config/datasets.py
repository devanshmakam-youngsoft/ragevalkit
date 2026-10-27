"""Spreadsheet handling for test cases."""
from pathlib import Path

from ragevalkit.config.base import Settings


class DatasetSettings(Settings):
    dataset_sheet: str = "dataset"
    default_dataset: Path | None = None

    # Map the developer's xlsx column names → internal names.
    # Example: {"user_query": "question", "gold_answer": "expected_answer"}
    column_map: dict[str, str] = {}
    # Extra xlsx columns to carry through into every result receipt.
    extra_columns: list[str] = []
