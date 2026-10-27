"""expected_sources: '|' = every group required, ',' = any alternative within a group."""
from types import SimpleNamespace

import pytest

from ragevalkit.evaluation.source_check import check_sources_by_keyword, parse_source_groups
from ragevalkit.judging.judge import Judge


def test_parse_groups():
    assert parse_source_groups("a.pdf , a_v2.pdf | b.pdf") == [["a.pdf", "a_v2.pdf"], ["b.pdf"]]
    assert parse_source_groups(" | , ") == []
    assert parse_source_groups("") == []


def test_keyword_mode_needs_every_group():
    hit = check_sources_by_keyword("a.pdf , a_v2.pdf | b.pdf", ["docs/A_V2.pdf", "b.pdf"])
    assert hit["source_match"] is True and hit["matched_sources"] == ["a_v2.pdf", "b.pdf"]
    partial = check_sources_by_keyword("a.pdf , a_v2.pdf | b.pdf", ["docs/A_V2.pdf"])
    assert partial["source_match"] is False and partial["missing_sources"] == ["b.pdf"]


@pytest.mark.parametrize("llm_matched, match, score", [
    (["A_v2.pdf"], False, 5),                # only the first group satisfied
    (["a.pdf", "b.pdf"], True, 10),
    ([], False, 0),
])
def test_llm_mode_applies_group_logic_in_code(llm_matched, match, score):
    judge = Judge(SimpleNamespace(judge_prompt_override="", judge_retries=1))
    import json
    judge._call = lambda messages, json_mode=False: json.dumps(
        {"matched_sources": llm_matched, "source_comment": "c"}
    )
    result = judge.check_sources(parse_source_groups("a.pdf , a_v2.pdf | b.pdf"), ["x"])
    assert result.source_match is match and result.source_score == score
