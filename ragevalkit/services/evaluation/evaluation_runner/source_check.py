"""Checking that the documents your pipeline retrieved are the ones the test case expects."""


def parse_source_groups(expected: str) -> list[list[str]]:
    """Parse an ``expected_sources`` cell into AND-groups of OR-alternatives.

    ``"a.pdf , a_v2.pdf | b.pdf"`` -> ``[["a.pdf", "a_v2.pdf"], ["b.pdf"]]``:
    groups are separated by ``|`` (all must be retrieved), alternatives within a
    group by ``,`` (any one satisfies the group). Empty groups are dropped.
    """
    groups = []
    for group in (expected or "").split("|"):
        alternatives = [a.strip() for a in group.split(",") if a.strip()]
        if alternatives:
            groups.append(alternatives)
    return groups


def check_sources_by_keyword(expected_str: str, recorded: list) -> dict:
    """Compare expected_sources against recorded sources.

    Format: groups separated by | (ALL must pass);
            alternatives within a group separated by , (ANY ONE satisfies the group).

    Example: "1.txt , 2.txt | 3.txt"
      Group 1: 1.txt OR 2.txt must be retrieved (any one is enough)
      Group 2: 3.txt must be retrieved
      Both groups must pass for source_match = True.

    Single-level usage (no commas) is identical to the old pipe-only format.
    """
    groups = parse_source_groups(expected_str)
    if not groups:
        return {"source_match": None, "matched_sources": [], "missing_sources": []}
    recorded_lower = [str(s).lower() for s in (recorded or [])]
    matched_sources: list[str] = []
    missing_sources: list[str] = []
    for alternatives in groups:
        hit = next(
            (alt for alt in alternatives
             if any(alt.lower() in r or r in alt.lower() for r in recorded_lower)),
            None,
        )
        if hit:
            matched_sources.append(hit)
        else:
            missing_sources.append(" , ".join(alternatives))
    return {
        "source_match": len(missing_sources) == 0,
        "matched_sources": matched_sources,
        "missing_sources": missing_sources,
    }
