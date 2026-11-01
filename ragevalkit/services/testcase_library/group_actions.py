"""Groups and the test cases that carry them."""
from ragevalkit.core.config import Config
from ragevalkit.core.exceptions.base import NotFoundError
from ragevalkit.data_access.store import EvalStore
from ragevalkit.services.spreadsheet_loader.uploads import load_uploaded_spreadsheet


def get_group(store: EvalStore, group_id: str, message: str | None = None) -> dict:
    """Return the group with ``group_id``.

    Args:
        store: The evaluation store holding the groups.
        group_id: ID of the group to find.
        message: Text of the error raised when there is no such group; defaults to ``"Group not found"``.

    Raises:
        NotFoundError: If no group has that ID.
    """
    group = next((g for g in store.list_groups() if g["group_id"] == group_id), None)
    if group is None:
        raise NotFoundError(message or "Group not found")
    return group


def import_file_into_group(cfg: Config, store: EvalStore, group_id: str, data: bytes) -> dict:
    """Add the test cases of an uploaded spreadsheet to the library and label them with an existing group.

    Args:
        cfg: Server configuration; its column mapping is used to read the file.
        store: The evaluation store to import into.
        group_id: ID of the group to label the imported test cases with.
        data: Raw bytes of the uploaded spreadsheet.

    Returns:
        A dict with the ``group_id`` and ``linked``, the number of group labels added.

    Raises:
        NotFoundError: If the group does not exist.
        DatasetError: If the file cannot be read or has no usable rows.
    """
    get_group(store, group_id, f"Group {group_id!r} not found")
    return {"group_id": group_id, "linked": store.import_into_group(group_id, load_uploaded_spreadsheet(cfg, data))}
