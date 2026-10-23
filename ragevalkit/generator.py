"""Writing test cases from documents.

FLOW
----
1. ``docs.read_document`` turns each upload into passages (and the upload is deleted).
2. ``plan_tasks`` decides which passages each question is written from: passages are taken in a spread
   order so they sample the whole document, and questions are shared out across the uploaded files.
3. Each task asks the model for ONE item of its category (a question, or a whole conversation) and
   ``validate`` rejects anything that breaks the rules — most importantly, every piece of evidence must be a
   verbatim quote that really is in the passages. A rejected item is retried with the reason spelled out.
4. Finished items are saved on the server straight away (a *review batch*), so closing the browser or losing
   the network loses nothing. They only become test cases when someone approves them; batches that are never
   approved are deleted after ``batch_ttl_hours``.

CATEGORIES
----------
direct     answered by one plainly stated fact
indirect   answered from the document, but phrased in everyday words / as a situation, not the document's own
multipart  one question with two or more parts, answered from different passages
multiturn  a short conversation whose follow-ups only make sense with the earlier turns
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from ragevalkit import lexical
from ragevalkit.docs import Chunk, ReadDocument, normalise, read_document, spread_order
from ragevalkit.exceptions import DocumentError, RagevalError

logger = logging.getLogger(__name__)

CATEGORY_LABELS = {"direct": "Direct", "indirect": "Indirect", "multipart": "Multi-part", "multiturn": "Multi-turn"}
CATEGORIES = tuple(CATEGORY_LABELS)

MAX_ATTEMPTS = 3
MIN_QUOTE_CHARS = 15
SIMILARITY_LIMIT = 0.75


class GenerationError(RagevalError):
    """A question could not be written that follows every rule."""


class GenerationBusy(RagevalError):
    """Another generation is already running."""


# ---------------------------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------------------------

COMMON_RULES = """You write test questions for an assistant that answers from a company's documents. You are given passages from one document.

Rules:
- Use ONLY the passages. Every fact in the expected answer must be stated in them.
- The question must stand on its own: someone who has never seen the document must understand it. Never write "the passage", "the document", "the text", "this section" or "according to".
- Do not ask about page numbers, layout, or the document itself.
- Write in the same language as the passages.
- The expected answer is complete but short: one to three sentences.
- "evidence" lists exact quotes copied word for word from the passages (8 to 40 words each). Never paraphrase a quote."""

CATEGORY_RULES = {
    "direct": """Write ONE direct question. It asks for a fact that one passage states plainly, so it can be answered by finding that sentence.

Reply with JSON only: {"question": "...", "expected_answer": "...", "evidence": ["exact quote"]}""",
    "indirect": """Write ONE indirect question. The answer is in the passages, but the question does NOT reuse the passage's own wording: it describes a situation, uses everyday words or synonyms, or needs a small step of inference (for example "If I leave tomorrow, how much notice do I owe?"). Never copy a phrase of four or more words from the passages into the question.

Reply with JSON only: {"question": "...", "expected_answer": "...", "evidence": ["exact quote"]}""",
    "multipart": """Write ONE multi-part question: a single question that asks for two or more distinct things (for example "What is the refund window, and who has to approve an exception?"). The parts must be answered by DIFFERENT passages (Passage A and Passage B). The expected answer addresses every part. Give at least one evidence quote from each passage.

Reply with JSON only: {"question": "...", "expected_answer": "...", "evidence": ["quote from A", "quote from B"]}""",
    "multiturn": """Write ONE conversation of exactly {turns} turns between a user and an assistant. Turn 1 is a normal, self-contained question. Every later turn is a natural follow-up that depends on the earlier turns (it uses "it", "that" or "what about ...?" and cannot be understood alone). Each turn has its own expected answer, grounded in the passages, with its own evidence.

Reply with JSON only: {"turns": [{"question": "...", "expected_answer": "...", "evidence": ["exact quote"]}, ...]}""",
}

# phrases that make a question depend on seeing the document
_NOT_STANDALONE = re.compile(
    r"\b(the|this|that|these|those)\s+(passage|passages|document|text|excerpt|section|paragraph|pdf|file)\b"
    r"|\baccording to (the|this)\b|\bpassage [ab]\b|\bas (stated|mentioned|described) (above|earlier|in)\b|\bprovided (text|context)\b",
    re.I,
)


# ---------------------------------------------------------------------------------------------
# Planning: which passages each question is written from
# ---------------------------------------------------------------------------------------------

@dataclass
class Task:
    category: str
    doc: str
    chunks: list[Chunk]
    number: int          # 1-based within its category


class _Stream:
    """Hands out a document's usable passages in a spread order, wrapping round when it runs out."""

    def __init__(self, doc: ReadDocument):
        self.chunks = doc.usable()
        self.order = spread_order(len(self.chunks))
        self.pointer = 0

    def take(self, k: int) -> list[Chunk]:
        if len(self.chunks) == 1 and k == 2:
            return _halves(self.chunks[0])
        picked = []
        for _ in range(k):
            picked.append(self.chunks[self.order[self.pointer % len(self.order)]])
            self.pointer += 1
        return picked


