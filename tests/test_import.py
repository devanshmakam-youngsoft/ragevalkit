"""Bulk import: reading forgivingly, reporting every unusable row, and never saving anything from a preview."""
import io
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ragevalkit.config import Config
from ragevalkit.importing import detect_mapping, parse_rows, split_labels, template_workbook
from ragevalkit.server import create_app
from ragevalkit.store import EvalStore


def table(**cols):
    return pd.DataFrame({k: list(v) for k, v in cols.items()})


def mapped(df):
    return detect_mapping(list(df.columns))


# ---- reading --------------------------------------------------------------------------

def test_common_header_names_are_recognised():
    df = table(Conversation=["a"], Turn=[1], User_Query=["q"], Gold_Answer=["x"], Tags=["g"])
    m = mapped(df)
    assert (m["chat_id"], m["turn_no"], m["question"], m["expected_answer"], m["groups"]) == (
        "Conversation", "Turn", "User_Query", "Gold_Answer", "Tags")


def test_the_developers_column_map_wins():
    m = detect_mapping(["my_q", "my_a"], {"my_q": "question", "my_a": "expected_answer"})
    assert (m["question"], m["expected_answer"]) == ("my_q", "my_a")


def test_a_file_with_only_questions_is_enough():
    df = table(question=["What is A?", "What is B?", "What is A?"])
    rows, problems = parse_rows(df, mapped(df))
    assert [r["turn_no"] for r in rows] == [1, 1]                      # each question is its own one-turn chat
    assert rows[0]["chat_id"] != rows[1]["chat_id"] and rows[0]["type"] == "rag"
    assert len(problems) == 1 and "Same question as row 2" in problems[0].reason


def test_turns_are_numbered_per_chat_when_the_file_has_no_turn_column():
    df = table(chat_id=["a", "a", "b"], question=["q1", "q2", "q3"])
    rows, _ = parse_rows(df, mapped(df))
    assert [(r["chat_id"], r["turn_no"]) for r in rows] == [("a", 1), ("a", 2), ("b", 1)]


@pytest.mark.parametrize("turn, ok", [("2", True), ("2.0", True), ("", True), ("abc", False), ("0", False), ("1.5", False)])
def test_a_wrong_turn_is_reported_not_silently_changed(turn, ok):
    df = table(chat_id=["a"], turn_no=[turn], question=["q"])
    rows, problems = parse_rows(df, mapped(df))
    assert bool(rows) is ok and bool(problems) is (not ok)
    if not ok:
        assert problems[0].row == 2 and "Turn number" in problems[0].reason and problems[0].cells["question"] == "q"


def test_unusable_rows_say_which_row_and_why_and_blank_lines_are_ignored():
    df = table(chat_id=["a", "", "b", "b", ""], question=["q1", "q2", "", "q4", ""], turn_no=["1", "1", "1", "1", ""])
    rows, problems = parse_rows(df, mapped(df))
    assert [r["question"] for r in rows] == ["q1", "q4"]
    assert [(p.row, p.reason) for p in problems] == [(3, "Chat ID is empty"), (4, "Question is empty")]


def test_two_questions_for_one_chat_and_turn_in_a_file_are_a_problem():
    df = table(chat_id=["a", "a"], turn_no=["1", "1"], question=["first", "second"])
    rows, problems = parse_rows(df, mapped(df))
    assert len(rows) == 1 and "already used by row 2" in problems[0].reason


def test_group_labels_are_split_and_deduplicated():
    assert split_labels("Billing; refunds | Billing , FAQ") == ["Billing", "refunds", "FAQ"]
    assert split_labels("") == []


def test_the_template_is_a_valid_workbook_that_imports_cleanly():
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(template_workbook()))
    assert book.sheetnames == ["dataset", "How to fill"]
    df = pd.read_excel(io.BytesIO(template_workbook()), sheet_name="dataset", dtype=str)
    rows, problems = parse_rows(df, mapped(df))
    assert len(rows) == 2 and not problems and rows[0]["groups"] == ["Billing", "Refunds"]


