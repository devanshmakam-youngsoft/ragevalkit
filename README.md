# RAG-Eval — UWI Regulations Chatbot

Conversational RAG over the UWI regulation PDFs in `data/input/`.
FastAPI + LangGraph + LangChain + FAISS + Groq (`ChatGroq`, `openai/gpt-oss-20b`) with local
HuggingFace embeddings (`all-MiniLM-L6-v2`), and a Streamlit chat UI.

## Layout
```
rag/backend/   FastAPI app (port 8000): config, routes, LangGraph graph, FAISS, session store
rag/frontend/  Streamlit UI (port 8001): login, chat, past sessions
rag/tests/     pytest suite
data/input/            source PDFs
data/output/chats/{user_id}/{uuid}_session.json   saved conversations (gitignored)
data/output/faiss_index/                          vector index (gitignored, built on first start)
tests/
```

## Pipeline
`router → (rag | replier) → summarize-if-needed`
- Questions about UWI documents are answered from FAISS-retrieved context (with sources);
  anything else gets a polite "I'm here to help with questions related to UWI" reply.
- In-memory conversation memory per session (LangGraph `MemorySaver`). When history exceeds
  `max_history_messages` (11, incl. system prompt) it is summarised and replaced by
  `[system prompt, summary as human message]`. The JSON file always keeps the full history.
- Session JSON keys: `messages`, `summary`, `date_created`, `session_title` (+ ids).

## Run
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r rag/backend/requirements.txt -r rag/frontend/requirements.txt
# .env must contain GROQ_API_KEY=...
.venv/Scripts/python rag/backend/run.py                    # http://localhost:8000 (first start builds the index)
.venv/Scripts/python -m streamlit run rag/frontend/app.py --server.port 8001  # http://localhost:8001
```
Demo logins (`rag/frontend/users.py`): alice/alice123 (id 1), bob/bob123 (id 2), carol/carol123 (id 3).

## Configuration
All tunables live in `rag/backend/app/config.py` (`Config`) and can be overridden via env/.env:
model, temperature, embedding model, chunk size/overlap, `top_k`, `max_history_messages`, paths, ports.
Delete `data/output/faiss_index/` to force a re-index.

## API
`GET /health` · `POST /api/chat {user_id, message, session_id?}` ·
`GET /api/sessions/{user_id}` · `GET /api/sessions/{user_id}/{session_id}`

## Tests
`python -m pytest`

---

# Evaluator (`eval/`)

LLM-as-judge evaluation of the RAG app, with a React dashboard.

```
eval/backend/   FastAPI (port 8002): dataset loading, runner (background + SSE), judge, lexical metrics, xlsx results
ragevalkit/frontend/  React + Vite + Tailwind + Recharts (port 8003): dashboard, execute modal, version detail
                (Paper & Ink theme in src/ui/theme.css; light/dark toggle top-right, follows the OS by default)
data/input/eval/eval_input.xlsx             default dataset (sheet "dataset": chat_id, turn_no, type, question, expected_answer)
data/output/eval_results/version_{n}_results.xlsx   sheets: summary, results
```

**How a run works:** for each row (sorted by chat_id, turn_no; one RAG session per chat_id so follow-ups keep context)
the evaluator calls the RAG `/api/chat`, then
- `gpt-oss-120b` judges `answer_marks` (vs. expected answer) and `material_marks` (is the retrieved material enough?).
  Material marks are N/A (excluded from averages) for `conversational` rows.
- keyword recall, BM25 and embedding cosine similarity between expected and generated answer (non-conversational rows)
- per-node timings: whatever nodes the RAG app reports (`query_decider`, `query_rewriter`, `retriever`, `answer_generator`, `replier`, `summarizer`, ...).
  Nodes are not hardcoded, so adding or removing a node in the RAG graph needs no evaluator change; older versions simply have no value for a new node.

At the end a 3-4 sentence LLM comment is added to the `summary` sheet. The dashboard lists every version (v1, v2, ...)
with averages, node timings, comment and date; a running version shows as "In progress" with live progress (SSE).

**Recommendation:** the dashboard opens with a recommended version: quality = 60% answer + 40% material marks, versions within a
tolerance (default 0.25) count as tied and the faster one wins, an optional max response time filters candidates, and versions with
failed rows or a different question-set size are left out. Logic and tests: `ragevalkit/frontend/src/recommend.ts`,
`node --test src/recommend.test.ts` (from `ragevalkit/frontend`).

**Run** (RAG backend on :8000 must be up):
```bash
.venv/Scripts/python eval/backend/run.py        # http://localhost:8002
cd ragevalkit/frontend && npm install && npm run dev  # http://localhost:8003
```
Config: `eval/backend/app/config.py` (judge model, RAG URL, paths, ports). Tests: `python -m pytest eval/tests`
(run `rag/tests` and `eval/tests` separately; both define an `app` package).

---

# Deployment

`deploy/` holds a Docker Compose setup with two public routes: `/rag-eval` (evaluator frontend, API under `/rag-eval/api`)
and `/charon/dolly` (RAG chat, API under `/charon/dolly/api`). The evaluator has a login page (users from `EVAL_USERS`).
See [deploy/README.md](deploy/README.md) for the port map, run/update commands and gateway checks.
