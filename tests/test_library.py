"""Test-case library: groups as labels, editing, and resolving what a run would execute."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ragevalkit.config import Config
from ragevalkit.exceptions import ConflictError, GroupNotFound
from ragevalkit.server import create_app
from ragevalkit.store import EvalStore


@pytest.fixture
def store(tmp_path):
    s = EvalStore(tmp_path / "store.json")
    yield s
    s.close()


def _df(rows):
    return pd.DataFrame(rows, columns=["chat_id", "turn_no", "type", "question", "expected_answer"])


def _seed(store):
    """Two groups: 'billing' (a 3-turn chat + one single-turn) and 'misc'."""
    billing = store.create_group("billing")
    misc = store.create_group("misc")
    store.import_into_group(billing, _df([
        ("c1", 1, "rag", "q1", "a1"),
        ("c1", 2, "rag", "q2", "a2"),
        ("c1", 3, "rag", "q3", "a3"),
        ("c2", 1, "rag", "q4", "a4"),
    ]))
    store.import_into_group(misc, _df([("c9", 1, "rag", "q9", "a9")]))
    cases = {c["question"]: c["tc_id"] for c in store.list_test_cases()}
    return billing, misc, cases


# ---- resolve_selection ---------------------------------------------------

def test_group_selection_runs_each_case_once_across_overlapping_groups(store):
    billing, misc, cases = _seed(store)
    store.add_tcs_to_group(misc, [cases["q4"]])  # q4 now carries both labels
    sel = store.resolve_selection(group_ids=[billing, misc])
    assert sel.total == 5 and sel.selected == 5 and sel.context == 0
    assert sel.group_names == ["billing", "misc"]


def test_picking_a_later_turn_pulls_in_earlier_turns_for_context(store):
    _, _, cases = _seed(store)
    sel = store.resolve_selection(tc_ids=[cases["q3"]])
    assert sel.selected == 1 and sel.context == 2 and sel.total == 3
    assert list(sel.df["turn_no"]) == [1, 2, 3]
    assert "tc_id" in sel.df.columns


def test_context_can_be_switched_off(store):
    _, _, cases = _seed(store)
    sel = store.resolve_selection(tc_ids=[cases["q3"]], include_context=False)
    assert sel.total == 1 and sel.context == 0


def test_context_only_comes_from_a_shared_group(store):
    billing, misc, cases = _seed(store)
    other = store.create_group("other")
    store.import_into_group(other, _df([("c1", 2, "rag", "unrelated", "x")]))
    # 'unrelated' shares chat c1 / turn 2 but not a group with q3 -> must not be pulled in
    sel = store.resolve_selection(tc_ids=[cases["q3"]])
    assert "unrelated" not in set(sel.df["question"])


def test_status_filter_applies_to_groups_but_not_to_picked_cases(store):
    billing, _, cases = _seed(store)
    store.update_status_bulk([cases["q4"]], "inactive")
    assert store.resolve_selection(group_ids=[billing]).total == 3
    assert store.resolve_selection(group_ids=[billing], status="all").total == 4
    assert store.resolve_selection(tc_ids=[cases["q4"]]).total == 1


def test_deleting_a_case_removes_it_everywhere_and_it_can_no_longer_run(store):
    billing, _, cases = _seed(store)
    assert store.delete_test_cases([cases["q4"], "tc_nope"]) == 1   # unknown ids are ignored
    assert store.get_test_case_history(cases["q4"]) == []           # every version is gone
    assert cases["q4"] not in {m["tc_id"] for m in store.group_members.all()}
    assert cases["q4"] not in store.existing_tc_ids()
    assert store.list_groups()[0]["member_count"] == 3
    sel = store.resolve_selection(group_ids=[billing], status="all", tc_ids=[cases["q4"], "tc_nope"])
    assert sel.total == 3 and sel.missing == 2


def test_a_case_can_only_be_active_or_inactive(store):
    _, _, cases = _seed(store)
    assert store.update_status_bulk([cases["q4"]], "deleted") == 0   # deleting is delete_test_cases
    assert store.update_status_bulk([cases["q4"]], "inactive") == 1


def test_cases_an_older_version_only_hid_are_removed_when_the_store_opens(tmp_path):
    from tinydb import Query

    from ragevalkit.store import EvalStore
    path = tmp_path / "old.json"
    first = EvalStore(path)
    first.import_cases([{"row": 2, "chat_id": "c1", "turn_no": 1, "type": "rag", "question": "q1", "expected_answer": "a",
                         "expected_sources": "", "groups": ["G"]},
                        {"row": 3, "chat_id": "c2", "turn_no": 1, "type": "rag", "question": "q2", "expected_answer": "a",
                         "expected_sources": "", "groups": ["G"]}])
    hidden = first.list_test_cases()[0]["tc_id"]
    first.test_cases.update({"status": "deleted"}, Query().tc_id == hidden)       # how an older version deleted a case
    first.db.close()
    again = EvalStore(path)
    assert [c["question"] for c in again.list_test_cases()] == ["q2"] and hidden not in {m["tc_id"] for m in again.group_members.all()}


def test_deleted_groups_are_hidden_kept_restorable_and_purgeable(store):
    billing, misc, cases = _seed(store)
    assert store.delete_group(billing) is True and store.delete_group(billing) is False
    assert [g["name"] for g in store.list_groups()] == ["misc"]
    assert [g["name"] for g in store.list_groups(include_deleted=True)] == ["billing", "misc"]
    with pytest.raises(GroupNotFound):
        store.resolve_selection(group_ids=[billing])
    case = next(c for c in store.list_test_cases() if c["tc_id"] == cases["q1"])
    assert case["groups"] == []                                      # no longer labels anything
    assert store.create_group("billing")                             # the name is free again...
    with pytest.raises(ConflictError):
        store.restore_group(billing)                                  # ...so restoring needs a rename first
    store.rename_group(next(g["group_id"] for g in store.list_groups() if g["name"] == "billing"), "billing 2")
    assert store.restore_group(billing) is True
    assert store.resolve_selection(group_ids=[billing]).total == 4   # its labels survived the round trip
    assert store.purge_group(billing) is False                       # only a deleted group can be purged
    store.delete_group(billing)
    assert store.purge_group(billing) is True
    assert billing not in {g["group_id"] for g in store.list_groups(include_deleted=True)}


def test_relabelling_a_case_keeps_a_deleted_groups_labels(store):
    billing, misc, cases = _seed(store)
    store.delete_group(billing)
    store.set_test_case_groups(cases["q1"], [misc])
    store.restore_group(billing)
    assert store.resolve_selection(group_ids=[billing]).total == 4


def test_two_cases_on_the_same_chat_and_turn_are_reported_as_a_collision(store):
    a = store.create_group("a")
    b = store.create_group("b")
    store.import_into_group(a, _df([("c1", 1, "rag", "first", "x")]))
    store.import_into_group(b, _df([("c1", 1, "rag", "second", "y")]))
    sel = store.resolve_selection(group_ids=[a, b])
    assert len(sel.collisions) == 1 and sel.collisions[0]["turn_no"] == 1


def test_unknown_group_and_bad_status_are_rejected(store):
    with pytest.raises(GroupNotFound):
        store.resolve_selection(group_ids=["grp_missing"])
    with pytest.raises(ValueError):
        store.resolve_selection(status="bogus")


# ---- editing ---------------------------------------------------------------

def test_chat_and_turn_are_editable_and_the_case_keeps_its_id_and_labels(store):
    billing, _, cases = _seed(store)
    tc_id = cases["q4"]
    edited = store.edit_test_case(tc_id, {"chat_id": "c7", "turn_no": 4})
    assert edited["tc_id"] == tc_id and edited["version"] == 2
    assert (edited["chat_id"], edited["turn_no"]) == ("c7", 4)
    assert [g["name"] for g in edited["groups"]] == ["billing"]
    assert len(store.get_test_case_history(tc_id)) == 2


@pytest.mark.parametrize("updates", [{"turn_no": 0}, {"turn_no": "x"}, {"chat_id": "  "}, {"question": " "}])
def test_invalid_edits_are_rejected(store, updates):
    _, _, cases = _seed(store)
    with pytest.raises(ValueError):
        store.edit_test_case(cases["q4"], updates)


def test_reimporting_the_original_file_does_not_revert_an_edited_chat_or_turn(store):
    billing, _, cases = _seed(store)
    store.edit_test_case(cases["q4"], {"chat_id": "c7", "turn_no": 4})
    store.import_into_group(billing, _df([("c2", 1, "rag", "q4", "changed answer")]))
    latest = next(c for c in store.list_test_cases() if c["tc_id"] == cases["q4"])
    assert (latest["chat_id"], latest["turn_no"]) == ("c7", 4)
    assert latest["expected_answer"] == "changed answer"


def test_cases_sort_naturally_by_chat(store):
    g = store.create_group("g")
    store.import_into_group(g, _df([("c10", 1, "rag", "q10", "a"), ("c2", 1, "rag", "q2", "a")]))
    assert [c["chat_id"] for c in store.list_test_cases()] == ["c2", "c10"]


# ---- groups as labels ------------------------------------------------------

def test_cases_report_their_group_labels_and_labels_can_be_replaced(store):
    billing, misc, cases = _seed(store)
    store.set_test_case_groups(cases["q1"], [misc])
    case = next(c for c in store.list_test_cases() if c["tc_id"] == cases["q1"])
    assert [g["name"] for g in case["groups"]] == ["misc"]
    store.remove_tcs_from_group(misc, [cases["q1"]])
    case = next(c for c in store.list_test_cases() if c["tc_id"] == cases["q1"])
    assert case["groups"] == []


def test_group_names_are_unique_and_renamable(store):
    a = store.create_group("Alpha")
    store.create_group("Beta")
    with pytest.raises(ConflictError):
        store.create_group("alpha")
    with pytest.raises(ConflictError):
        store.rename_group(a, "beta")
    assert store.rename_group(a, "Gamma") is True


# ---- API -------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    cfg = Config(store_path=tmp_path / "api.json", require_login=False, eval_secret="test-secret")
    app = create_app(cfg, fn=lambda q: "answer")
    with TestClient(app) as c:
        yield c


def test_api_preview_edit_and_bulk_label_flow(client):
    gid = client.post("/api/groups", json={"name": "smoke"}).json()["group_id"]
    for turn in (1, 2):
        r = client.post("/api/test-cases", json={
            "chat_id": "c1", "turn_no": turn, "question": f"q{turn}", "expected_answer": "a", "group_id": gid,
        })
        assert r.status_code == 201
    cases = client.get("/api/test-cases").json()
    assert cases[0]["groups"][0]["name"] == "smoke"
    second = cases[1]["tc_id"]

    preview = client.post("/api/runs/preview", json={"tc_ids": [second]}).json()
    assert (preview["selected"], preview["context"], preview["total"]) == (1, 1, 2)

    edited = client.patch(f"/api/test-cases/{second}", json={"chat_id": "renamed", "turn_no": 5})
    assert edited.status_code == 200 and edited.json()["chat_id"] == "renamed"
    assert client.patch(f"/api/test-cases/{second}", json={"turn_no": 0}).status_code == 422

    other = client.post("/api/groups", json={"name": "other"}).json()["group_id"]
    assert client.post(f"/api/groups/{other}/members", json={"tc_ids": [second]}).json()["added"] == 1
    assert client.post(f"/api/groups/{other}/members/remove", json={"tc_ids": [second]}).json()["removed"] == 1
    assert client.post("/api/groups", json={"name": "SMOKE"}).status_code == 409
    assert client.post("/api/runs/preview", json={"group_ids": ["nope"]}).status_code == 404
