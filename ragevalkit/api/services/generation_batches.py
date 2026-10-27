"""Generated test cases waiting for review, and the uploads that start them."""
import json
import shutil
import tempfile
from pathlib import Path

from fastapi import UploadFile

from ragevalkit.config import Config
from ragevalkit.documents.constants import SUPPORTED_MESSAGE, SUPPORTED_SUFFIXES
from ragevalkit.exceptions import InvalidInput, NotFoundError, TooLargeError
from ragevalkit.generation.categories import CATEGORIES
from ragevalkit.generation.exceptions import GenerationBusy
from ragevalkit.generation.manager import GenerationManager
from ragevalkit.storage.store import EvalStore

UPLOAD_READ_BYTES = 1024 * 1024


def batch_summary(batch: dict) -> dict:
    """A batch without its (bulky) items: what the 'waiting for review' banner needs."""
    items = batch.get("items", [])
    return {
        **{k: v for k, v in batch.items() if k != "items"},
        "item_count": len(items),
        "case_count": sum(len(i["turns"]) for i in items),
        "by_category": {c: sum(1 for i in items if i["category"] == c) for c in CATEGORIES},
    }


def get_batch(store: EvalStore, batch_id: str) -> dict:
    batch = store.get_batch(batch_id)
    if batch is None:
        raise NotFoundError("These generated test cases are no longer available (they expire if not approved in time)")
    return batch


async def _save_uploads(cfg: Config, uploads: list[UploadFile], workdir: Path) -> list[tuple[str, Path]]:
    limit = cfg.generate_max_file_mb * 1024 * 1024
    saved: list[tuple[str, Path]] = []
    for index, upload in enumerate(uploads):
        name = Path(upload.filename).name
        suffix = Path(name).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise InvalidInput(f"{name}: unsupported file type. {SUPPORTED_MESSAGE}")
        dest = workdir / f"{index}{suffix}"
        size = 0
        with dest.open("wb") as out:
            while block := await upload.read(UPLOAD_READ_BYTES):
                size += len(block)
                if size > limit:
                    raise TooLargeError(f"{name} is larger than {cfg.generate_max_file_mb} MB")
                out.write(block)
        saved.append((name, dest))
    return saved


async def start_generation(cfg: Config, manager: GenerationManager, files: list[UploadFile], per_category: int, categories: str | None, turns: int) -> dict:
    uploads = [f for f in files if f.filename]
    if not uploads:
        raise InvalidInput("Choose at least one document")
    if len(uploads) > cfg.generate_max_files:
        raise InvalidInput(f"Upload at most {cfg.generate_max_files} documents at once")
    try:
        wanted = json.loads(categories) if categories else list(CATEGORIES)
    except ValueError as e:
        raise InvalidInput("categories must be a JSON list") from e

    workdir = Path(tempfile.mkdtemp(prefix="ragevalkit_gen_"))
    try:
        saved = await _save_uploads(cfg, uploads, workdir)
        batch = manager.start(saved, workdir, per_category=per_category, categories=wanted, turns=turns)
    except BaseException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    return batch_summary(batch)


def discard_batch(manager: GenerationManager, store: EvalStore, batch_id: str) -> dict:
    """Throw the generated test cases away (a batch still being written is asked to stop first)."""
    batch = get_batch(store, batch_id)
    if batch["status"] == "running":
        manager.cancel(batch_id)
        raise GenerationBusy("Still writing; it was asked to stop. Discard again in a moment.")
    store.delete_batch(batch_id)
    return {"batch_id": batch_id, "discarded": True}
