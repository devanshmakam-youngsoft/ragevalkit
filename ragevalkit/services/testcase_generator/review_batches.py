"""Generated test cases waiting for review, and the uploads that start them."""
import json
import shutil
import tempfile
from pathlib import Path

from fastapi import UploadFile

from ragevalkit.core.config import Config
from ragevalkit.core.constants.document_reading import SUPPORTED_MESSAGE, SUPPORTED_SUFFIXES
from ragevalkit.core.constants.generator_categories import CATEGORIES
from ragevalkit.core.constants.library import TEMP_FOLDER_PREFIX
from ragevalkit.core.exceptions.base import InvalidInput, NotFoundError, TooLargeError
from ragevalkit.core.exceptions.testcase_generator import GenerationBusy
from ragevalkit.services.db_services.store import EvalStore
from ragevalkit.services.testcase_generator.manager import GenerationManager

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
    """Return the stored review batch, including its items.

    Raises:
        NotFoundError: When there is no such batch; batches are deleted once approved or discarded, and expire.
    """
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
    """Save the uploaded documents to a temporary folder and start writing test cases from them.

    Returns the new batch without its items (see ``batch_summary``); the questions are written in the background.
    The temporary folder is removed once the files have been read, or at once if starting fails.

    Args:
        cfg: The app config, for the upload limits.
        manager: The generation manager that runs the job.
        files: The uploads from the form; entries without a file name are ignored.
        per_category: How many questions to write for each category.
        categories: A JSON list of category keys, or None for all of them.
        turns: How many turns a conversation has.

    Raises:
        InvalidInput: When no document is sent, there are too many, one has an unsupported type, or the options
            are invalid.
        TooLargeError: When a document is larger than the configured limit.
        GenerationBusy: When another generation is still running.
    """
    uploads = [f for f in files if f.filename]
    if not uploads:
        raise InvalidInput("Choose at least one document")
    if len(uploads) > cfg.generate_max_files:
        raise InvalidInput(f"Upload at most {cfg.generate_max_files} documents at once")
    try:
        wanted = json.loads(categories) if categories else list(CATEGORIES)
    except ValueError as e:
        raise InvalidInput("categories must be a JSON list") from e

    workdir = Path(tempfile.mkdtemp(prefix=f"{TEMP_FOLDER_PREFIX}gen_"))
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
