"""Writing test cases from documents: upload, watch progress, review, approve."""
from fastapi import APIRouter, Depends, File, Form, UploadFile

from ragevalkit.core.config import Config
from ragevalkit.data_access.store import EvalStore
from ragevalkit.routers.dependencies import (
    get_config,
    get_generation_manager,
    get_store,
    require_user,
)
from ragevalkit.schemas.testcase_generator.requests import Approval, ItemEdit
from ragevalkit.schemas.testcase_generator.responses import (
    ApproveResult,
    BatchCancelling,
    BatchDetail,
    BatchDiscarded,
    BatchSummary,
    GeneratedItem,
    GenerationLimits,
    ItemRemoved,
)
from ragevalkit.services.testcase_generator.manager import GenerationManager
from ragevalkit.services.testcase_generator.review_batches import (
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
    """Generated test cases waiting for review (so work survives a closed tab or a dropped connection)."""
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
    return await start_generation(cfg, manager, files, per_category, categories, turns)


@router.get("/{batch_id}")
def read_batch(batch_id: str, store: EvalStore = Depends(get_store)) -> BatchDetail:
    return get_batch(store, batch_id)


@router.patch("/{batch_id}/items/{item_id}")
def edit_item(batch_id: str, item_id: str, body: ItemEdit, manager: GenerationManager = Depends(get_generation_manager)) -> GeneratedItem:
    """Reword a generated question or its expected answer during review."""
    return manager.edit_item(batch_id, item_id, [t.model_dump() for t in body.turns])


@router.delete("/{batch_id}/items/{item_id}")
def remove_item(batch_id: str, item_id: str, manager: GenerationManager = Depends(get_generation_manager)) -> ItemRemoved:
    manager.remove_item(batch_id, item_id)
    return {"item_id": item_id, "removed": True}


@router.post("/{batch_id}/approve")
def approve(batch_id: str, body: Approval | None = None, manager: GenerationManager = Depends(get_generation_manager)) -> ApproveResult:
    """Add the reviewed items to the library, labelled by category. The batch is then deleted; anything left out goes with it."""
    return manager.approve(batch_id, body.item_ids if body else None)


@router.post("/{batch_id}/cancel", status_code=202)
def cancel(batch_id: str, store: EvalStore = Depends(get_store), manager: GenerationManager = Depends(get_generation_manager)) -> BatchCancelling:
    """Stop writing more questions; what is already written stays for review."""
    get_batch(store, batch_id)
    manager.cancel(batch_id)
    return {"batch_id": batch_id, "cancelling": True}


@router.delete("/{batch_id}")
def discard(batch_id: str, store: EvalStore = Depends(get_store), manager: GenerationManager = Depends(get_generation_manager)) -> BatchDiscarded:
    """Throw the generated test cases away."""
    return discard_batch(manager, store, batch_id)
