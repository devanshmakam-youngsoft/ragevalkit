"""Finished runs ("versions") as the dashboard reads them."""
from pathlib import Path

from ragevalkit.config import Config
from ragevalkit.exceptions import NotFoundError
from ragevalkit.storage.store import EvalStore
from ragevalkit.storage.version_names import valid_version


def get_version_with_deleted_flags(store: EvalStore, version: str) -> dict:
    """A version's summary and rows; a row whose test case has been deleted since is marked ``case_deleted``."""
    data = store.get(version)
    alive = store.existing_tc_ids()
    for row in data.get("rows", []):
        if row.get("tc_id") and row["tc_id"] not in alive:
            row["case_deleted"] = True
    return data


def read_version_log(cfg: Config, store: EvalStore, version: str) -> bytes:
    """The text of the log file written while this version ran."""
    if not valid_version(version) or not store.exists(version):
        raise NotFoundError("Version not found")
    name = store.get(version).get("summary", {}).get("log_file")
    path = cfg.logs_dir / "runs" / Path(name).name if name else None      # a bare file name: never a path from outside
    if path is None or not path.is_file():
        raise NotFoundError("The log file for this version is no longer available")
    return path.read_bytes()


def export_version(store: EvalStore, version: str) -> bytes:
    """The version's results as an Excel workbook."""
    if not valid_version(version) or not store.exists(version):
        raise NotFoundError("Version not found")
    return store.export_xlsx(version)
