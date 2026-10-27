# ragevalkit

Evaluate any RAG pipeline, chatbot or agent. You give ragevalkit a Python function; it replays your test questions through it, scores every answer with an AI judge and text metrics, and shows the versions of your pipeline side by side in a dashboard.

- Score each version: answer quality, context quality, response time, and how long each step takes
- A test case library: groups (labels), bulk import from Excel/CSV, and test cases written from your own documents
- A recommendation of which version to ship, computed on the test cases the versions share
- Plain-language findings for every run: each watch-out paired with what to do about it
- Excel export, optional login, and one JSON file for storage (TinyDB), so there is nothing to set up

**More:** [docs/guide.html](docs/guide.html) is the full reference; [docs/how-ragevalkit-works.html](docs/how-ragevalkit-works.html) explains how it works inside, file by file.

---

## Installation

```bash
pip install git+https://github.com/devanshmakam-youngsoft/ragevalkit.git
```

To pin a release, add a tag, for example `@v0.1.3` (tags: `v0.1.0` to `v0.1.3`). Features described below that are newer than that tag (document-based test case generation, bulk import, the paired findings) are on `main` until the next tag is made.

In `requirements.txt`:

```
git+https://github.com/devanshmakam-youngsoft/ragevalkit.git
```

> **Windows:** run `pip install` from **Git Bash** if `git` is not in your PowerShell PATH.

**Dependencies are pinned for safety.** `litellm` is held to `>=1.104,<1.107`: version 1.107.0 (21 Oct 2026) and 1.82.7/1.82.8 (Mar 2026) were published with credential-stealing malware. Raise the upper bound only after checking that a newer release is clean.

---

## Quick Start

### 1. Start the evaluation server

`serve()` takes **your pipeline function**. Anything that turns a question into an answer works:

```python
import ragevalkit

def my_rag(question: str) -> str:
    return pipeline.run(question)

ragevalkit.serve(my_rag, port=8002, require_login=False)
```

The dashboard opens at `http://localhost:8002` (the default port is `8001`). A `.env` file next to your script is read, so `GROQ_API_KEY`, `OPENAI_API_KEY` and the like are picked up for the judge.

Your function can also take history or a session id, return a dict, or be `async`; ragevalkit adapts to its parameter names (see the guide). To show what happens *inside* the pipeline, mark its steps:

```python
@ragevalkit.step("retrieval")
def retrieve(query):
    return vector_db.search(query)

with ragevalkit.step("llm") as s:
    answer = llm.generate(query, docs)
    s.material = docs          # what the answer was based on: this is what "context quality" scores
    s.sources = ["policy.pdf"] # which documents were used: checked against expected_sources
```

### 2. Add test cases

