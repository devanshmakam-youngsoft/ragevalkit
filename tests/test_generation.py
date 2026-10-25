"""Writing test cases from documents: reading, planning, checking, the background job and approval."""
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from ragevalkit.config import Config
from ragevalkit.docs import Chunk, normalise, read_document, spread_order
from ragevalkit.exceptions import DocumentError
from ragevalkit.generator import GenerationError, Task, generate_item, plan_tasks, validate
from ragevalkit.server import create_app


# ---- helpers ------------------------------------------------------------------------------

SUBJECTS = ["Expense claims", "Visitor badges", "Password resets", "Holiday requests", "Equipment orders", "Training courses",
            "Parking permits", "Security incidents", "Supplier invoices", "Remote work agreements", "Medical certificates", "Meeting rooms"]
DEPARTMENTS = ["finance", "reception", "the service desk", "human resources", "procurement", "the learning team",
               "facilities", "the security office", "accounts payable", "the people team", "occupational health", "the office manager"]
ACTIONS = ["must be submitted", "has to be registered", "is requested", "should be confirmed", "needs written approval", "can be cancelled"]


def sentences(count: int, start: int = 0) -> str:
    """Sentences that differ from one another in subject, owner and wording, like a real policy."""
    return " ".join(
        f"{SUBJECTS[(start + i) % len(SUBJECTS)]} {ACTIONS[(start + i * 5) % len(ACTIONS)]} through {DEPARTMENTS[(start + i * 7) % len(DEPARTMENTS)]} "
        f"within {(start + i) % 9 + 3} working days, and amounts above {(start + i + 1) * 125} dollars need a second signature "
        f"from the {['director', 'supervisor', 'auditor', 'coordinator'][(start + i) % 4]} before processing continues."
        for i in range(start, start + count)
    )


def long_text(paragraphs: int = 10) -> str:
    return "\n\n".join(sentences(8, start=p * 3) for p in range(paragraphs))


