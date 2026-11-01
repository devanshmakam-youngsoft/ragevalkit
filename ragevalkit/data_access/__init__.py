"""TinyDB-backed persistence.

FOUR-TABLE DESIGN
-----------------
  runs        — one document per version (summary stats + AI findings)
  receipts    — one document per question per version (the raw grade + metrics)
  test_cases  — one document per version of each test case (stable tc_id + version counter)
  groups, group_members, gen_batches, datasets — labels, which cases carry them, review batches, legacy uploads

WHY two eval tables (runs + receipts)?
  The dashboard's list view only needs the `runs` table (fast, small).
  Loading all receipts for every version on every page load would be slow.
  The detail view / download hits `receipts` only when the user asks.

WHY a test_cases table?
  Gives every question a stable tc_id that survives across re-imports.
  Each edit creates a new version record (the old one stays for history).
  Eval receipts reference tc_id so you can join eval results with the test case
  that was active at the time.

WHY TinyDB (not SQLite)?
  Zero setup — a single JSON file the developer can open in any text editor,
  commit to git, or copy between machines. No schema migrations needed.
  The lock is a plain threading.Lock because TinyDB is not thread-safe by
  itself and the runner writes from a background thread while FastAPI reads.

LAYOUT
------
  store.py                  EvalStore, assembled from the repositories below
  base.py                   opens the file; the tables and the lock
  evaluation_runs.py        versions and their receipts
  testcases.py              test cases, and choosing what a run executes
  testcase_import.py        bulk import of test cases
  testcase_groups.py        groups (labels)
  generated_batches.py      generated questions waiting for approval
  datasets.py               older uploaded datasets
  records.py                small helpers for the stored records
"""
from ragevalkit.core.exceptions.data_access import (
    ConflictError,
    GroupNotFound,
    StoreError,
    VersionNotFound,
)
from ragevalkit.data_access.store import EvalStore
from ragevalkit.schemas.internal.run_selection import RunSelection
from ragevalkit.utils.version_names import valid_version

__all__ = ["ConflictError", "EvalStore", "GroupNotFound", "RunSelection", "StoreError", "VersionNotFound", "valid_version"]
