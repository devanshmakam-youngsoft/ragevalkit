"""Which version should ship, and how has a group done over time?

Everything here is computed on every request from the scores saved on each run, over the runs that
are *not archived* — so archiving or deleting a version changes the answer straight away, and nothing
about a recommendation is ever saved that could go stale.

HOW VERSIONS ARE COMPARED
-------------------------
Averages are only fair when versions answered the same questions. Each run saves its score for every
test case (``case_scores``), so versions are compared **on the test cases they share**:

1. Take the test cases every compared version ran (a case counts as the same only if its chat, turn,
   question and expected answer are unchanged). Adding a test case, or running an extra group, in a
   later version therefore no longer hides that version: it is judged on the cases the others also ran.
2. If the shared cases are only a thin slice (fewer than half of a typical version's cases — say a
   2-question smoke test next to 10-question runs), the version that shares least is left out and
   reported as not compared, instead of letting it shrink everyone's comparison.
3. Versions that were stopped early, or had a failure on a shared case, are left out.
4. Each remaining version is scored on the shared cases only: *overall score* = answer quality and
   context quality weighted by ``serve()`` (default 60/40). Context quality only counts when every
   compared version has it; otherwise all are compared on answer quality alone, and the result says so.
5. Versions within ``tolerance`` of the best overall score are tied; the fastest of them is recommended.

Runs saved before per-case scores existed are filled in from their saved results the first time they
are needed (see ``EvalStore.list_versions_for_comparison``). If a run has none at all, the older
whole-run comparison (same number of questions) is used instead.
"""
from ragevalkit.recommendation.constants import DEFAULT_ANSWER_WEIGHT, DEFAULT_MATERIAL_WEIGHT, DEFAULT_TOLERANCE
from ragevalkit.recommendation.engine import recommend
from ragevalkit.recommendation.group_overview import group_overview

__all__ = ["DEFAULT_ANSWER_WEIGHT", "DEFAULT_MATERIAL_WEIGHT", "DEFAULT_TOLERANCE", "group_overview", "recommend"]
