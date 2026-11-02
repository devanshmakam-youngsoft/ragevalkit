"""The older dataset endpoints: a default dataset, validating a file, uploading one into the library."""
from ragevalkit.core.config import Config
from ragevalkit.core.exceptions import DatasetError, NotFoundError
from ragevalkit.services.db_services import EvalStore
from ragevalkit.services.spreadsheet_loader.loader import REQUIRED_COLUMNS, load_dataset
from ragevalkit.services.spreadsheet_loader.uploads import load_uploaded_spreadsheet


def describe_default_dataset(cfg: Config) -> dict:
    """Return a summary of the dataset configured as ``default_dataset`` in serve().

    Returns:
        A dict with ``name`` (file name), ``rows``, ``chats`` (distinct chat IDs), ``required_columns`` and the
        content ``fingerprint``.

    Raises:
        NotFoundError: If no default dataset is configured, or it cannot be read.
    """
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
    """Validate an uploaded spreadsheet and describe it, without saving it anywhere.

    Args:
        cfg: Server configuration; its column mapping and sheet name are used to read the file.
        filename: Original file name, echoed back as ``name``.
        data: Raw bytes of the uploaded file.

    Returns:
        A dict with ``name``, ``rows``, ``chats`` (distinct chat IDs) and the content ``fingerprint``.

    Raises:
        DatasetError: If the file cannot be read or has no usable rows.
    """
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