def make_pdf(pages: list[str]) -> bytes:
    """A small valid text PDF (no extra libraries), one string per page."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{' '.join(f'{4 + 2 * i} 0 R' for i in range(len(pages)))}] /Count {len(pages)} >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i, text in enumerate(pages):
        lines = re.findall(r".{1,95}(?:\s|$)", text) or [text]
        stream = "BT /F1 9 Tf 30 770 Td 11 TL " + " ".join(f"({esc(ln.strip())}) Tj T*" for ln in lines) + " ET"
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {5 + 2 * i} 0 R "
                    f"/Resources << /Font << /F1 3 0 R >> >> >>")
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    return out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()


class FakeLLM:
    """Writes a valid item of whatever category the prompt asks for, quoting the passages word for word."""

    def __init__(self, hold: threading.Event | None = None, fail_first: int = 0):
        self.calls = 0
        self.hold = hold
        self.fail_first = fail_first
        self.lock = threading.Lock()

    def __call__(self, messages):
        with self.lock:
            self.calls += 1
            n = self.calls
        if self.hold is not None:
            self.hold.wait(10)
        if n <= self.fail_first:
            raise ConnectionError("network down")
        system, user = messages[0]["content"], messages[1]["content"]
        passages = [p.strip() for p in re.findall(r"\[Passage [AB]\] \([^)]*\)\n(.*?)(?=\n\n\[Passage|\n\nQuestions already|\Z)", user, re.S)]
        passages = [re.sub(r"\[[AB]\d+\] ", "", p) for p in passages]      # the sentence numbers are not part of the text

        def quote(text, k):
            words = text.split()
            start = (k * 11) % max(1, len(words) - 14)
            return " ".join(words[start:start + 14])

        def topic(text, k):
            words = [w for w in re.findall(r"[A-Za-z]+", quote(text, k))][2:6]
            return " ".join(words)

        import json
        if "ONE direct question" in system:
            return json.dumps({"question": f"What is the rule about {topic(passages[0], n)}?",
                               "expected_answer": "Claims follow the stated deadline.", "evidence": [quote(passages[0], n)]})
        if "ONE indirect question" in system:
            asks = ["Suppose a colleague is late with paperwork, what happens next?", "How soon must a manager react when someone sends a request?",
                    "A person came back from a trip last week, what are they supposed to do now?", "What is the deadline for reimbursing someone who travelled?",
                    "Who gets to decide when somebody wants money back for a journey?", "Is a late request still accepted after a month away?"]
            return json.dumps({"question": asks[n % len(asks)], "expected_answer": "They must follow the stated deadline.",
                               "evidence": [quote(passages[0], n)]})
        if "multi-part question" in system:
            return json.dumps({"question": f"What is the rule about {topic(passages[0], n)}, and what is the rule about {topic(passages[1], n + 1)}?",
                               "expected_answer": "Both rules are stated.", "evidence": [quote(passages[0], n), quote(passages[1], n)]})
        turns = int(re.search(r"exactly (\d+) turns", system).group(1))
        follow_ups = [("And what happens if I miss that by {n} days?", "the deadline given in the previous answer"),
                      ("Who has to sign off on it when it is {n} dollars?", "the amount mentioned earlier"),
                      ("Does the same apply to the other cases there, say {n}?", "the rule explained in the earlier answers")]

        def turn(t):
            question, needs = (f"What is the rule about {topic(passages[0], n)}?", "") if t == 0 else (
                follow_ups[(t - 1) % 3][0].format(n=n * 10 + t), follow_ups[(t - 1) % 3][1])
            return {"question": question, "expected_answer": f"Answer {t + 1}.", "evidence": [quote(passages[0], n + t)], "depends_on": needs}

        return json.dumps({"turns": [turn(t) for t in range(turns)]})


def chunk(text: str, file="a.txt", label="page 1") -> Chunk:
    return Chunk(id=f"{file}#1", file=file, text=text, label=label, pages=[(1, normalise(text))])


# ---- reading documents ----------------------------------------------------------------------

def test_text_and_markdown_files_become_passages_that_remember_their_section(tmp_path):
    md = tmp_path / "policy.md"
    md.write_text("# Expenses\n\n" + long_text(5) + "\n\n# Travel\n\n" + long_text(5), encoding="utf-8")
    doc = read_document(md)
    assert doc.pages is None and len(doc.usable()) >= 3
    assert doc.chunks[0].label == "section: Expenses"
    txt = tmp_path / "notes.txt"
    txt.write_text(long_text(3), encoding="utf-8")
    assert read_document(txt).chunks[0].label == "document"


def test_a_pdf_is_read_page_by_page_so_evidence_can_cite_the_page(tmp_path):
    pdf = tmp_path / "handbook.pdf"
    pdf.write_bytes(make_pdf([sentences(10, 0), sentences(10, 100), sentences(10, 200)]))
    doc = read_document(pdf)
    assert doc.pages == 3 and doc.usable()
    first = doc.chunks[0]
    assert "page" in first.label
    quote = normalise(sentences(10, 100)[:70])
    holder = next(c for c in doc.chunks if quote in normalise(c.text))
    assert holder.page_of(quote) == "page 2"


def test_unreadable_documents_say_why(tmp_path):
    scanned = tmp_path / "scan.pdf"
    scanned.write_bytes(make_pdf([""]))
    with pytest.raises(DocumentError, match="no selectable text"):
        read_document(scanned)
    with pytest.raises(DocumentError, match="unsupported file type"):
        read_document(tmp_path / "slides.pptx", "slides.pptx")
    tiny = tmp_path / "tiny.txt"
    tiny.write_text("hi", encoding="utf-8")
    with pytest.raises(DocumentError):
        read_document(tiny)
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf at all")
    with pytest.raises(DocumentError, match="could not be read"):
        read_document(broken)


def test_spread_order_samples_the_whole_document_in_any_prefix():
    assert spread_order(8) == [0, 4, 2, 6, 1, 5, 3, 7]
    assert spread_order(0) == [] and spread_order(1) == [0]


# ---- planning ---------------------------------------------------------------------------------

def test_questions_are_shared_across_documents_and_spread_through_each(tmp_path):
    docs = []
    for name in ("a.txt", "b.md"):
        path = tmp_path / name
        path.write_text(long_text(10), encoding="utf-8")
        docs.append(read_document(path))
    tasks = plan_tasks(docs, ["direct", "multipart"], per_category=3)
    assert [t.category for t in tasks].count("direct") == 3 and [t.category for t in tasks].count("multipart") == 3
    assert {t.doc for t in tasks if t.category == "direct"} == {"a.txt", "b.md"}
    assert all(len(t.chunks) == 2 and t.chunks[0].id != t.chunks[1].id for t in tasks if t.category == "multipart")
    a_ids = [t.chunks[0].id for t in tasks if t.doc == "a.txt" and t.category == "direct"]
    assert len(set(a_ids)) == len(a_ids)                                   # different passages, not the same one twice


def test_a_one_passage_document_still_gives_a_multipart_question_two_passages(tmp_path):
    path = tmp_path / "short.txt"
    path.write_text(sentences(14), encoding="utf-8")
    doc = read_document(path)
    assert len(doc.chunks) == 1
    (task,) = plan_tasks([doc], ["multipart"], 1)
    assert len(task.chunks) == 2 and task.chunks[0].text != task.chunks[1].text


# ---- checking what the model wrote ------------------------------------------------------------

PASSAGE = ("Employees must submit expense claims within thirty days of travel. Managers approve claims above five hundred dollars "
           "within five working days. Late claims are paid in the next monthly cycle unless finance grants an exception in writing.")


def task(category="direct", chunks=None):
    return Task(category, "a.txt", chunks or [chunk(PASSAGE)], 1)


def reply(**kw):
    base = {"question": "Within how many days must travel expenses be submitted?", "expected_answer": "Within thirty days of travel.",
            "evidence": ["Employees must submit expense claims within thirty days of travel."]}
    return {**base, **kw}


def test_a_valid_item_passes_and_keeps_its_evidence_with_the_page():
    turns, reason = validate(task(), reply(), turns=3, avoid=[])
    assert reason == "" and turns[0]["evidence"] == [{
        "quote": "Employees must submit expense claims within thirty days of travel.", "file": "a.txt", "page": "page 1", "passage": "A"}]


@pytest.mark.parametrize("changes, expected", [
    ({"evidence": ["Employees can submit claims whenever they feel like it at all."]}, "does not point at any sentence"),   # invented quote
    ({"evidence": ["too short"]}, "does not point at any sentence"),
    ({"question": "According to the document, what is the deadline?"}, "stand on its own"),
    ({"question": "Why?"}, "between 12 and 400"),
    ({"expected_answer": ""}, "expected answer"),
])
def test_rejects_items_that_break_the_rules(changes, expected):
    turns, reason = validate(task(), reply(**changes), turns=3, avoid=[])
    assert turns is None and expected in reason


def test_a_hallucinated_quote_among_good_ones_is_dropped_not_fatal():
    turns, _ = validate(task(), reply(evidence=["Totally made up sentence that is not in the text at all.",
                                                 "Managers approve claims above five hundred dollars within five working days."]), turns=3, avoid=[])
    assert [e["quote"] for e in turns[0]["evidence"]] == ["Managers approve claims above five hundred dollars within five working days."]


def test_indirect_questions_must_not_reuse_the_documents_wording():
    copied = reply(question="Who approves claims above five hundred dollars within five working days?")
    assert validate(task("indirect"), copied, turns=3, avoid=[])[1].startswith("the question copies")
    fine = reply(question="If my manager is on holiday, who signs off a big refund request?")
    assert validate(task("indirect"), fine, turns=3, avoid=[])[0] is not None


def test_multipart_needs_evidence_from_both_passages():
    other = "Visitors must sign the register at reception and wear a badge at all times while inside the building premises."
    chunks = [chunk(PASSAGE, label="page 1"), chunk(other, label="page 2")]
    one = reply(question="What is the deadline, and who approves?", evidence=["Employees must submit expense claims within thirty days of travel."])
    assert "both Passage A and Passage B" in validate(task("multipart", chunks), one, turns=3, avoid=[])[1]
    both = reply(question="What is the deadline, and what must visitors do?",
                 evidence=["Employees must submit expense claims within thirty days of travel.",
                           "Visitors must sign the register at reception and wear a badge at all times"])
    assert validate(task("multipart", chunks), both, turns=3, avoid=[])[0] is not None


def test_multiturn_needs_the_right_number_of_turns_and_only_the_first_must_stand_alone():
    follow = {"question": "And what about the ones above that amount?", "expected_answer": "Managers approve them within five working days.",
              "evidence": ["Managers approve claims above five hundred dollars within five working days."],
              "depends_on": "the filing deadline given in the first answer"}
    first = {"question": "How long do I have to submit an expense claim?", "expected_answer": "Thirty days.",
             "evidence": ["Employees must submit expense claims within thirty days of travel."]}
    ok, reason = validate(task("multiturn"), {"turns": [first, follow]}, turns=2, avoid=[])
    assert reason == "" and len(ok) == 2
    assert validate(task("multiturn"), {"turns": [first]}, turns=3, avoid=[])[0] is None
    bad_first = dict(first, question="According to the document, how long is the deadline?")
    assert validate(task("multiturn"), {"turns": [bad_first, follow]}, turns=2, avoid=[])[0] is None


def test_near_duplicate_questions_are_rejected():
    _, reason = validate(task(), reply(), turns=3, avoid=["Within how many days must travel expenses be submitted?"])
    assert "too similar" in reason


def test_a_rejected_reply_is_retried_with_the_reason_and_network_errors_are_survived():
    replies = iter(["not json", None, reply()])
    seen = []

    def llm(messages):
        seen.append(messages)
        value = next(replies)
        if value is None:
            raise ConnectionError("blip")
        return value if isinstance(value, str) else __import__("json").dumps(value)

    item = generate_item(task(), llm, turns=3, avoid=[], sleep=lambda s: None)
    assert item["turns"][0]["question"].startswith("Within how many days") and len(seen) == 3
    assert "rejected" in seen[1][-1]["content"]

    with pytest.raises(GenerationError):
        generate_item(task(), lambda m: "never json", turns=3, avoid=[], sleep=lambda s: None)


# ---- the job, review and approval over the API ---------------------------------------------------

@pytest.fixture
def make_client(tmp_path):
    clients = []

    def build(llm=None, **config):
        config.setdefault("generate_workers", 4)
        cfg = Config(store_path=tmp_path / f"store{len(clients)}.json", require_login=False, eval_secret="s", **config)
        c = TestClient(create_app(cfg, fn=lambda q: "a", generation_llm=llm or FakeLLM()))
        c.__enter__()
        clients.append(c)
        return c

    yield build
    for c in clients:
        c.__exit__(None, None, None)


def upload(client, files, **data):
    return client.post("/api/generate", files=[("files", f) for f in files], data=data)


def wait(client, batch_id, until=("ready", "failed", "cancelled"), timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        batch = client.get(f"/api/generate/{batch_id}").json()
        if batch["status"] in until:
            return batch
        time.sleep(0.05)
    raise AssertionError(f"still {batch['status']}")


TXT = ("policy.txt", long_text(12).encode(), "text/plain")
MD = ("faq.md", ("# FAQ\n\n" + long_text(12)).encode(), "text/markdown")
PDF = ("handbook.pdf", make_pdf([sentences(10, 0), sentences(10, 100), sentences(10, 200), sentences(10, 300)]), "application/pdf")


def test_documents_in_questions_out_and_nothing_is_kept_of_the_upload(make_client):
    client = make_client()
    started = upload(client, [TXT, MD, PDF], per_category=3, turns=3)
    assert started.status_code == 202
    batch = wait(client, started.json()["batch_id"])
    assert batch["status"] == "ready" and batch["errors"] == []
    by_category = {c: [i for i in batch["items"] if i["category"] == c] for c in ("direct", "indirect", "multipart", "multiturn")}
    assert {c: len(v) for c, v in by_category.items()} == {"direct": 3, "indirect": 3, "multipart": 3, "multiturn": 3}
    assert all(len(i["turns"]) == 3 for i in by_category["multiturn"]) and all(len(i["turns"]) == 1 for i in by_category["direct"])
    assert {i["file"] for i in batch["items"]} == {"policy.txt", "faq.md", "handbook.pdf"}
    pdf_item = next(i for i in batch["items"] if i["file"] == "handbook.pdf")
    assert pdf_item["turns"][0]["evidence"][0]["page"].startswith("page ")
    assert [f["name"] for f in batch["files"]] == ["policy.txt", "faq.md", "handbook.pdf"] and "chunks" not in str(batch)
    assert client.app.state.store.list_test_cases() == []                      # nothing is a test case yet


def test_review_then_approve_adds_cases_labelled_by_category_with_their_evidence(make_client):
    client = make_client()
    batch = wait(client, upload(client, [TXT], per_category=2, turns=2).json()["batch_id"])
    bid = batch["batch_id"]
    drop = batch["items"][0]
    assert client.delete(f"/api/generate/{bid}/items/{drop['item_id']}").status_code == 200
    keep = batch["items"][1]
    edited = client.patch(f"/api/generate/{bid}/items/{keep['item_id']}",
                          json={"turns": [{"question": "How many days do I have to file my travel expenses?", "expected_answer": "Ten days."}] * len(keep["turns"])})
    assert edited.status_code == 200
    assert client.patch(f"/api/generate/{bid}/items/{keep['item_id']}", json={"turns": []}).status_code == 422

    done = client.post(f"/api/generate/{bid}/approve", json={}).json()
    assert done["items"] == len(batch["items"]) - 1 and done["groups"] == ["Direct", "Indirect", "Multi-part", "Multi-turn"]
    cases = client.get("/api/test-cases").json()
    assert len(cases) == done["cases"] == sum(len(i["turns"]) for i in batch["items"]) - len(drop["turns"])
    assert {g["name"] for c in cases for g in c["groups"]} == {"Direct", "Indirect", "Multi-part", "Multi-turn"}
    assert {c["type"] for c in cases} == {"rag"}                                 # the type is rag; the category is the group
    sample = next(c for c in cases if c["origin"]["category"] == "multiturn" and c["turn_no"] == 2)
    assert sample["origin"]["needs_context"] and sample["expected_sources"] == "policy.txt" and sample["origin"]["kind"] == "generated" and sample["origin"]["evidence"][0]["quote"]
    assert client.get(f"/api/generate/{bid}").status_code == 404                # the batch is gone once approved
    assert client.post(f"/api/generate/{bid}/approve", json={}).status_code == 404


def test_approving_only_some_items_discards_the_rest(make_client):
    client = make_client()
    batch = wait(client, upload(client, [TXT], per_category=2, categories='["direct"]').json()["batch_id"])
    first = batch["items"][0]["item_id"]
    done = client.post(f"/api/generate/{batch['batch_id']}/approve", json={"item_ids": [first]}).json()
    assert done["items"] == 1 and done["discarded"] == 1 and len(client.get("/api/test-cases").json()) == 1
    assert client.get("/api/generate").json() == []


def test_questions_are_saved_as_they_are_written_so_a_dropped_connection_loses_nothing(make_client):
    gate = threading.Event()
    client = make_client(llm=FakeLLM(hold=gate))
    bid = upload(client, [TXT], per_category=2).json()["batch_id"]
    time.sleep(0.2)
    running = client.get(f"/api/generate/{bid}").json()
    assert running["status"] == "running" and running["total_tasks"] == 8 and running["items"] == []
    assert upload(client, [TXT]).status_code == 409                                 # one at a time
    gate.set()
    batch = wait(client, bid)
    assert len(batch["items"]) == 8
    # the batch is on the server, not in the browser: a fresh listing (new tab) still finds it
    listed = client.get("/api/generate").json()
    assert listed[0]["batch_id"] == bid and listed[0]["item_count"] == 8 and listed[0]["case_count"] == 12


def test_cancelling_keeps_what_was_already_written(make_client):
    gate = threading.Event()
    client = make_client(llm=FakeLLM(hold=gate), generate_workers=1)
    bid = upload(client, [TXT], per_category=3).json()["batch_id"]
    time.sleep(0.2)
    assert client.post(f"/api/generate/{bid}/cancel").status_code == 202
    gate.set()
    batch = wait(client, bid)
    assert batch["status"] == "cancelled" and len(batch["items"]) < 12
    assert client.delete(f"/api/generate/{bid}").status_code == 200                 # once stopped, it can be discarded
    assert client.get(f"/api/generate/{bid}").status_code == 404


def test_discarding_while_still_writing_asks_it_to_stop_instead(make_client):
    gate = threading.Event()
    client = make_client(llm=FakeLLM(hold=gate), generate_workers=1)
    bid = upload(client, [TXT], per_category=3).json()["batch_id"]
    time.sleep(0.2)
    assert client.delete(f"/api/generate/{bid}").status_code == 409
    gate.set()
    assert wait(client, bid)["status"] == "cancelled"


def test_a_restart_marks_unfinished_batches_but_keeps_their_items(make_client):
    client = make_client()
    store = client.app.state.store
    store.save_batch({"batch_id": "old", "status": "running", "created_at": "2026-01-01T00:00:00+00:00",
                      "expires_at": "2999-01-01T00:00:00+00:00", "items": [{"item_id": "x", "category": "direct", "turns": [{}]}]})
    from ragevalkit.generator import GenerationManager
    GenerationManager(client.app.state.config, store, llm=FakeLLM())
    assert store.get_batch("old")["status"] == "interrupted" and len(store.get_batch("old")["items"]) == 1


def test_unapproved_batches_are_deleted_after_their_time_is_up(make_client):
    client = make_client()
    store = client.app.state.store
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    store.save_batch({"batch_id": "stale", "status": "ready", "created_at": past, "expires_at": past, "items": []})
    store.save_batch({"batch_id": "busy", "status": "running", "created_at": past, "expires_at": past, "items": []})
    assert [b["batch_id"] for b in client.get("/api/generate").json()] == ["busy"]     # expired one is gone, running one is not
    assert client.get("/api/generate/stale").status_code == 404


def test_limits_and_unreadable_uploads_are_reported_clearly(make_client):
    client = make_client(generate_max_file_mb=1, generate_max_files=2)
    assert upload(client, [TXT, MD, ("c.txt", b"x" * 500, "text/plain")]).status_code == 422
    big = ("big.txt", b"a" * (2 * 1024 * 1024), "text/plain")
    too_big = upload(client, [big])
    assert too_big.status_code == 413 and "1 MB" in too_big.json()["detail"]
    wrong = upload(client, [("deck.pptx", b"zzz", "application/octet-stream")])
    assert wrong.status_code == 422 and "unsupported file type" in wrong.json()["detail"]
    assert upload(client, [TXT], per_category=0).status_code == 422
    assert upload(client, [TXT], categories="[]").status_code == 422

    scanned = ("scan.pdf", make_pdf([""]), "application/pdf")
    batch = wait(client, upload(client, [scanned]).json()["batch_id"])
    assert batch["status"] == "failed" and "no selectable text" in batch["error"]
    assert "limits" in client.get("/api/generate/limits").text or client.get("/api/generate/limits").json()["max_files"] == 2


def test_one_unreadable_file_does_not_stop_the_others(make_client):
    client = make_client()
    scanned = ("scan.pdf", make_pdf([""]), "application/pdf")
    batch = wait(client, upload(client, [scanned, TXT], per_category=1).json()["batch_id"])
    assert batch["status"] == "ready" and len(batch["items"]) == 4
    assert "no selectable text" in next(f for f in batch["files"] if f["name"] == "scan.pdf")["error"]


def test_model_failures_are_reported_per_question_and_do_not_lose_the_rest(make_client):
    client = make_client(llm=FakeLLM(fail_first=1000))
    client.app.state.generator._sleep = lambda s: None          # do not really wait between retries
    batch = wait(client, upload(client, [TXT], per_category=1).json()["batch_id"])
    assert batch["status"] == "failed" and batch["items"] == [] and "could not be reached" in batch["error"]
    assert len(batch["errors"]) == 4



def test_generated_chat_ids_are_short_and_carry_on_across_approvals(make_client):
    client = make_client()
    first = wait(client, upload(client, [TXT], per_category=2, turns=2).json()["batch_id"])
    client.post(f"/api/generate/{first['batch_id']}/approve", json={})
    cases = client.get("/api/test-cases").json()
    chats = sorted({c["chat_id"] for c in cases})
    assert chats == ["direct-1", "direct-2", "indirect-1", "indirect-2", "multipart-1", "multipart-2", "multiturn-1", "multiturn-2"]
    assert {c["chat_id"] for c in cases if c["origin"]["category"] == "multiturn"} == {"multiturn-1", "multiturn-2"}
    assert sorted(c["turn_no"] for c in cases if c["chat_id"] == "multiturn-1") == [1, 2]      # one chat, both turns

    # a second approval continues the numbering
    second = wait(client, upload(client, [TXT], per_category=1, turns=2).json()["batch_id"])
    client.post(f"/api/generate/{second['batch_id']}/approve", json={})
    everything = {c["chat_id"] for c in client.get("/api/test-cases").json()}
    assert everything - set(chats) == {"direct-3", "indirect-3", "multipart-3", "multiturn-3"}
