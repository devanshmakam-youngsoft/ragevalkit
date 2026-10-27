"""The background job that writes questions, and the review that turns them into test cases.

A *review batch* (stored in ``store.batches``) looks like::

    {batch_id, status: running|ready|failed|cancelled|interrupted, created_at, expires_at,
     options: {per_category, categories, turns}, model, files: [{name, pages, passages, error}],
     total_tasks, done_tasks, errors: [{category, file, reason}], error,
     items: [{item_id, category, file, number,
              turns: [{question, expected_answer, evidence: [{quote, file, page, passage}], needs_context}]}]}

It is saved after every item, so nothing is lost if the browser goes away; it only becomes test cases when approved.
"""
from __future__ import annotations

import logging
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from ragevalkit.docs import SUPPORTED_SUFFIXES, ReadDocument, read_document
from ragevalkit.documents.exceptions import DocumentError
from ragevalkit.generation.exceptions import GenerationBusy
from ragevalkit.generator.categories import (
    CASE_TYPE, CATEGORIES, CATEGORY_LABELS, DEFAULT_PER_CATEGORY, DEFAULT_TURNS, MAX_TURNS, MIN_TURNS,
)
from ragevalkit.generator.checks import check_text
from ragevalkit.generator.llm import LiteLLM
from ragevalkit.generator.planning import Task, plan_tasks
from ragevalkit.generator.writer import generate_item

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GenerationManager:
    """Starts generation jobs and turns approved review batches into test cases."""

    def __init__(self, config, store, llm: Callable | None = None, sleep: Callable | None = None):
        self.config = config
        self.store = store
        self._llm = llm or LiteLLM(config)
        self._sleep = sleep or time.sleep
        self._lock = threading.Lock()
        self._active: str | None = None
        self._cancelled: set[str] = set()
        self.store.interrupt_running_batches()  # a restart cannot resume a job, but what it saved stays reviewable

    @property
    def model(self) -> str:
        return getattr(self._llm, "model", None) or self.config.generator_model or self.config.judge_model

    def limits(self) -> dict:
        """What the dialog states up front: limits, the categories, and which model receives the text."""
        return {
            "max_files": self.config.generate_max_files,
            "max_file_mb": self.config.generate_max_file_mb,
            "per_category_max": self.config.generate_per_category_max,
            "per_category_default": DEFAULT_PER_CATEGORY,
            "turns_default": DEFAULT_TURNS,
            "categories": [{"key": k, "label": v} for k, v in CATEGORY_LABELS.items()],
            "model": self.model,
            "ttl_hours": self.config.batch_ttl_hours,
            "formats": [s.lstrip(".") for s in SUPPORTED_SUFFIXES if s != ".markdown"],
        }

    # ---- writing ------------------------------------------------------------------------------

    def start(self, files: list[tuple[str, Path]], workdir: Path | None, *, per_category: int, categories: list[str], turns: int) -> dict:
        """Create a review batch and start writing into it. ``files`` are (name, path) pairs; ``workdir`` is deleted once read."""
        categories = [c for c in CATEGORIES if c in categories]
        if not categories:
            raise ValueError("Choose at least one category")
        if not 1 <= per_category <= self.config.generate_per_category_max:
            raise ValueError(f"Questions per category must be between 1 and {self.config.generate_per_category_max}")
        if not MIN_TURNS <= turns <= MAX_TURNS:
            raise ValueError(f"A conversation needs between {MIN_TURNS} and {MAX_TURNS} turns")
        with self._lock:
            if self._active:
                raise GenerationBusy("Another generation is already running")
            batch_id = uuid.uuid4().hex[:12]
            created = _now()
            batch = {
                "batch_id": batch_id, "status": "running", "created_at": created.isoformat(),
                "expires_at": (created + timedelta(hours=self.config.batch_ttl_hours)).isoformat(),
                "options": {"per_category": per_category, "categories": categories, "turns": turns},
                "model": self.model, "files": [{"name": n} for n, _ in files],
                "total_tasks": 0, "done_tasks": 0, "items": [], "errors": [], "error": "",
            }
            self.store.save_batch(batch)
            self._active = batch_id
        threading.Thread(target=self._run, args=(batch, files, workdir), daemon=True, name=f"generate-{batch_id}").start()
        return batch

    def cancel(self, batch_id: str) -> None:
        self._cancelled.add(batch_id)

    def _run(self, batch: dict, files: list[tuple[str, Path]], workdir: Path | None) -> None:
        batch_id = batch["batch_id"]
        try:
            docs = self._read_documents(batch, files, workdir)
            if docs:
                self._write_items(batch, docs)
            self._finish(batch)
        except Exception as e:  # never leave a batch stuck on "running"
            logger.exception("generation %s failed", batch_id)
            batch.update(status="failed" if not batch["items"] else "ready", error=str(e))
            self.store.save_batch(batch)
        finally:
            self._cancelled.discard(batch_id)
            with self._lock:
                self._active = None

    def _read_documents(self, batch: dict, files: list[tuple[str, Path]], workdir: Path | None) -> list[ReadDocument]:
        """Read every upload (one that cannot be read is reported and skipped), then delete the uploads."""
        docs: list[ReadDocument] = []
        batch["files"] = []
        try:
            for name, path in files:
                try:
                    doc = read_document(path, name)
                    docs.append(doc)
                    batch["files"].append({"name": name, "pages": doc.pages, "passages": len(doc.usable())})
                except DocumentError as e:
                    batch["files"].append({"name": name, "error": str(e)})
        finally:
            if workdir:
                shutil.rmtree(workdir, ignore_errors=True)  # nothing of the upload is kept
        if not docs:
            reasons = " ".join(f["error"] for f in batch["files"] if f.get("error"))
            batch.update(status="failed", error=reasons or "No document could be read.")
        self.store.save_batch(batch)
        return docs

    def _write_items(self, batch: dict, docs: list[ReadDocument]) -> None:
        batch_id, opts = batch["batch_id"], batch["options"]
        tasks = plan_tasks(docs, opts["categories"], opts["per_category"])
        batch["total_tasks"] = len(tasks)
        self.store.save_batch(batch)
        lock = threading.Lock()

        def work(task: Task) -> dict | None:
            if batch_id in self._cancelled:
                return None
            with lock:
                avoid = [t["question"] for it in batch["items"] if it["file"] == task.doc for t in it["turns"]]
            return generate_item(task, self._llm, turns=opts["turns"], avoid=avoid, sleep=self._sleep)

        with ThreadPoolExecutor(max_workers=max(1, self.config.generate_workers)) as pool:
            futures = {pool.submit(work, t): t for t in tasks}
            for future in as_completed(futures):
                task = futures[future]
                with lock:
                    batch["done_tasks"] += 1
                    try:
                        item = future.result()
                        if item:
                            item["item_id"] = uuid.uuid4().hex[:8]
                            batch["items"].append(item)
                    except Exception as e:
                        batch["errors"].append({"category": task.category, "file": task.doc, "reason": str(e)})
                    batch["items"].sort(key=lambda it: (CATEGORIES.index(it["category"]), it["number"]))
                    self.store.save_batch(batch)  # saved after every item: nothing is lost if the browser goes away

    def _finish(self, batch: dict) -> None:
        if batch["status"] == "failed":  # no document could be read
            return
        if batch["batch_id"] in self._cancelled:
            batch["status"] = "cancelled"
        elif not batch["items"]:
            batch.update(status="failed", error="No question could be written. " + (batch["errors"][0]["reason"] if batch["errors"] else ""))
        else:
            batch["status"] = "ready"
        self.store.save_batch(batch)

    # ---- review -------------------------------------------------------------------------------

    def _editable(self, batch_id: str) -> dict:
        batch = self.store.get_batch(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        if batch["status"] == "running":
            raise GenerationBusy("Wait for generation to finish before editing")
        return batch

    def edit_item(self, batch_id: str, item_id: str, turns: list[dict]) -> dict:
        """Reword the question / expected answer of an item. The evidence and the number of turns stay as they are."""
        batch = self._editable(batch_id)
        item = next((i for i in batch["items"] if i["item_id"] == item_id), None)
        if item is None:
            raise KeyError(item_id)
        if len(turns) != len(item["turns"]):
            raise ValueError("The number of turns cannot change")
        for turn, new in zip(item["turns"], turns):
            question, answer = str(new.get("question", "")).strip(), str(new.get("expected_answer", "")).strip()
            problem = check_text(question, answer, standalone=False)
            if problem:
                raise ValueError(problem[0].upper() + problem[1:])
            turn["question"], turn["expected_answer"] = question, answer
        self.store.save_batch(batch)
        return item

    def remove_item(self, batch_id: str, item_id: str) -> None:
        batch = self._editable(batch_id)
        remaining = [i for i in batch["items"] if i["item_id"] != item_id]
        if len(remaining) == len(batch["items"]):
            raise KeyError(item_id)
        batch["items"] = remaining
        self.store.save_batch(batch)

    def _chat_ids(self, items: list[dict]) -> dict[str, str]:
        """A short chat id for each item: ``direct-1``, ``multiturn-2``, ... Numbering carries on after the highest one
        already in the store, so ids never collide with a case that exists."""
        highest: dict[str, int] = {}
        for case in self.store.list_test_cases():
            found = re.fullmatch(r"([a-z]+)-(\d+)", str(case.get("chat_id", "")))
            if found and found.group(1) in CATEGORIES:
                highest[found.group(1)] = max(highest.get(found.group(1), 0), int(found.group(2)))
        ids = {}
        for item in items:
            highest[item["category"]] = highest.get(item["category"], 0) + 1
            ids[item["item_id"]] = f"{item['category']}-{highest[item['category']]}"
        return ids

    def approve(self, batch_id: str, item_ids: list[str] | None = None) -> dict:
        """Turn the chosen items (all by default) into test cases, labelled by category, and delete the batch.
        Anything not chosen is discarded with it."""
        batch = self.store.get_batch(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        if batch["status"] == "running":
            raise GenerationBusy("Wait for generation to finish, or cancel it first")
        wanted = set(item_ids) if item_ids is not None else None
        chosen = [it for it in batch["items"] if wanted is None or it["item_id"] in wanted]
        if not chosen:
            raise ValueError("There is nothing to approve")

        chat_ids = self._chat_ids(chosen)
        rows = []
        for item in chosen:
            for turn_no, turn in enumerate(item["turns"], start=1):
                rows.append({
                    "row": len(rows) + 2, "chat_id": chat_ids[item["item_id"]], "turn_no": turn_no, "type": CASE_TYPE,
                    "question": turn["question"], "expected_answer": turn["expected_answer"],
                    "expected_sources": item["file"], "groups": [CATEGORY_LABELS[item["category"]]],
                    "origin": {
                        "kind": "generated", "category": item["category"], "file": item["file"],
                        "evidence": turn["evidence"], "model": batch.get("model", ""),
                        **({"needs_context": turn["needs_context"]} if turn.get("needs_context") else {}),
                    },
                })
        result = self.store.import_cases(rows)
        self.store.delete_batch(batch_id)
        return {
            "cases": len(rows), "items": len(chosen), "discarded": len(batch["items"]) - len(chosen),
            "groups": [label for key, label in CATEGORY_LABELS.items() if any(i["category"] == key for i in chosen)],
            "groups_created": result["groups_created"],
        }
