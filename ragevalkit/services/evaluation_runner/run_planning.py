"""Deciding what a run executes, from what the dashboard sent."""
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ragevalkit.core.config import Config
from ragevalkit.core.exceptions.base import InvalidInput, NotFoundError
from ragevalkit.core.exceptions.db_services import ConflictError
from ragevalkit.core.exceptions.evaluation_runner import NoDatasetError
from ragevalkit.schemas.internal.run_selection import RunSelection
from ragevalkit.services.db_services.store import EvalStore
from ragevalkit.services.spreadsheet_loader.uploads import (
    load_spreadsheet,
    load_uploaded_spreadsheet,
)
from ragevalkit.utils.version_names import valid_version


@dataclass
class RunPlan:
    """The test cases a run will execute, and how to label the run."""

    df: pd.DataFrame
    dataset_name: str
    group_names: list[str]
    from_library: bool
    source_dataset_id: str


def parse_id_list(raw: str | None) -> list[str]:
    """A list of ids sent as a JSON array (or, leniently, comma-separated) in a form field."""
    if not raw:
        return []
    try:
        val = json.loads(raw)
        if isinstance(val, list):
            return [str(v) for v in val]
    except ValueError:
        pass
    return [part.strip() for part in raw.split(",") if part.strip()]


def check_version_name(version: str) -> str:
    """Return the version name without surrounding whitespace.

    Raises:
        InvalidInput: When the stripped name is empty, longer than 20 characters, or has characters other than
            letters, digits, ``.``, ``_`` or ``-``.
    """
    version =version.strip()
    if not valid_version(version):
        raise InvalidInput("Version may only contain letters, digits, '.', '_' or '-' (max 20 chars)")
    return version


def collision_message(collisions: list[dict]) -> str:
    """Return the error text for test cases that share a chat id and turn number; names only the first collision."""
    first =collisions[0]
    more = f" (and {len(collisions) - 1} more)" if len(collisions) > 1 else ""
    return (
        f"Chat {first['chat_id']!r} turn {first['turn_no']} is used by {len(first['tc_ids'])} different "
        f"test cases in this selection{more}. Deselect one or change its chat / turn number."
    )


def selection_preview(selection: RunSelection) -> dict:
    """What a run with this selection would execute (the live count in the Execute dialog)."""
    return {
        "selected": selection.selected,
        "context": selection.context,
        "total": selection.total,
        "missing": selection.missing,
        "group_names": selection.group_names,
        "collisions": selection.collisions,
    }


def _plan_from_library(store: EvalStore, groups: list[str], picked: list[str], status: str, include_context: bool) -> RunPlan:
    selection = store.resolve_selection(groups, picked, status=status, include_context=include_context)
    if selection.collisions:
        raise ConflictError(collision_message(selection.collisions))
    if selection.df.empty:
        raise NotFoundError("No runnable test cases in the selection")
    label = list(selection.group_names)
    if picked:
        label.append(f"{len(picked)} picked test case{'s' if len(picked) != 1 else ''}")
    return RunPlan(
        df=selection.df, dataset_name=" + ".join(label), group_names=selection.group_names, from_library=True,
        source_dataset_id=groups[0] if len(groups) == 1 and not picked else "",
    )


def _plan_from_upload_as_group(cfg: Config, store: EvalStore, data: bytes, group_name: str, status: str) -> RunPlan:
    df = load_uploaded_spreadsheet(cfg, data)
    group_id = store.create_group(group_name)
    store.import_into_group(group_id, df)
    selection = store.resolve_selection([group_id], [], status=status, include_context=False)
    return RunPlan(df=selection.df, dataset_name=group_name, group_names=[group_name], from_library=True, source_dataset_id=group_id)


def _plan_from_file(cfg: Config, path: Path, name: str) -> RunPlan:
    try:
        df = load_spreadsheet(cfg, path)
    except FileNotFoundError as e:
        raise NotFoundError("Dataset file not found") from e
    return RunPlan(df=df, dataset_name=name, group_names=[], from_library=False, source_dataset_id="")


def plan_run(
    cfg: Config, store: EvalStore, *, version: str, group_ids: list[str], picked: list[str], status: str, include_context: bool,
    upload_name: str | None, upload_data: bytes | None, save_as_group: bool, group_name: str | None,
) -> RunPlan:
    """The test cases to run, from the first source that applies: a library selection (groups and/or picked
    cases), an uploaded file saved as a group, an uploaded file used once, or the configured default dataset.

    An upload that is not saved as a group is written to ``cfg.uploads_dir``; one saved as a group creates that
    group in the store as a side effect.

    Args:
        version: The version name of the run; names the stored copy of an upload used once.
        group_ids: Library groups to run (every case in them that matches ``status``).
        picked: Ids of individual library test cases to run, whatever their ``status``.
        status: Which cases of the groups to take: ``active``, ``inactive`` or ``all``.
        include_context: Whether to add the earlier turns of a conversation that a selected turn needs.
        upload_name: File name of an uploaded spreadsheet, if one was sent.
        upload_data: Raw bytes of the uploaded spreadsheet.
        save_as_group: Whether to import the upload into the library as a new group instead of using it once.
        group_name: Name for that new group; the upload is only saved when this is also set.

    Raises:
        NoDatasetError: When nothing was selected or uploaded and no default dataset is configured.
        NotFoundError: When the selection has no runnable cases, or the dataset file is missing.
        ConflictError: When two selected cases share a chat id and turn number.
    """
    if group_ids or picked:
        return _plan_from_library(store, group_ids, picked, status, include_context)
    if upload_name and upload_data is not None and save_as_group and group_name:
        return _plan_from_upload_as_group(cfg, store, upload_data, group_name, status)
    if upload_name and upload_data is not None:
        cfg.uploads_dir.mkdir(parents=True, exist_ok=True)
        path = cfg.uploads_dir / f"version_{version}_input.xlsx"
        path.write_bytes(upload_data)
        return _plan_from_file(cfg, path, upload_name)
    if cfg.default_dataset:
        return _plan_from_file(cfg, cfg.default_dataset, cfg.default_dataset.name)
    raise NoDatasetError("No dataset provided and no default_dataset configured")