def _halves(chunk: Chunk) -> list[Chunk]:
    """A document with a single passage: split it so a multi-part question still has two passages."""
    pieces = [p for p in re.split(r"\n\s*\n|\n", chunk.text) if p.strip()]
    if len(pieces) < 2:  # one long paragraph: cut at a sentence boundary instead
        pieces = [p for p in re.split(r"(?<=[.!?])\s+", chunk.text) if p.strip()]
    middle = max(1, len(pieces) // 2)
    texts = [" ".join(pieces[:middle]), " ".join(pieces[middle:]) or chunk.text]
    return [Chunk(id=f"{chunk.id}.{i}", file=chunk.file, text=t, label=chunk.label, pages=chunk.pages) for i, t in enumerate(texts, 1)]


def plan_tasks(docs: list[ReadDocument], categories: list[str], per_category: int) -> list[Task]:
    """``per_category`` questions in each category, shared out across the documents in turn."""
    streams = {d.name: _Stream(d) for d in docs}
    tasks = []
    for category in categories:
        for i in range(per_category):
            doc = docs[i % len(docs)]
            tasks.append(Task(category, doc.name, streams[doc.name].take(2 if category == "multipart" else 1), i + 1))
    return tasks


# ---------------------------------------------------------------------------------------------
# Checking what the model wrote
# ---------------------------------------------------------------------------------------------

def _loads(raw: str | None) -> dict | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    for candidate in (text, text[text.find("{"): text.rfind("}") + 1] if "{" in text else ""):
        try:
            data = json.loads(candidate)
            return data if isinstance(data, dict) else None
        except ValueError:
            continue
    return None


def _similar(a: str, b: str) -> float:
    x, y = set(lexical.tokenize(a)), set(lexical.tokenize(b))
    return len(x & y) / len(x | y) if x | y else 0.0


def _evidence(quotes, chunks: list[Chunk], normalised: list[str]) -> list[dict]:
    """The quotes that really are in the passages, with the file, page and passage letter each came from."""
    found = []
    for quote in quotes if isinstance(quotes, list) else [quotes]:
        text = str(quote or "").strip()
        n = normalise(text)
        if len(n) < MIN_QUOTE_CHARS:
            continue
        for index, (chunk, chunk_text) in enumerate(zip(chunks, normalised)):
            if n in chunk_text:
                found.append({"quote": text, "file": chunk.file, "page": chunk.page_of(n), "passage": "AB"[index] if index < 2 else "A"})
                break
    return found


def _check_text(question: str, answer: str, *, standalone: bool) -> str | None:
    if not 12 <= len(question) <= 400:
        return "the question must be between 12 and 400 characters"
    if not 3 <= len(answer) <= 1200:
        return "the expected answer must be between 3 and 1200 characters"
    if standalone and _NOT_STANDALONE.search(question):
        return 'the question refers to "the passage / document / text"; it must stand on its own'
    return None


def validate(task: Task, data: dict | None, *, turns: int, avoid: list[str]) -> tuple[list[dict] | None, str]:
    """Check one model reply. Returns (turns, "") when it follows every rule, else (None, reason)."""
    if not data:
        return None, "the reply was not valid JSON in the required shape"
    normalised = [normalise(c.text) for c in task.chunks]
    raw_turns = data.get("turns") if task.category == "multiturn" else [data]
    if not isinstance(raw_turns, list) or not raw_turns:
        return None, 'the reply must contain "turns" for a conversation' if task.category == "multiturn" else "missing question"
    if task.category == "multiturn" and not 2 <= len(raw_turns) <= max(2, turns):
        return None, f"the conversation must have {turns} turns"

    out: list[dict] = []
    for index, raw in enumerate(raw_turns):
        if not isinstance(raw, dict):
            return None, "each turn must be an object with question, expected_answer and evidence"
        question, answer = str(raw.get("question") or "").strip(), str(raw.get("expected_answer") or "").strip()
        problem = _check_text(question, answer, standalone=index == 0)
        if problem:
            return None, problem
        evidence = _evidence(raw.get("evidence"), task.chunks, normalised)
        if not evidence:
            return None, "none of the evidence quotes appears word for word in the passages; copy quotes exactly"
        if task.category == "multipart" and len({e["passage"] for e in evidence}) < 2:
            return None, "a multi-part question needs evidence from both Passage A and Passage B"
        if task.category == "indirect":
            joined = " ".join(normalised)
            words = normalise(question).split()
            if any(" ".join(words[i:i + 4]) in joined for i in range(len(words) - 3)):
                return None, "the question copies four or more words in a row from the passages; rephrase it in everyday words"
            q_tokens = set(lexical.tokenize(question))
            if q_tokens and len(q_tokens & set(lexical.tokenize(" ".join(e["quote"] for e in evidence)))) / len(q_tokens) > 0.6:
                return None, "the question uses too many of the evidence's own words; make it more indirect"
        if any(_similar(question, other) >= SIMILARITY_LIMIT for other in avoid + [t["question"] for t in out]):
            return None, "this is too similar to a question already written; ask about something different"
        out.append({"question": question, "expected_answer": answer, "evidence": evidence})
    return out, ""


# ---------------------------------------------------------------------------------------------
# Asking the model
# ---------------------------------------------------------------------------------------------

class LiteLLM:
    """The configured model: ``generator_model`` if set, otherwise the judge's model, through LiteLLM."""

    def __init__(self, config):
        self.config = config

    @property
    def model(self) -> str:
        return self.config.generator_model or self.config.judge_model

    def __call__(self, messages: list[dict]) -> str:
        import litellm

        kwargs: dict = dict(model=self.model, messages=messages, response_format={"type": "json_object"})
        if self.config.judge_api_key:
            kwargs["api_key"] = self.config.judge_api_key
        try:
            resp = litellm.completion(**kwargs)
        except Exception as e:
            if "response_format" not in str(e).lower():
                raise
            kwargs.pop("response_format")  # this provider has no JSON mode: the prompt asks for JSON anyway
            resp = litellm.completion(**kwargs)
        return resp.choices[0].message.content


def _prompt(task: Task, turns: int, avoid: list[str]) -> list[dict]:
    system = COMMON_RULES + "\n\n" + CATEGORY_RULES[task.category].replace("{turns}", str(turns))
    parts = [f"[Passage {'AB'[i]}] ({c.label})\n{c.text}" for i, c in enumerate(task.chunks[:2])]
    user = "\n\n".join(parts)
    if avoid:
        user += "\n\nQuestions already written (do not repeat or closely resemble them):\n" + "\n".join(f"- {q}" for q in avoid[-12:])
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def generate_item(task: Task, llm: Callable, *, turns: int, avoid: list[str], sleep: Callable = time.sleep) -> dict:
    """One finished item for a task, retrying with the reason whenever the model's reply is rejected."""
    messages = _prompt(task, turns, avoid)
    reason = "no reply"
    for attempt in range(MAX_ATTEMPTS):
        try:
            raw = llm(messages)
        except Exception as e:  # network, rate limit, provider error
            reason = f"the model could not be reached: {e}"
            logger.warning("generation call failed (attempt %d): %s", attempt + 1, e)
            sleep(1.5 * (attempt + 1))
            continue
        checked, reason = validate(task, _loads(raw), turns=turns, avoid=avoid)
        if checked is not None:
            return {"category": task.category, "file": task.doc, "number": task.number, "turns": checked}
        messages = messages + [
            {"role": "assistant", "content": raw or ""},
            {"role": "user", "content": f"That was rejected: {reason}. Write a different one that follows every rule. Reply with JSON only."},
        ]
    raise GenerationError(reason)


# ---------------------------------------------------------------------------------------------
# The job: runs in the background, saves as it goes
# ---------------------------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


class GenerationManager:
    """Starts generation jobs and turns approved review batches into test cases."""

    def __init__(self, config, store, llm: Callable | None = None):
        self.config = config
        self.store = store
        self._llm = llm or LiteLLM(config)
        self._lock = threading.Lock()
        self._active: str | None = None
        self._cancelled: set[str] = set()
        self.store.interrupt_running_batches()  # a restart cannot resume a job, but what it saved stays reviewable

    @property
    def model(self) -> str:
        return getattr(self._llm, "model", None) or self.config.generator_model or self.config.judge_model

    def limits(self) -> dict:
        return {
            "max_files": self.config.generate_max_files,
            "max_file_mb": self.config.generate_max_file_mb,
            "per_category_max": self.config.generate_per_category_max,
            "per_category_default": 3,
            "turns_default": 3,
            "categories": [{"key": k, "label": v} for k, v in CATEGORY_LABELS.items()],
            "model": self.model,
            "ttl_hours": self.config.batch_ttl_hours,
            "formats": ["pdf", "txt", "md"],
        }

    def start(self, files: list[tuple[str, Path]], workdir: Path | None, *, per_category: int, categories: list[str], turns: int) -> dict:
        """Create a review batch and start writing into it. ``files`` are (name, path) pairs; ``workdir`` is deleted once read."""
        categories = [c for c in CATEGORIES if c in categories]
        if not categories:
            raise ValueError("Choose at least one category")
        if not 1 <= per_category <= self.config.generate_per_category_max:
            raise ValueError(f"Questions per category must be between 1 and {self.config.generate_per_category_max}")
        if not 2 <= turns <= 4:
            raise ValueError("A conversation needs between 2 and 4 turns")
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
        batch_id, opts = batch["batch_id"], batch["options"]
        lock = threading.Lock()
        try:
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
                batch.update(status="failed", error=" ".join(f["error"] for f in batch["files"] if f.get("error")) or "No document could be read.")
                self.store.save_batch(batch)
                return

            tasks = plan_tasks(docs, opts["categories"], opts["per_category"])
            batch["total_tasks"] = len(tasks)
            self.store.save_batch(batch)

            def work(task: Task) -> dict | None:
                if batch_id in self._cancelled:
                    return None
                with lock:
                    avoid = [t["question"] for it in batch["items"] if it["file"] == task.doc for t in it["turns"]]
                return generate_item(task, self._llm, turns=opts["turns"], avoid=avoid)

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
                                item["chat_id"] = f"gen-{batch_id[:6]}-{item['category']}-{item['number']}"
                                batch["items"].append(item)
                        except Exception as e:
                            batch["errors"].append({"category": task.category, "file": task.doc, "reason": str(e)})
                        batch["items"].sort(key=lambda it: (CATEGORIES.index(it["category"]), it["number"]))
                        self.store.save_batch(batch)  # saved after every item: nothing is lost if the browser goes away

            if batch_id in self._cancelled:
                batch["status"] = "cancelled"
            elif not batch["items"]:
                batch.update(status="failed", error="No question could be written. " + (batch["errors"][0]["reason"] if batch["errors"] else ""))
            else:
                batch["status"] = "ready"
            self.store.save_batch(batch)
        except Exception as e:  # never leave a batch stuck on "running"
            logger.exception("generation %s failed", batch_id)
            batch.update(status="failed" if not batch["items"] else "ready", error=str(e))
            self.store.save_batch(batch)
        finally:
            self._cancelled.discard(batch_id)
            with self._lock:
                self._active = None

    # ---- review ------------------------------------------------------------------------------

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
            problem = _check_text(question, answer, standalone=False)
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

    def approve(self, batch_id: str, item_ids: list[str] | None = None) -> dict:
        """Turn the chosen items (all by default) into test cases, labelled by category, and delete the batch.
        Anything not chosen is discarded with it."""
        batch = self.store.get_batch(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        if batch["status"] == "running":
            raise GenerationBusy("Wait for generation to finish, or cancel it first")
        chosen = [it for it in batch["items"] if item_ids is None or it["item_id"] in set(item_ids)]
        if not chosen:
            raise ValueError("There is nothing to approve")
        rows, number = [], 2
        for item in chosen:
            for turn_no, turn in enumerate(item["turns"], start=1):
                evidence = turn["evidence"]
                rows.append({
                    "row": number, "chat_id": item["chat_id"], "turn_no": turn_no, "type": item["category"],
                    "question": turn["question"], "expected_answer": turn["expected_answer"],
                    "expected_sources": item["file"], "groups": [CATEGORY_LABELS[item["category"]]],
                    "origin": {"kind": "generated", "file": item["file"], "evidence": evidence, "model": batch.get("model", "")},
                })
                number += 1
        result = self.store.import_cases(rows)
        self.store.delete_batch(batch_id)
        return {
            "cases": len(rows), "items": len(chosen), "discarded": len(batch["items"]) - len(chosen),
            "groups": sorted({CATEGORY_LABELS[i["category"]] for i in chosen}, key=list(CATEGORY_LABELS.values()).index),
            "groups_created": result["groups_created"],
        }
