"""Adding test cases from parsed rows, with a preview that saves nothing."""
import logging
from datetime import datetime, timezone


from ragevalkit.storage.base import StoreBase
from ragevalkit.storage.exceptions import GroupNotFound
from ragevalkit.storage.records import clean_expected_sources
from ragevalkit.test_cases.identity import latest_versions, case_id_for

logger = logging.getLogger(__name__)


class CaseImportRepository(StoreBase):
    """Bulk import of test cases (new, updated, unchanged), used by the import dialog and by document generation."""

    def import_cases(
        self,
        rows: list[dict],
        *,
        group_ids: list[str] | tuple = (),
        new_group_name: str | None = None,
        update_by_slot: bool = False,
        dry_run: bool = False,
    ) -> dict:
        """Add or update test cases from parsed rows (see ragevalkit.importing.parse_rows).

        Each row is one of: ``new``; ``update`` (a case with the same chat, turn and question exists but its
        answer, sources or type differ: saved as a new version, keeping the case's chat/turn and status);
        ``unchanged``. Importing the same file twice therefore changes nothing the second time. A case that
        was deleted is simply gone, so a row for it is new again.

        Every row is labelled with ``group_ids`` and ``new_group_name`` (created if needed), and with the group
        names in its own ``groups`` list (created if needed). Names match existing groups case-insensitively.

        ``update_by_slot``: a row whose chat and turn match exactly one existing case that has a *different
        question* updates that case instead of being added as a new one (the case keeps its history).
        Either way such rows are counted in ``slot_conflicts``.

        ``dry_run`` computes the same result without saving or creating anything, so a preview cannot
        disagree with the import. Raises GroupNotFound for an unknown ``group_ids`` entry.
        """
        now = datetime.now(timezone.utc).isoformat()

        # ---- which groups: chosen ones, a new one, and the names written in the file
        with self._lock:
            live = {g["group_id"]: g["name"] for g in self.groups.all() if not g.get("deleted_at")}
        for gid in group_ids:
            if gid not in live:
                raise GroupNotFound(gid)
        wanted_names: dict[str, str] = {}
        for name in ([new_group_name] if new_group_name and new_group_name.strip() else []) + [
            n for r in rows for n in (r.get("groups") or [])
        ]:
            wanted_names.setdefault(name.strip().lower(), name.strip())
        by_name = {n.lower(): gid for gid, n in live.items()}
        groups_created: list[str] = []
        name_to_id: dict[str, str | None] = {}
        for key, name in wanted_names.items():
            if key in by_name:
                name_to_id[key] = by_name[key]
            else:
                groups_created.append(name)
                name_to_id[key] = f"__new__:{key}" if dry_run else self.create_group(name)  # placeholder: nothing is created in a dry run
        everywhere = list(dict.fromkeys(
            list(group_ids)
            + ([name_to_id[new_group_name.strip().lower()]] if new_group_name and new_group_name.strip() else [])
        ))

        result = {
            "new": 0, "updated": 0, "unchanged": 0,
            "slot_conflicts": 0, "labelled": 0, "groups_created": groups_created, "outcomes": [],
        }
        with self._lock:
            latest = latest_versions(list(self.test_cases.all()))
            linked = {(m["group_id"], m["tc_id"]) for m in self.group_members.all()}
            slots: dict[tuple[str, int], list[str]] = {}
            for tc in latest.values():
                slots.setdefault((str(tc["chat_id"]), int(tc["turn_no"])), []).append(tc["tc_id"])
            inserts: list[dict] = []
            links: list[dict] = []
            touched: set[str] = set()

            for r in rows:
                tc_id = case_id_for(r["chat_id"], r["turn_no"], r["question"])
                fields = {
                    "question": r["question"],
                    "expected_answer": r["expected_answer"],
                    "expected_sources": clean_expected_sources(r.get("expected_sources", "")),
                    "type": r.get("type") or "rag",
                }
                target: str | None = tc_id
                existing = latest.get(tc_id)
                if existing is None:
                    candidates = [t for t in slots.get((r["chat_id"], r["turn_no"]), []) if t != tc_id and t not in touched]
                    same_question = [t for t in candidates if latest[t]["question"] == r["question"]]
                    if same_question:
                        # e.g. a case whose question was updated by an earlier import: match it by content
                        target, existing = same_question[0], latest[same_question[0]]
                    elif candidates:
                        result["slot_conflicts"] += 1
                        if update_by_slot and len(candidates) == 1:
                            target, existing = candidates[0], latest[candidates[0]]

                if existing is not None:
                    changed = any(existing.get(k, "") != v for k, v in fields.items())
                    outcome = "update" if changed else "unchanged"
                    if changed:
                        record = {k: v for k, v in existing.items() if not k.startswith("_")}
                        record.pop("doc_id", None)
                        record.update(fields, version=existing["version"] + 1, updated_at=now)
                        if r.get("origin"):
                            record["origin"] = r["origin"]
                        inserts.append(record)
                        latest[target] = record
                else:
                    outcome = "new"
                    record = {
                        "tc_id": tc_id, "version": 1, "chat_id": r["chat_id"], "turn_no": r["turn_no"],
                        **fields, "status": "active", "created_at": now, "updated_at": now,
                        **({"origin": r["origin"]} if r.get("origin") else {}),  # e.g. generated from a document
                    }
                    inserts.append(record)
                    latest[tc_id] = record
                    slots.setdefault((r["chat_id"], r["turn_no"]), []).append(tc_id)

                result[{"new": "new", "update": "updated", "unchanged": "unchanged"}[outcome]] += 1
                result["outcomes"].append({"row": r["row"], "outcome": outcome, "tc_id": target})
                if target is None:
                    continue
                touched.add(target)
                for gid in everywhere + [name_to_id[n.lower()] for n in (r.get("groups") or [])]:
                    if gid is None or (gid, target) in linked:
                        continue
                    linked.add((gid, target))
                    links.append({"group_id": gid, "tc_id": target, "added_at": now})

            result["labelled"] = len(links)
            if not dry_run:
                if inserts:
                    self.test_cases.insert_multiple(inserts)
                if links:
                    self.group_members.insert_multiple(links)
        return result
