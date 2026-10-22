# ragevalkit

A generic RAG / LLM evaluation toolkit with a FastAPI backend and React dashboard.

- Run scored evaluation versions of your RAG pipeline
- Manage test case groups (many-to-many)
- Multi-group run selection with run notes
- Dashboard: quality trend, score distribution, per-version detail
- Excel export with full results and summary sheet
- HMAC session auth with optional login requirement
- TinyDB persistence — zero setup, single JSON file

---

## Installation

**From GitHub (recommended):**

```bash
pip install git+https://github.com/devanshmakam-youngsoft/ragevalkit.git@v0.1.0
```

**In `requirements.txt`:**

```
git+https://github.com/devanshmakam-youngsoft/ragevalkit.git@v0.1.0
```

Then install with:

```bash
pip install -r requirements.txt
```

> **Note:** Run this from **Git Bash** (not PowerShell) if `git` is not in your PowerShell PATH.

---

## Quick Start

### 1. Start the evaluation server

```python
from ragevalkit import serve

serve(
    host="your-rag-api-host",   # base URL of your RAG API e.g. "http://localhost:8000"
    port=8002,
    store_path="eval_store.json",
)
```

This starts the dashboard at `http://localhost:8002`.

### 2. Add test cases

Populate your test case library through the dashboard — upload an Excel/CSV file in the **Library** tab, create individual cases manually, or import programmatically via the REST API (`POST /api/test-cases`).

Each test case needs: `chat_id`, `turn_no`, `type`, `question`, `expected_answer`. Add an optional `expected_sources` column to enable source verification (see [Source Verification](#source-verification)).

### 3. Run an evaluation

From the dashboard, open the **Execute** modal, select a version name and test case groups, add an optional note, and click **Run**. The evaluator calls your RAG API for each test case, scores answers with an LLM judge, and computes lexical metrics.

### 4. View results

The dashboard shows all versions with average scores, quality trend, and node timings. Click a version to see per-question breakdowns filtered by score tier (High / Mid / Low). Download a full Excel report from the version detail page.

---

## Configuration

`serve()` accepts:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `host` | required | Base URL of your RAG API |
| `port` | `8002` | Port for the eval server |
| `store_path` | `"eval_store.json"` | TinyDB file path |
| `require_login` | `False` | Enable login page |
| `users` | `None` | `"user:password"` or list of them |
| `judge_model` | `"gpt-4o"` | LiteLLM model string for the judge |
| `rag_chat_path` | `"/api/chat"` | Chat endpoint on your RAG API |

---

## Test cases and groups

Test cases are the unit of the library. A **group** is just a label you put on test cases: one case can carry any number of labels, and you can add or remove them from the Test Cases page (tick rows → *Add to group…*) or from a case's detail panel.

You can run:

- one or more **groups** (a case that is in several selected groups runs once), or
- any **hand-picked test cases** — tick rows on the Test Cases page and choose *Run*, or use *Pick test cases* in the Execute dialog.

Follow-up questions need the turns before them, so by default a run also includes the earlier turns of each selected case's conversation; the Execute dialog shows exactly how many cases will run and lets you turn this off. Chat ID and turn number can be edited on any test case.

**Deleting a test case is permanent** (all its versions and group labels are removed; results of past runs keep their own copy of the question). To take a case out of runs without losing it, mark it *inactive*.

## Which version should ship?

The dashboard's recommendation is computed by the server (`GET /api/recommendation`) every time from the saved scores of every run that is **not archived** — archive or delete a version and the recommendation, trend charts, deltas and group history update straight away. Quality is `answer_weight` / `material_weight` from `serve()` (default 60/40); speed only breaks near-ties. Runs are only compared when they covered the same number of questions, had no failed rows and were not stopped early. If material marks were not graded for every compared version, all versions are compared on answer marks alone and the dashboard says so.

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

then copy `dist/*` into `ragevalkit/static/` (replace the old files). Backend tests: `pip install -e .[dev]` then `pytest`.
