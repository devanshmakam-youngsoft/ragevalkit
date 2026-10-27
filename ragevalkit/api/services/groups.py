"""Groups and the test cases that carry them."""
from ragevalkit.config import Config
from ragevalkit.exceptions import NotFoundError
from ragevalkit.api.services.uploads import load_uploaded_spreadsheet
from ragevalkit.storage.store import EvalStore


def get_group(store: EvalStore, group_id: str, message: str | None = None) -> dict:
    group = next((g for g in store.list_groups() if g["group_id"] == group_id), None)
    if group is None:
        raise NotFoundError(message or "Group not found")
    return group


def import_file_into_group(cfg: Config, store: EvalStore, group_id: str, data: bytes) -> dict:
    get_group(store, group_id, f"Group {group_id!r} not found")
    return {"group_id": group_id, "linked": store.import_into_group(group_id, load_uploaded_spreadsheet(cfg, data))}