Open **Test Cases**. You can add one case with **+ New test case**, bring many in with **Import** (Excel/CSV or pasted rows), or write them from your documents with **Generate from documents**. Only the question is required for an import; each case has a `chat_id`, `turn_no`, `type`, `question`, `expected_answer` and an optional `expected_sources` (see [Source Verification](#source-verification)).

### 3. Run an evaluation

Click **Execute session**, name the version, pick groups and/or individual test cases, add an optional note, and run. For each test case ragevalkit calls your function, scores the answer with the judge, and computes text metrics.

### 4. Read the results

The **Dashboard** shows every version with its average scores and a recommendation. Open a version for the score distribution, the timing of each step, watch-outs with suggestions, and every question's answer. Download an Excel report from the version page.

---

## Configuration

The most used `serve()` parameters (the full list, with every default, is in the `serve()` docstring and `docs/guide.html`):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `fn` | required | Your pipeline function |
| `port` | `8001` | Port for the dashboard |
| `store_path` | `"eval_store.json"` | TinyDB file that holds everything |
| `require_login` | `True` | Show the login page; `False` lets anyone in as a guest |
| `users` | `"admin:admin123"` | `"user:password"` pairs, comma separated |
| `judge_model` | `"groq/openai/gpt-oss-120b"` | Any LiteLLM model string for the judge |
| `judge_api_key` | `None` | Otherwise LiteLLM reads the provider's environment variable |
| `generator_model` | `None` | Model that writes test cases from documents; defaults to `judge_model` |
| `answer_weight` / `material_weight` | `0.6` / `0.4` | How the recommendation weighs answer and context quality |
| `recommendation_tolerance` | `0.25` | Versions this close to the best count as tied; the fastest wins |
| `max_response_time` | `None` | Leave out versions slower than this (seconds) when recommending |
| `source_check_mode` | `"keyword"` | `"keyword"`, `"llm"` or `"off"` |
| `summary_prompt` | `None` | Changes what the AI-written findings look for |
| `eval_env` | `"dev"` | `"prod"` turns the dashboard and every eval route off |

---

## Test cases and groups

Test cases are the unit of the library. A **group** is just a label you put on test cases: one case can carry any number of labels, and you can add or remove them from the Test Cases page (tick rows → *Add to group…*) or from a case's detail panel.

You can run:

- one or more **groups** (a case that is in several selected groups runs once), or
- any **hand-picked test cases** — tick rows on the Test Cases page and choose *Run*, or use *Pick test cases* in the Execute dialog.

Follow-up questions need the turns before them, so by default a run also includes the earlier turns of each selected case's conversation; the Execute dialog shows exactly how many cases will run and lets you turn this off. Chat ID and turn number can be edited on any test case.

**Deleting a test case removes it for good**, with all its versions and group labels. Past versions keep their own copy of the question and the answer, and mark that row *Test case deleted*. **Deleting a group** only hides it (its labels stay, so past versions still read correctly); open *Deleted groups* on the Groups page to restore or remove one. Deleting a **version** removes it and its results from the store for good. To take a test case out of runs without deleting it, mark it *inactive*.

## Generating test cases from documents

**Test Cases → Generate from documents** writes test cases from your own documents (PDF, Word `.docx`, TXT or Markdown; up to 5 files, 50 MB each). By default it writes 3 questions in each of four categories and puts them in a group per category:

| Category | What it is |
|---|---|
| **Direct** | The answer is stated plainly in one place. |
| **Indirect** | The answer is in the document, but the question uses everyday words or describes a situation rather than the document's own wording. |
| **Multi-part** | One question with several parts, answered from different places in the document. |
| **Multi-turn** | A short conversation (3 turns by default). Each follow-up is what a person would type *next* ("and what happens if I miss that?"): it refers back to the earlier answer and cannot be understood alone. Every follow-up records what it builds on, shown during review. |

- **Type.** Every generated test case has the type `rag` (its answer has to come from the documents); the category is the group it is in.
- **Questions per category** is shared across the files you upload; change it (1–10) and which categories to write in the dialog.
- **Every answer comes with evidence.** The writer sees each passage as numbered sentences and cites the sentences that prove its answer; ragevalkit stores the document's own wording of them, with file and page, so evidence can never be invented. A question whose evidence does not point at real sentences is rejected and rewritten, and a rejected conversation is sent back naming the turn that failed. Evidence is shown during review and later on the test case ("Written from your document"), and the file name becomes the case's `expected_sources`.
- **Saved as it goes, approved by you.** Questions are saved on the server while they are being written, so closing the browser or losing the network loses nothing; a banner on the Test Cases page brings you back. They only become test cases when you press *Add*; you can edit or remove any of them first. Anything not added within 24 hours (`batch_ttl_hours`) is deleted.
- **Nothing of the upload is kept** — only the questions, answers and evidence snippets.
- **Which model writes them:** `serve(generator_model=...)`, defaulting to `judge_model`. The text of your documents is sent to that model, so pick one you are allowed to send them to (a local `ollama/...` model works). Scanned PDFs (no selectable text), password-protected files and old `.doc` files are reported with a clear message (save `.doc` as `.docx`).

## Test case types: rag and non-rag

Each test case has a type. **`rag`** (the default) means the answer has to come from your documents, so the retrieved material is scored too. **`non-rag`** is for greetings, small talk and anything else where no retrieval is expected: it is graded on the answer only, like the `conversational` type. Older values such as `query` keep working and count as rag. Pick the type in the test case form, in a `type` column when importing, or leave it blank for `rag`.

## Importing test cases in bulk

**Test Cases → Import** takes an Excel or CSV file, or rows pasted from a spreadsheet, in three steps: pick the file, check what will happen, then choose where the cases go. Nothing is saved until the last step.

- **Check first.** You see how many rows are new, will be updated, are already there, or can't be imported — with the row number and reason for each one that can't — before anything is saved. Nothing is silently corrected: a turn of "abc" is reported, not turned into 1.
- **Only the question column is required.** Without a chat column every question becomes its own chat; without a turn column turns are numbered in file order within each chat. Common header names (`query`, `gold_answer`, `tags`…) are recognised, and the dialog lets you point any column at the right field.
- **Groups are optional.** The default is *No group*. Pick existing groups or a new one for the whole file, and/or add a `groups` column (`Billing; Refunds`) to label rows individually — missing groups are created.
- **Safe to repeat.** Importing the same file again changes nothing; an edited answer becomes a new version of the existing case. If a row has the same chat and turn as an existing case but a different question you can add it as a new case or update the existing one.
- **Fix and re-import.** The rows that couldn't be imported can be downloaded with the reason next to each. A template (with a short guide) is available in the dialog.

## Which version should ship?

The dashboard's recommendation is computed by the server (`GET /api/recommendation`) every time, from the saved scores of every run that is **not archived** — archive or delete a version and the recommendation, trend charts, deltas and group history update straight away.

**Versions are compared on the test cases they share.** Each run saves its score for every test case, so adding a test case (or running an extra group) in a later version no longer hides it: it is judged on the cases the others also ran, and the dashboard says so ("Compared on the 10 test cases every compared version ran; v4 ran 20"). A case only counts as the same if its question and expected answer are unchanged. If the shared cases are only a thin slice (fewer than half of a typical version's cases, e.g. a 2-question smoke test next to 10-question runs) that version is left out and the reason is shown. Versions that were stopped early, or failed on a shared case, are left out too. The *overall score* is answer quality and context quality weighted by `answer_weight` / `material_weight` from `serve()` (default 60/40); versions within the tie tolerance of the best are tied and the fastest wins. If context quality was not graded for every compared version, all are compared on answer quality alone and the dashboard says so. Changes (the ± figures) and BEST marks use the same shared cases.

Each run's summary also has *Watch-outs & suggestions*: AI-written findings, each pairing one thing that needs attention with the next step that answers it (it does not repeat the headline scores). The reply is checked: a finding without its suggestion is sent back to the model, and if one is still missing it is filled in from the run's own numbers. `serve(summary_prompt=...)` changes what it looks for; the JSON reply format is added automatically.

Each run also saves a detailed `scores` block (score tiers, per-question-type averages, response-time spread, source-check results) on its summary.

---

## Source Verification

Add an `expected_sources` column to your dataset to track which documents the RAG should retrieve.

### Format

| Separator | Meaning | Example |
|-----------|---------|---------|
| `\|` | AND — every group must be retrieved | `doc_a.pdf \| doc_b.pdf` |
| `,` | OR — any one alternative satisfies the group | `doc_a.pdf , doc_a_v2.pdf` |

Combined: `doc_a.pdf , doc_a_v2.pdf | policy_2025.pdf`  
→ (doc_a.pdf **or** doc_a_v2.pdf) **and** policy_2025.pdf must both be retrieved.

Single-source rows (`doc_a.pdf`) work as before.

### Modes

Control the check with `source_check_mode` in `serve()`:

| Mode | Behaviour |
|------|-----------|
| `"keyword"` | Fast substring match — case-insensitive, ignores path prefix and extension (default) |
| `"llm"` | LLM judge call — understands capitalisation/extension differences; strict about year/version differences; adds `source_score` (0–10) and `source_comment` to results |
| `"off"` | Skip source verification entirely |

```python
serve(..., source_check_mode="llm")
```

Results always include `matched_sources`, `missing_sources`, and `source_match` (True only when every required group was retrieved).

---

## Versioning

When you release a new version of your RAG app, run the evaluator against the same test cases and give it a new version name (e.g. `v2`). The dashboard tracks all versions so you can compare quality over time.

---

## Development

The dashboard source lives in `ragevalkit/frontend/` (React + Vite). To rebuild it:

```bash
cd ragevalkit/frontend
npm ci
npm run build
```

then copy `dist/*` into `ragevalkit/static/` (replace the old files; the dashboard is served from there). Backend tests: `pip install -e .[dev]` then `pytest`.
