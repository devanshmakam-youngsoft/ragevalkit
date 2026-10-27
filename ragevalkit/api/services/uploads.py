"""Reading spreadsheets that were uploaded to the API."""
import tempfile
from pathlib import Path

import pandas as pd

from ragevalkit.config import Config
from ragevalkit.datasets.loader import load_dataset


def load_spreadsheet(cfg: Config, path: Path) -> pd.DataFrame:
    """The test case spreadsheet at ``path``, read with the column mapping given to serve()."""
    return load_dataset(path, cfg.dataset_sheet, column_map=cfg.column_map or None, extra_columns=cfg.extra_columns or None)


def load_uploaded_spreadsheet(cfg: Config, data: bytes) -> pd.DataFrame:
    """A spreadsheet that arrived as bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.xlsx"
        path.write_bytes(data)
        return load_spreadsheet(cfg, path)
