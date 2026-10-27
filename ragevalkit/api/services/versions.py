"""Finished runs ("versions") as the dashboard reads them."""
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


def export_version(store: EvalStore, version: str) -> bytes:
    """The version's results as an Excel workbook."""
    if not valid_version(version) or not store.exists(version):
        raise NotFoundError("Version not found")
    return store.export_xlsx(version)