# ---- importing ------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    s = EvalStore(tmp_path / "s.json")
    yield s
    s.close()


def row(n, chat, turn, question, answer="a", groups=(), sources="", type_="rag"):
    return {"row": n, "chat_id": chat, "turn_no": turn, "type": type_, "question": question,
            "expected_answer": answer, "expected_sources": sources, "groups": list(groups)}


def counts(r):
    return (r["new"], r["updated"], r["unchanged"])


def test_a_dry_run_saves_and_creates_nothing_and_matches_the_real_import(store):
    rows = [row(2, "c1", 1, "q1", groups=["Billing"]), row(3, "c2", 1, "q2")]
    preview = store.import_cases(rows, new_group_name="Fresh", dry_run=True)
    assert counts(preview) == (2, 0, 0) and preview["groups_created"] == ["Fresh", "Billing"]
    assert store.list_test_cases() == [] and store.list_groups() == []
    real = store.import_cases(rows, new_group_name="Fresh")
    assert counts(real) == counts(preview) and real["labelled"] == preview["labelled"] == 3
    assert sorted(g["name"] for g in store.list_groups()) == ["Billing", "Fresh"]


def test_importing_without_any_group_leaves_cases_unlabelled(store):
    store.import_cases([row(2, "c1", 1, "q1")])
    assert store.list_test_cases()[0]["groups"] == [] and store.list_groups() == []


def test_importing_twice_changes_nothing_the_second_time(store):
    rows = [row(2, "c1", 1, "q1", groups=["G"]), row(3, "c1", 2, "q2", groups=["G"])]
    store.import_cases(rows)
    again = store.import_cases(rows)
    assert counts(again) == (0, 0, 2) and again["labelled"] == 0
    assert all(len(store.get_test_case_history(c["tc_id"])) == 1 for c in store.list_test_cases())


def test_an_edited_answer_becomes_a_new_version_keeping_status_and_labels(store):
    store.import_cases([row(2, "c1", 1, "q1", answer="old", groups=["G"])])
    tc = store.list_test_cases()[0]["tc_id"]
    store.update_status_bulk([tc], "inactive")
    changed = store.import_cases([row(2, "c1", 1, "q1", answer="new", groups=["G"])])
    assert counts(changed) == (0, 1, 0)
    case = store.list_test_cases()[0]
    assert (case["expected_answer"], case["version"], case["status"]) == ("new", 2, "inactive")


def test_a_deleted_case_is_gone_so_importing_it_again_makes_a_new_one(store):
    store.import_cases([row(2, "c1", 1, "q1", groups=["G"])])
    tc = store.list_test_cases()[0]["tc_id"]
    assert store.delete_test_cases([tc]) == 1 and store.list_test_cases() == []
    result = store.import_cases([row(2, "c1", 1, "q1", answer="changed")])
    case = store.list_test_cases()[0]
    assert counts(result) == (1, 0, 0) and (case["expected_answer"], case["version"], case["groups"]) == ("changed", 1, [])


def test_same_chat_and_turn_with_a_different_question_is_reported_and_added_by_default(store):
    store.import_cases([row(2, "c1", 1, "old question")])
    result = store.import_cases([row(2, "c1", 1, "reworded question")])
    assert result["slot_conflicts"] == 1 and counts(result) == (1, 0, 0)
    assert len(store.list_test_cases()) == 2


def test_update_by_slot_rewrites_the_existing_case_and_stays_idempotent(store):
    store.import_cases([row(2, "c1", 1, "old question", groups=["G"])])
    original = store.list_test_cases()[0]["tc_id"]
    result = store.import_cases([row(2, "c1", 1, "reworded question", answer="b")], update_by_slot=True)
    assert counts(result) == (0, 1, 0) and result["slot_conflicts"] == 1
    cases = store.list_test_cases()
    assert len(cases) == 1 and cases[0]["tc_id"] == original and cases[0]["question"] == "reworded question"
    assert cases[0]["version"] == 2 and [g["name"] for g in cases[0]["groups"]] == ["G"]
    # importing that file again, with or without the option, finds the case by its content
    for option in (True, False):
        again = store.import_cases([row(2, "c1", 1, "reworded question", answer="b")], update_by_slot=option)
        assert counts(again) == (0, 0, 1) and again["slot_conflicts"] == 0


