"""Reading test cases from a spreadsheet, paste or CSV — forgivingly, but never silently.

The importer works in two stages so the dashboard can show a preview before anything is saved:

1. ``read_table`` + ``detect_mapping`` find the data and work out which column is which (by common
   names, the developer's ``column_map``, or a choice made in the dialog).
2. ``parse_rows`` turns the table into clean rows and, for every row it cannot use, says which row
   and why. Nothing is quietly "fixed": a turn of "abc" is a problem, not a 1.

What happens to the clean rows (new / updated / unchanged) is decided by ``EvalStore.import_cases``,
which uses the same code for the preview (``dry_run=True``) and the real import, so they never disagree.
"""
from ragevalkit.services.testcase_import.fields import (
    ALIASES,
    FIELD_LABELS,
    FIELDS,
    MAX_BYTES,
    MAX_ROWS,
)
from ragevalkit.services.testcase_import.import_workflow import (
    preview_import,
    read_upload,
    run_import,
)
from ragevalkit.services.testcase_import.row_parser import Problem, parse_rows, split_labels
from ragevalkit.services.testcase_import.table_reader import (
    SUPPORTED_SUFFIXES,
    clean_mapping,
    detect_mapping,
    read_table,
)
from ragevalkit.services.testcase_import.template import template_workbook

__all__ = [
    "ALIASES", "FIELDS", "FIELD_LABELS", "MAX_BYTES", "MAX_ROWS", "Problem", "SUPPORTED_SUFFIXES",
    "clean_mapping", "detect_mapping", "parse_rows", "preview_import", "read_table", "read_upload",
    "run_import", "split_labels", "template_workbook"
]
