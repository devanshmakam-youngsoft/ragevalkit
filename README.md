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

### 2. Record test cases

Use the `Recorder` to capture real conversations from your RAG app and save them as test cases:

```python
from ragevalkit import Recorder

recorder = Recorder(store_path="eval_store.json")

recorder.record(
    chat_id="session_001",
    turn_no=1,
    question="What is the admission deadline?",
    expected_answer="The admission deadline is March 31.",
    generated_answer=your_rag_response,
    retrieved_context=your_rag_context,
    sources=["doc_1.pdf"],
)
```

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

## Versioning

When you release a new version of your RAG app, run the evaluator against the same test cases and give it a new version name (e.g. `v2`). The dashboard tracks all versions so you can compare quality over time.
