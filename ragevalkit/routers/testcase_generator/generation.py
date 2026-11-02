"""Writing test cases from documents: upload, watch progress, review, approve."""
from fastapi import APIRouter, Depends, File, Form, UploadFile

from ragevalkit.core.config import Config
from ragevalkit.routers.dependencies import (
    get_config,
    get_generation_manager,
    get_store,
    require_user,
)
from ragevalkit.schemas.testcase_generator import (
    Approval,
    ApproveResult,
    BatchCancelling,
    BatchDetail,
    BatchDiscarded,
    BatchSummary,
    GeneratedItem,
    GenerationLimits,
    ItemEdit,
    ItemRemoved,
)
from ragevalkit.services.db_services import EvalStore
from ragevalkit.services.testcases.testcase_generator import (
    GenerationManager,
    batch_summary,
    discard_batch,
    get_batch,
    start_generation,
)

router = APIRouter(prefix="/api/generate", tags=["generate"], dependencies=[Depends(require_user)])


@router.get("/limits")
def limits(manager: GenerationManager = Depends(get_generation_manager)) -> GenerationLimits:
    """What the dialog needs to state up front: file limits, the categories, which model gets the text."""
    return manager.limits()


@router.get("")
def list_batches(store: EvalStore = Depends(get_store)) -> list[BatchSummary]:
    """Generated test cases waiting for review (so work survives a closed tab or a dropped connection).

    Newest first, each without its items; open one with ``GET /api/generate/{batch_id}``. A batch nobody
    approves is removed once it expires (see ``ttl_hours`` in ``GET /api/generate/limits``).
    """
    return [batch_summary(b) for b in store.list_batches()]


@router.post("", status_code=202)
async def start_generation_batch(
    files: list[UploadFile] = File(...),
    per_category: int = Form(3),
    categories: str | None = Form(None),   # JSON array; default: all four
    turns: int = Form(3),
    cfg: Config = Depends(get_config),
    manager: GenerationManager = Depends(get_generation_manager),
) -> BatchSummary:
    """Upload documents and start writing test cases from them in the background (answers 202).

    The questions are written by the configured model and wait in a review batch; nothing reaches the library
    until the batch is approved. Only one generation can be going at a time. The accepted file types and the
    limits are given by ``GET /api/generate/limits``.

    Args:
        files: The documents to write questions from.
        per_category: How many questions to write in each category.
        categories: JSON array with any of ``direct``, ``indirect``, ``multipart`` and ``multiturn``.
            Defaults to all four.
        turns: How many turns a multi-turn conversation has (2 to 4).

    Returns:
        The new batch, with status ``running``. Follow it with ``GET /api/generate/{batch_id}``.

    Error answers:
        409 when another generation is running; 413 when a file is over the size limit;
        422 for no file, too many files, an unsupported file type, a bad ``categories`` list, or
        ``per_category`` or ``turns`` out of range. A document that cannot be read is reported later, on the batch.
    """
    return await start_generation(cfg, manager, files, per_category, categories, turns)


@router.get("/{batch_id}")
def read_batch(batch_id: str, store: EvalStore = Depends(get_store)) -> BatchDetail:
    """Read a review batch with every generated item, to watch its progress or to review it.

    ``status`` is ``running`` while questions are being written, then ``ready``, ``failed``, ``cancelled``
    or ``interrupted`` (the server restarted). Answers 404 when the batch is unknown or has expired.
    """
    return get_batch(store, batch_id)


@router.patch("/{batch_id}/items/{item_id}")
def edit_item(batch_id: str, item_id: str, body: ItemEdit, manager: GenerationManager = Depends(get_generation_manager)) -> GeneratedItem:
    """Reword a generated question or its expected answer during review.

    ``turns`` must hold one entry per turn the item already has, in order; the number of turns cannot change.
    Answers 404 for an unknown batch or item, 409 while the batch is still being written, and 422 when the
    number of turns differs or a text is outside the length limits (question 12 to 400 characters, expected
    answer 3 to 1200).
    """
    return manager.edit_item(batch_id, item_id, [t.model_dump() for t in body.turns])


@router.delete("/{batch_id}/items/{item_id}")
def remove_item(batch_id: str, item_id: str, manager: GenerationManager = Depends(get_generation_manager)) -> ItemRemoved:
    """Drop one generated item from a batch during review, so it is not added when the batch is approved.

    Answers 404 for an unknown batch or item and 409 while the batch is still being written.
    """
    manager.remove_item(batch_id, item_id)
    return {"item_id": item_id, "removed": True}


@router.post("/{batch_id}/approve")
def approve(batch_id: str, body: Approval | None = None, manager: GenerationManager = Depends(get_generation_manager)) -> ApproveResult:
    """Add the reviewed items to the library, labelled by category.

    The batch is then deleted; anything left out goes with it. The optional body names the items to add
    (``item_ids``); without it every item left in the batch is added.
    Each item becomes a chat of test cases (one per turn) in the group of its category, created if needed.
    Answers 404 for an unknown batch, 409 while the batch is still being written, and 422 when there is
    nothing to approve.
    """
    return manager.approve(batch_id, body.item_ids if body else None)


@router.post("/{batch_id}/cancel", status_code=202)
def cancel(batch_id: str, store: EvalStore = Depends(get_store), manager: GenerationManager = Depends(get_generation_manager)) -> BatchCancelling:
    """Stop writing more questions; what is already written stays for review.

    Answers 202 once the request is noted (the batch may need a moment to finish its current question)
    and 404 for an unknown batch.
    """
    get_batch(store, batch_id)
    manager.cancel(batch_id)
    return {"batch_id": batch_id, "cancelling": True}


@router.delete("/{batch_id}")
def discard(batch_id: str, store: EvalStore = Depends(get_store), manager: GenerationManager = Depends(get_generation_manager)) -> BatchDiscarded:
    """Throw the generated test cases away.

    A batch that is still being written is asked to stop and answers 409; discard it again a moment later.
    Answers 404 for an unknown batch.
    """
    return discard_batch(manager, store, batch_id)
