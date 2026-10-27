"""Groups: labels put on test cases."""
import logging
from datetime import datetime, timezone

import pandas as pd
from tinydb import Query
from tinydb.operations import delete

from ragevalkit.storage.base import StoreBase
from ragevalkit.storage.exceptions import ConflictError, GroupNotFound
from ragevalkit.storage.records import clean_expected_sources, new_group_id
from ragevalkit.test_cases.identity import latest_versions

logger = logging.getLogger(__name__)


class GroupsRepository(StoreBase):
    """A group is just a label; a test case can carry any number of them."""

    def _group_name_taken(self, name: str, ignore_id: str | None = None) -> bool:
        wanted = name.strip().lower()
        return any(
            g["name"].strip().lower() == wanted and g["group_id"] != ignore_id and not g.get("deleted_at")
            for g in self.groups.all()
        )

    def _is_live_group(self, group_id: str) -> bool:
        """True for a group that exists and is not deleted. Caller holds the lock."""
        hit = self.groups.search(Query().group_id == group_id)
        return bool(hit) and not hit[0].get("deleted_at")

    def create_group(self, name: str) -> str:
        """Create a named group. Returns group_id. Raises ConflictError if the name is in use."""
        name = name.strip()
        if not name:
            raise ValueError("Group name cannot be empty")
        gid = new_group_id()
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if self._group_name_taken(name):
                raise ConflictError(f"A group named {name!r} already exists")
            self.groups.insert({"group_id": gid, "name": name, "created_at": now})
        return gid

    def rename_group(self, group_id: str, name: str) -> bool:
        """Rename a group. Raises ConflictError if another group already has that name."""
        name = name.strip()
        if not name:
            raise ValueError("Group name cannot be empty")
        with self._lock:
            Q = Query()
            if not self._is_live_group(group_id):
                return False
            if self._group_name_taken(name, ignore_id=group_id):
                raise ConflictError(f"A group named {name!r} already exists")
            old = self.groups.search(Q.group_id == group_id)[0]["name"]
            self.groups.update({"name": name}, Q.group_id == group_id)
            if old != name:
                self._rename_in_runs(old, name)
        return True

    def _rename_in_runs(self, old: str, new: str) -> None:
        """Past runs record group names; follow a rename so group history and dashboard filters keep working.
        Caller holds the lock."""
        for run in self.runs.all():
            names = run.get("group_names") or []
            stats = run.get("group_stats") or {}
            if old not in names and old not in stats:
                continue
            changes: dict = {
                "group_names": [new if n == old else n for n in names],
                "group_stats": {(new if k == old else k): v for k, v in stats.items()},
            }
            if old in str(run.get("dataset", "")).split(" + "):
                changes["dataset"] = " + ".join(new if p == old else p for p in str(run["dataset"]).split(" + "))
            self.runs.update(changes, doc_ids=[run.doc_id])

    def list_groups(self, include_deleted: bool = False) -> list[dict]:
        """Return groups with member_count. Deleted groups are
        left out unless ``include_deleted``; they carry a ``deleted_at`` timestamp."""
        with self._lock:
            all_groups = [dict(g) for g in self.groups.all()]
            all_members = list(self.group_members.all())
            latest = latest_versions(list(self.test_cases.all()))
        counts: dict[str, int] = {}
        for m in all_members:
            tc = latest.get(m["tc_id"])
            if tc is not None:
                counts[m["group_id"]] = counts.get(m["group_id"], 0) + 1
        out = []
        for g in all_groups:
            if g.get("deleted_at") and not include_deleted:
                continue
            g["member_count"] = counts.get(g["group_id"], 0)
            g.setdefault("deleted_at", None)
            out.append(g)
        return sorted(out, key=lambda g: g.get("created_at", ""))

    def import_into_group(self, group_id: str, df: "pd.DataFrame") -> int:
        """Upsert test cases from a DataFrame and label them with a group. Returns how many labels were added."""
        rows = [
            {
                "row": i + 2,
                "chat_id": str(r.chat_id),
                "turn_no": int(r.turn_no),
                "type": str(getattr(r, "type", "rag")),
                "question": str(r.question),
                "expected_answer": str(r.expected_answer),
                "expected_sources": clean_expected_sources(getattr(r, "expected_sources", "")),
                "groups": [],
            }
            for i, r in enumerate(df.itertuples(index=False))
        ]
        return self.import_cases(rows, group_ids=[group_id])["labelled"]

    def get_group_test_cases(self, group_id: str, status: str | None = None) -> list[dict]:
        """Return test cases in a group (latest version each)."""
        return self.list_test_cases(group_id=group_id, status=status)

    def add_tc_to_group(self, group_id: str, tc_id: str) -> bool:
        return bool(self.add_tcs_to_group(group_id, [tc_id]))

    def add_tcs_to_group(self, group_id: str, tc_ids: list[str]) -> int:
        """Label test cases with a group. Returns how many were newly added (already-labelled
        and unknown tc_ids are skipped). Raises GroupNotFound for an unknown group."""
        now = datetime.now(timezone.utc).isoformat()
        added = 0
        with self._lock:
            Q = Query()
            if not self._is_live_group(group_id):
                raise GroupNotFound(group_id)
            for tc_id in dict.fromkeys(tc_ids):
                if not self.test_cases.search(Q.tc_id == tc_id):
                    continue
                if self.group_members.search((Q.group_id == group_id) & (Q.tc_id == tc_id)):
                    continue
                self.group_members.insert({"group_id": group_id, "tc_id": tc_id, "added_at": now})
                added += 1
        return added

    def remove_tc_from_group(self, group_id: str, tc_id: str) -> bool:
        return bool(self.remove_tcs_from_group(group_id, [tc_id]))

    def remove_tcs_from_group(self, group_id: str, tc_ids: list[str]) -> int:
        """Remove a group label from test cases. Returns how many labels were removed."""
        if not tc_ids:
            return 0
        with self._lock:
            Q = Query()
            removed = self.group_members.remove((Q.group_id == group_id) & Q.tc_id.one_of(list(tc_ids)))
        return len(removed)

    def set_test_case_groups(self, tc_id: str, group_ids: list[str]) -> bool:
        """Replace the full set of group labels on one test case. Returns False if it is unknown.
        Raises GroupNotFound for an unknown group."""
        now = datetime.now(timezone.utc).isoformat()
        wanted = list(dict.fromkeys(group_ids))
        with self._lock:
            Q = Query()
            if not self.test_cases.search(Q.tc_id == tc_id):
                return False
            known = {g["group_id"] for g in self.groups.all() if not g.get("deleted_at")}
            for gid in wanted:
                if gid not in known:
                    raise GroupNotFound(gid)
            # only touch labels from live groups: a deleted group's labels must survive for a restore
            self.group_members.remove((Q.tc_id == tc_id) & Q.group_id.one_of(list(known)))
            for gid in wanted:
                self.group_members.insert({"group_id": gid, "tc_id": tc_id, "added_at": now})
        return True

    def delete_group(self, group_id: str) -> bool:
        """Delete a group: it disappears from the app but is kept (with its labels), so past runs
        that refer to it stay readable and it can be restored. Test cases are never touched.
        Returns False if the group does not exist or is already deleted."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if not self._is_live_group(group_id):
                return False
            self.groups.update({"deleted_at": now}, Query().group_id == group_id)
        return True

    def restore_group(self, group_id: str) -> bool:
        """Bring a deleted group back with its labels. Raises ConflictError if another group
        has taken its name in the meantime. Returns False if it is not a deleted group."""
        with self._lock:
            Q = Query()
            hit = self.groups.search(Q.group_id == group_id)
            if not hit or not hit[0].get("deleted_at"):
                return False
            if self._group_name_taken(hit[0]["name"], ignore_id=group_id):
                raise ConflictError(f"A group named {hit[0]['name']!r} already exists; rename it first")
            self.groups.update(delete("deleted_at"), Q.group_id == group_id)
        return True

    def purge_group(self, group_id: str) -> bool:
        """Permanently remove a group that is already deleted, with its labels. Past runs keep
        the group's name and scores. Returns False if it is not a deleted group."""
        with self._lock:
            Q = Query()
            hit = self.groups.search(Q.group_id == group_id)
            if not hit or not hit[0].get("deleted_at"):
                return False
            self.groups.remove(Q.group_id == group_id)
            self.group_members.remove(Q.group_id == group_id)
        return True

    def group_names_by_test_case(self) -> dict[str, set[str]]:
        """The labels each test case carries now, as {tc_id: {group name, ...}}."""
        with self._lock:
            names = {g["group_id"]: g["name"] for g in self.groups.all()}
            members = list(self.group_members.all())
        names_of: dict[str, set[str]] = {}
        for member in members:
            if member["group_id"] in names:
                names_of.setdefault(member["tc_id"], set()).add(names[member["group_id"]])
        return names_of