def test_an_unknown_group_id_is_rejected(store):
    from ragevalkit.exceptions import GroupNotFound
    with pytest.raises(GroupNotFound):
        store.import_cases([row(2, "c1", 1, "q")], group_ids=["grp_nope"])


# ---- API -----------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    cfg = Config(store_path=tmp_path / "api.json", require_login=False, eval_secret="s")
    with TestClient(create_app(cfg, fn=lambda q: "a")) as c:
        yield c


def csv_file(text, name="cases.csv"):
    return {"file": (name, text.encode("utf-8"), "text/csv")}


def test_api_preview_then_import_a_pasted_tab_separated_table(client):
    pasted = "User Query\tGold Answer\tTags\nWhat is X?\tX is 1\tBilling; FAQ\nWhat is Y?\tY is 2\t\n\t\t\n"
    preview = client.post("/api/test-cases/import/preview", files=csv_file(pasted, "pasted.tsv")).json()
    assert preview["mapping"]["question"] == "User Query" and preview["mapping"]["groups"] == "Tags"
    assert preview["counts"] == {"new": 2, "update": 0, "unchanged": 0, "problem": 0}
    assert preview["group_names_in_file"] == ["Billing", "FAQ"] and preview["new_group_names"] == ["Billing", "FAQ"]
    assert preview["auto_chat"] and preview["auto_turn"]
    assert client.get("/api/test-cases").json() == []                    # preview saved nothing

    done = client.post("/api/test-cases/import", files=csv_file(pasted, "pasted.tsv")).json()
    assert (done["new"], done["updated"], done["unchanged"]) == (2, 0, 0)
    assert {g["name"]: g["member_count"] for g in client.get("/api/groups").json()} == {"Billing": 1, "FAQ": 1}


def test_api_a_wrong_column_can_be_remapped_and_bad_rows_come_back_for_fixing(client):
    text = "when,ask,reply\n1,Q one,A one\nx,Q two,A two\n"
    first = client.post("/api/test-cases/import/preview", files=csv_file(text)).json()
    assert first["question_missing"] is True
    mapping = json.dumps({"question": "ask", "expected_answer": "reply", "turn_no": "when", "chat_id": None})
    second = client.post("/api/test-cases/import/preview", files=csv_file(text), data={"mapping": mapping}).json()
    assert second["counts"]["new"] == 1 and second["counts"]["problem"] == 1
    assert second["problems"][0]["row"] == 3 and second["problems"][0]["cells"]["ask"] == "Q two"

    done = client.post("/api/test-cases/import", files=csv_file(text), data={
        "mapping": mapping, "new_group_name": "Batch 1"}).json()
    assert done["new"] == 1 and done["problems"] == 1 and done["problem_rows"][0]["reason"].startswith("Turn number")
    assert client.get("/api/groups").json()[0]["name"] == "Batch 1"


def test_api_rejects_unsupported_files_and_missing_question_column(client):
    bad = client.post("/api/test-cases/import/preview", files={"file": ("x.pdf", b"%PDF", "application/pdf")})
    assert bad.status_code == 422 and "Unsupported file type" in bad.json()["detail"]
    no_q = client.post("/api/test-cases/import", files=csv_file("a,b\n1,2\n"))
    assert no_q.status_code == 422


def test_api_template_downloads_and_group_options_validate(client):
    template = client.get("/api/test-cases/import/template")
    assert template.status_code == 200 and template.content[:2] == b"PK"
    bad = client.post("/api/test-cases/import", files=csv_file("question\nq\n"), data={"group_ids": json.dumps(["grp_nope"])})
    assert bad.status_code == 404
