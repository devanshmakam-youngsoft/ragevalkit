"""Writing test cases from documents: upload, watch progress, review, approve."""
import json
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from ragevalkit.documents.constants import SUPPORTED_MESSAGE, SUPPORTED_SUFFIXES
from ragevalkit.generator import CATEGORIES, GenerationBusy
from ragevalkit.routes.deps import require_user

router = APIRouter(prefix="/api/generate", dependencies=[Depends(require_user)])


def _summary(batch: dict) -> dict:
    """A batch without its (bulky) items: what the 'waiting for review' banner needs."""
    items = batch.get("items", [])
    return {
        **{k: v for k, v in batch.items() if k != "items"},
        "item_count": len(items),
        "case_count": sum(len(i["turns"]) for i in items),
        "by_category": {c: sum(1 for i in items if i["category"] == c) for c in CATEGORIES},
    }


def _batch(request: Request, batch_id: str) -> dict:
    batch = request.app.state.store.get_batch(batch_id)
    if batch is None:
        raise HTTPException(404, "These generated test cases are no longer available (they expire if not approved in time)")
    return batch


@router.get("/limits")
def limits(request: Request) -> dict:
    """What the dialog needs to state up front: file limits, the categories, which model gets the text."""
    return request.app.state.generator.limits()


@router.get("")
def list_batches(request: Request) -> list[dict]:
    """Generated test cases waiting for review (so work survives a closed tab or a dropped connection)."""
    return [_summary(b) for b in request.app.state.store.list_batches()]


@router.post("", status_code=202)
async def start_generation(
    request: Request,
    files: list[UploadFile] = File(...),
    per_category: int = Form(3),
    categories: str | None = Form(None),   # JSON array; default: all four
    turns: int = Form(3),
) -> dict:
    cfg, manager = request.app.state.config, request.app.state.generator
    uploads = [f for f in files if f.filename]
    if not uploads:
        raise HTTPException(422, "Choose at least one document")
    if len(uploads) > cfg.generate_max_files:
        raise HTTPException(422, f"Upload at most {cfg.generate_max_files} documents at once")
    limit = cfg.generate_max_file_mb * 1024 * 1024
    try:
        wanted = json.loads(categories) if categories else list(CATEGORIES)
    except ValueError:
        raise HTTPException(422, "categories must be a JSON list")

    workdir = Path(tempfile.mkdtemp(prefix="ragevalkit_gen_"))
    saved: list[tuple[str, Path]] = []
    try:
        for index, upload in enumerate(uploads):
            name = Path(upload.filename).name
            suffix = Path(name).suffix.lower()
            if suffix not in SUPPORTED_SUFFIXES:
                raise HTTPException(422, f"{name}: unsupported file type. {SUPPORTED_MESSAGE}")
            dest = workdir / f"{index}{suffix}"
            size = 0
            with dest.open("wb") as out:
                while block := await upload.read(1024 * 1024):
                    size += len(block)
                    if size > limit:
                        raise HTTPException(413, f"{name} is larger than {cfg.generate_max_file_mb} MB")
                    out.write(block)
            saved.append((name, dest))
        batch = manager.start(saved, workdir, per_category=per_category, categories=wanted, turns=turns)
    except GenerationBusy as e:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(409, str(e))
    except ValueError as e:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(422, str(e))
    except BaseException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    return _summary(batch)


@router.get("/{batch_id}")
def get_batch(batch_id: str, request: Request) -> dict:
    return _batch(request, batch_id)


class TurnText(BaseModel):
    question: str
    expected_answer: str


class ItemEdit(BaseModel):
    turns: list[TurnText]


@router.patch("/{batch_id}/items/{item_id}")
def edit_item(batch_id: str, item_id: str, body: ItemEdit, request: Request) -> dict:
    """Reword a generated question or its expected answer during review."""
    try:
        return request.app.state.generator.edit_item(batch_id, item_id, [t.model_dump() for t in body.turns])
    except KeyError:
        raise HTTPException(404, "Item not found")
    except GenerationBusy as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/{batch_id}/items/{item_id}")
def remove_item(batch_id: str, item_id: str, request: Request) -> dict:
    try:
        request.app.state.generator.remove_item(batch_id, item_id)
    except KeyError:
        raise HTTPException(404, "Item not found")
    except GenerationBusy as e:
        raise HTTPException(409, str(e))
    return {"item_id": item_id, "removed": True}


class Approval(BaseModel):
    item_ids: list[str] | None = None   # default: everything left in the batch


@router.post("/{batch_id}/approve")
def approve(batch_id: str, request: Request, body: Approval | None = None) -> dict:
    """Add the reviewed items to the library, labelled by category. The batch is then deleted; anything left out goes with it."""
    try:
        return request.app.state.generator.approve(batch_id, body.item_ids if body else None)
    except KeyError:
        raise HTTPException(404, "These generated test cases are no longer available")
    except GenerationBusy as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/{batch_id}/cancel", status_code=202)
def cancel(batch_id: str, request: Request) -> dict:
    """Stop writing more questions; what is already written stays for review."""
    _batch(request, batch_id)
    request.app.state.generator.cancel(batch_id)
    return {"batch_id": batch_id, "cancelling": True}


@router.delete("/{batch_id}")
def discard(batch_id: str, request: Request) -> dict:
    """Throw the generated test cases away."""
    manager, store = request.app.state.generator, request.app.state.store
    batch = _batch(request, batch_id)
    if batch["status"] == "running":
        manager.cancel(batch_id)
        raise HTTPException(409, "Still writing; it was asked to stop. Discard again in a moment.")
    store.delete_batch(batch_id)
    return {"batch_id": batch_id, "discarded": True}
