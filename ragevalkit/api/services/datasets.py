"""The older dataset endpoints: a default dataset, validating a file, uploading one into the library."""
from ragevalkit.api.services.uploads import load_uploaded_spreadsheet
from ragevalkit.config import Config
from ragevalkit.datasets.exceptions import DatasetError
from ragevalkit.datasets.loader import REQUIRED_COLUMNS, load_dataset
from ragevalkit.exceptions import NotFoundError
from ragevalkit.storage.store import EvalStore


def describe_default_dataset(cfg: Config) -> dict:
    if not cfg.default_dataset:
        raise NotFoundError("No default dataset configured")
    try:
        df = load_dataset(cfg.default_dataset, cfg.dataset_sheet)
    except (DatasetError, FileNotFoundError) as e:
        raise NotFoundError(f"Default dataset unavailable: {e}") from e
    return {
        "name": cfg.default_dataset.name,
        "rows": len(df),
        "chats": int(df.chat_id.nunique()),
        "required_columns": REQUIRED_COLUMNS,
        "fingerprint": df.attrs.get("fingerprint", ""),
    }


def describe_uploaded_dataset(cfg: Config, filename: str | None, data: bytes) -> dict:
    df = load_uploaded_spreadsheet(cfg, data)
    return {
        "name": filename,
        "rows": len(df),
        "chats": int(df.chat_id.nunique()),
        "fingerprint": df.attrs.get("fingerprint", ""),
    }


def import_uploaded_dataset(cfg: Config, store: EvalStore, filename: str | None, data: bytes) -> dict:
    """Add an uploaded spreadsheet to the test case library without starting a run."""
    df = load_uploaded_spreadsheet(cfg, data)
    dataset_id = store.import_dataset(filename or "upload.xlsx", df, df.attrs.get("fingerprint", ""))
    return {"dataset_id": dataset_id, "rows": len(df)}
