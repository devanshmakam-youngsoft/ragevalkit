"""Which version to ship and how groups have done, with the settings given to serve()."""
from ragevalkit.config import Config
from ragevalkit.exceptions import InvalidInput, NotFoundError
from ragevalkit.recommendation import group_overview, recommend
from ragevalkit.storage.store import EvalStore


def recommendation_settings(cfg: Config, tolerance: float | None = None, max_time: float | None = None) -> dict:
    """Weights, tolerance and time ceiling from serve(), overridable per request."""
    return {
        "answer_weight": cfg.answer_weight,
        "material_weight": cfg.material_weight,
        "tolerance": cfg.recommendation_tolerance if tolerance is None else tolerance,
        "min_quality": cfg.recommendation_min_quality,
        "max_time": cfg.max_response_time if max_time is None else (max_time if max_time > 0 else None),
    }


def recommend_version(cfg: Config, store: EvalStore, group: str | None, tolerance: float | None, max_time: float | None) -> dict:
    if tolerance is not None and tolerance < 0:
        raise InvalidInput("tolerance must be 0 or higher")
    return recommend(store.list_versions_for_comparison(), group=group, **recommendation_settings(cfg, tolerance, max_time))


def groups_with_history(cfg: Config, store: EvalStore, include_deleted: bool) -> list[dict]:
    """Every group with its test case count and how it has done: its last run and its best version so far."""
    versions = store.list_versions_for_comparison()
    out = []
    for group in store.list_groups(include_deleted=include_deleted):
        overview = group_overview(versions, group["name"], **recommendation_settings(cfg))
        out.append({**group, "run_count": overview["run_count"], "last_run": overview["last"], "best_run": overview["best"]})
    return out


def history_of_group(cfg: Config, store: EvalStore, group_id: str) -> dict:
    """One group's history across non-archived runs (newest first), its last run and its best version."""
    group = next((g for g in store.list_groups() if g["group_id"] == group_id), None)
    if group is None:
        raise NotFoundError("Group not found")
    return {"group": group, **group_overview(store.list_versions_for_comparison(), group["name"], **recommendation_settings(cfg))}
