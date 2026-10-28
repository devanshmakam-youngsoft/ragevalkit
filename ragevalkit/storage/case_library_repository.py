"""Test cases: listing, editing, status, deleting and choosing which ones a run executes."""
import logging
from datetime import datetime, timezone

from tinydb import Query

from ragevalkit.exceptions import InvalidInput
from ragevalkit.storage.base import StoreBase
from ragevalkit.storage.exceptions import GroupNotFound
from ragevalkit.storage.selection import RunSelection, cases_to_dataframe
from ragevalkit.test_cases.identity import case_id_for, case_order, latest_versions

logger = logging.getLogger(__name__)


class CaseLibraryRepository(StoreBase):
    """Versioned test cases. Editing a case adds a new version row; the case id stays the same."""

    def _with_groups(self, cases: list[dict]) -> list[dict]:
        """Copy each case and attach ``groups``: the labels it carries, as [{group_id, name}]."""
        with self._lock:
            names = {g["group_id"]: g["name"] for g in self.groups.all() if not g.get("deleted_at")}
            members = list(self.group_members.all())
        by_tc: dict[str, list[dict]] = {}
        for m in members:
            name = names.get(m["group_id"])
            if name is not None:
                by_tc.setdefault(m["tc_id"], []).append({"group_id": m["group_id"], "name": name})
        return [
            {**c, "groups": sorted(by_tc.get(c["tc_id"], []), key=lambda g: g["name"].lower())}
            for c in cases
        ]

    def list_test_cases(
        self,
        group_id: str | None = None,
        status: str | None = None,
        # backward-compat alias — ignored but accepted so old callers don't break
        dataset_id: str | None = None,
    ) -> list[dict]:
        """Return the latest version of each test case (with its group labels), optionally filtered."""
        effective_group = group_id or dataset_id  # dataset_id alias
        with self._lock:
            Q = Query()
            if effective_group:
                member_tcs = {m["tc_id"] for m in self.group_members.search(Q.group_id == effective_group)}
                if not member_tcs:
                    return []
                all_tc = self.test_cases.search(Q.tc_id.one_of(list(member_tcs)))
            else:
                all_tc = self.test_cases.all()

        result = list(latest_versions(all_tc).values())
        if status:
            result = [r for r in result if r.get("status") == status]
        return self._with_groups(sorted(result, key=case_order))

    def get_test_case_history(self, tc_id: str, dataset_id: str | None = None) -> list[dict]:
        """Return all versions of a test case, oldest first."""
        with self._lock:
            Q = Query()
            versions = self.test_cases.search(Q.tc_id == tc_id)
        return sorted(versions, key=lambda r: r.get("version", 1))

    def update_test_case_status(self, tc_id: str, status: str, dataset_id: str | None = None) -> bool:
        """Set status of all versions of a test case to active / inactive."""
        return bool(self.update_status_bulk([tc_id], status))

    def update_status_bulk(self, tc_ids: list[str], status: str) -> int:
        """Set the status of several test cases at once: ``active`` or ``inactive`` (inactive cases do not run).
        Removing a case is ``delete_test_cases``. Returns how many cases were found."""
        if status not in ("active", "inactive"):
            return 0
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            Q = Query()
            known = {r["tc_id"] for r in self.test_cases.search(Q.tc_id.one_of(list(tc_ids)))} if tc_ids else set()
            if known:
                self.test_cases.update({"status": status, "updated_at": now}, Q.tc_id.one_of(list(known)))
        return len(known)

    def delete_test_cases(self, tc_ids: list[str]) -> int:
        """Permanently remove test cases: every version, and their group labels. Returns how many existed.
        Results of past runs are untouched (each receipt keeps its own copy of the question and answer)."""
        if not tc_ids:
            return 0
        with self._lock:
            Q = Query()
            found = {r["tc_id"] for r in self.test_cases.search(Q.tc_id.one_of(list(tc_ids)))}
            if found:
                self.test_cases.remove(Q.tc_id.one_of(list(found)))
                self.group_members.remove(Q.tc_id.one_of(list(found)))
        return len(found)

    def existing_tc_ids(self) -> set[str]:
        """The ids of every test case that still exists (past results use this to tell which were deleted since)."""
        with self._lock:
            return {r["tc_id"] for r in self.test_cases.all()}

    def _drop_legacy_deleted(self) -> None:
        """Test cases are deleted for good now. Ones an older version only hid (status "deleted") are removed here."""
        with self._lock:
            latest = latest_versions(list(self.test_cases.all()))
            gone = [tid for tid, tc in latest.items() if tc.get("status") == "deleted"]
            if gone:
                Q = Query()
                self.test_cases.remove(Q.tc_id.one_of(gone))
                self.group_members.remove(Q.tc_id.one_of(gone))
        if gone:
            logger.info("removed %d test case(s) that had been deleted earlier", len(gone))

    def edit_test_case(self, tc_id: str, updates: dict, dataset_id: str | None = None) -> dict | None:
        """Create a new version of a test case with the given field updates.

        Editable: question, expected_answer, expected_sources, type, chat_id, turn_no.
        The tc_id never changes, so group labels and history follow the case when its
        chat or turn is edited. Returns the new version record, or None if tc_id is unknown
        or there is nothing to change. Raises ValueError for an invalid value.
        """
        allowed = {"question", "expected_answer", "expected_sources", "type", "chat_id", "turn_no"}
        updates = {k: v for k, v in updates.items() if k in allowed and v is not None}
        if not updates:
            return None
        if "chat_id" in updates:
            updates["chat_id"] = str(updates["chat_id"]).strip()
            if not updates["chat_id"]:
                raise InvalidInput("Chat ID cannot be empty")
        if "turn_no" in updates:
            try:
                updates["turn_no"] = int(updates["turn_no"])
            except (TypeError, ValueError):
                raise InvalidInput("Turn number must be a whole number") from None
            if updates["turn_no"] < 1:
                raise InvalidInput("Turn number must be 1 or higher")
        if "question" in updates and not str(updates["question"]).strip():
            raise InvalidInput("Question cannot be empty")

        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            Q = Query()
            existing = self.test_cases.search(Q.tc_id == tc_id)
            if not existing:
                return None
            latest = max(existing, key=lambda r: r.get("version", 1))
            new_record = {k: v for k, v in latest.items() if not k.startswith("_")}
            new_record.pop("doc_id", None)
            new_record["version"] = latest["version"] + 1
            new_record["updated_at"] = now
            new_record.update(updates)
            self.test_cases.insert(new_record)

        return self._with_groups([new_record])[0]

    def resolve_selection(
        self,
        group_ids: list[str] | tuple = (),
        tc_ids: list[str] | tuple = (),
        status: str = "active",
        include_context: bool = True,
    ) -> "RunSelection":
        """Work out exactly which test cases a run would execute.

        ``group_ids`` pulls in every case carrying one of those labels, filtered by ``status``
        (``active`` | ``inactive`` | ``all``). ``tc_ids`` adds
        individual cases regardless of their active/inactive state. A case in several of the
        chosen groups runs once.

        Conversations are replayed turn by turn, so a case at turn 3 needs turns 1-2 for context.
        With ``include_context`` those earlier active turns of the same chat (limited to a shared
        group when the case has one) are added; they are counted separately in the result.

        Raises GroupNotFound for an unknown group, ValueError for a bad ``status``.
        """
        if status not in ("active", "inactive", "all"):
            raise InvalidInput(f"status must be 'active', 'inactive' or 'all', got {status!r}")
        group_ids = list(dict.fromkeys(group_ids))
        tc_ids = list(dict.fromkeys(tc_ids))

        with self._lock:
            latest = latest_versions(list(self.test_cases.all()))
            group_names = {g["group_id"]: g["name"] for g in self.groups.all() if not g.get("deleted_at")}
            members = [m for m in self.group_members.all()]
        for gid in group_ids:
            if gid not in group_names:
                raise GroupNotFound(gid)

        tcs_of_group: dict[str, set[str]] = {}
        groups_of_tc: dict[str, set[str]] = {}
        for m in members:
            if m["group_id"] not in group_names:
                continue  # deleted groups no longer label anything
            tcs_of_group.setdefault(m["group_id"], set()).add(m["tc_id"])
            groups_of_tc.setdefault(m["tc_id"], set()).add(m["group_id"])

        chosen: dict[str, dict] = {}
        for gid in group_ids:
            for tid in tcs_of_group.get(gid, ()):
                tc = latest.get(tid)
                if tc is None:
                    continue
                if status != "all" and tc.get("status") != status:
                    continue
                chosen[tid] = tc
        missing = 0
        for tid in tc_ids:
            tc = latest.get(tid)
            if tc is None:
                missing += 1
            else:
                chosen[tid] = tc

        context: dict[str, dict] = {}
        if include_context:
            active_by_chat: dict[str, list[dict]] = {}
            for tc in latest.values():
                if tc.get("status") == "active":
                    active_by_chat.setdefault(str(tc["chat_id"]), []).append(tc)
            for tc in chosen.values():
                if tc["turn_no"] <= 1:
                    continue
                mine = groups_of_tc.get(tc["tc_id"], set())
                for prev in active_by_chat.get(str(tc["chat_id"]), []):
                    if prev["turn_no"] >= tc["turn_no"] or prev["tc_id"] in chosen:
                        continue
                    if mine and not (mine & groups_of_tc.get(prev["tc_id"], set())):
                        continue
                    context[prev["tc_id"]] = prev

        cases = sorted({**context, **chosen}.values(), key=case_order)

        # Two different cases in one run on the same chat + turn would share a conversation
        # slot and silently overwrite each other's history — surface that instead.
        slots: dict[tuple[str, int], list[str]] = {}
        for tc in cases:
            slots.setdefault((str(tc["chat_id"]), int(tc["turn_no"])), []).append(tc["tc_id"])
        collisions = [
            {"chat_id": chat, "turn_no": turn, "tc_ids": ids}
            for (chat, turn), ids in slots.items() if len(ids) > 1
        ]

        ran_groups = {g for tid in chosen for g in groups_of_tc.get(tid, ()) if g in group_ids}
        names_of_tc = {
            tid: sorted(group_names[g] for g in gids if g in group_names)
            for tid, gids in groups_of_tc.items()
        }
        return RunSelection(
            df=cases_to_dataframe(cases, names_of_tc),
            selected=len(chosen),
            context=len(context),
            missing=missing,
            group_names=[group_names[g] for g in group_ids if g in ran_groups],      # only groups that had cases in this run
            collisions=collisions,
        )

    def create_test_case(self, chat_id: str, turn_no: int,
                         question: str, expected_answer: str,
                         type: str = "rag", expected_sources: str = "",
                         group_id: str | None = None,
                         # backward-compat: dataset_id accepted but ignored
                         dataset_id: str | None = None) -> dict:
        """Create a new test case manually (without dataset upload)."""
        now = datetime.now(timezone.utc).isoformat()
        tc_id = case_id_for(chat_id, turn_no, question)
        record = {
            "tc_id": tc_id,
            "version": 1,
            "chat_id": chat_id,
            "turn_no": turn_no,
            "type": type,
            "question": question,
            "expected_answer": expected_answer,
            "expected_sources": expected_sources,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            Q = Query()
            existing = self.test_cases.search(Q.tc_id == tc_id)
            if existing:
                latest = max(existing, key=lambda r: r.get("version", 1))
                record["version"] = latest["version"] + 1
                record["created_at"] = latest["created_at"]
            self.test_cases.insert(record)
        if group_id:
            self.add_tc_to_group(group_id, tc_id)
        return self._with_groups([record])[0]
