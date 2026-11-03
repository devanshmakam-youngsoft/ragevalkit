"""The short reasons shown in the Remarks column: cleaned from the judge's reply, filled in from the mark when it gave none."""
import pytest

from ragevalkit.prompts.answer_judge import ANSWER_TAGS, MATERIAL_TAGS, grader_format
from ragevalkit.services.evaluation.answer_judge import (
    Grade,
    add_remark_tags,
    clean_answer_tags,
    clean_material_tags,
    remark_summary,
)


def test_only_known_tags_are_kept_once_each_and_at_most_two():
    assert clean_answer_tags(["wrong", "banana", "wrong", "made_up", "incomplete"]) == ["wrong", "made_up"]
    assert clean_answer_tags("Made-up") == ["made_up"]                 # one word, written loosely
    assert clean_material_tags(None) == [] and clean_material_tags(7) == []


def test_a_grade_with_odd_tags_is_still_a_valid_grade():
    grade = Grade(answer_marks=3, answer_comment="Mostly wrong.", answer_tags=["wrong", "banana"], material_tags="partial")
    assert grade.answer_tags == ["wrong"] and grade.material_tags == ["partial"]
    assert Grade(answer_marks=9, answer_comment="Good.").answer_tags == []     # tags are optional: custom rubrics keep working


@pytest.mark.parametrize("marks, status, expected", [
    (10, "ok", "correct"), (8, "ok", "minor_gaps"), (5, "ok", "partly_correct"), (2, "ok", "wrong"),
    (0, "ok", "wrong"), (0, "generation_failed", "no_answer"),
])
def test_without_tags_from_the_judge_the_answer_mark_gives_one(marks, status, expected):
    described = add_remark_tags({"answer_marks": marks, "status": status, "generated_answer": "some answer"})["answer_tags"]
    assert [t["key"] for t in described] == [expected]


@pytest.mark.parametrize("marks, material, expected", [
    (10, "text", "complete"), (6, "text", "partial"), (2, "text", "key_missing"), (0, "", "empty"), (0, "text", "key_missing"),
])
def test_without_tags_from_the_judge_the_context_mark_gives_one(marks, material, expected):
    described = add_remark_tags({"material_marks": marks, "material": material})["material_tags"]
    assert [t["key"] for t in described] == [expected]


def test_a_row_without_marks_has_no_tags():
    row = add_remark_tags({"status": "grading_failed"})
    assert row["answer_tags"] == [] and row["material_tags"] == []


def test_the_judge_s_own_tags_win_and_come_with_a_label_and_a_tone():
    row = add_remark_tags({"answer_marks": 10, "answer_tags": ["made_up"], "material_marks": 9, "material_tags": ["noisy"]})
    assert row["answer_tags"] == [{"key": "made_up", "label": "Made-up detail", "tone": "bad"}]
    assert row["material_tags"] == [{"key": "noisy", "label": "Too much noise", "tone": "warn"}]


def test_the_excel_remark_is_one_plain_line():
    row = {"answer_marks": 2, "material_marks": 2, "material": "x"}
    assert remark_summary(row) == "Answer: Wrong answer | Context: Key text missing"
    assert remark_summary({}) == ""


def test_the_judge_is_told_every_tag_it_may_use():
    for key in [*ANSWER_TAGS, *MATERIAL_TAGS]:
        assert key in grader_format


def test_a_zero_for_an_empty_answer_is_no_answer():
    described = add_remark_tags({"answer_marks": 0, "status": "ok", "generated_answer": ""})["answer_tags"]
    assert [t["key"] for t in described] == ["no_answer"]
