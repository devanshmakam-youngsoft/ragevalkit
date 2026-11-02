"""The folders are layers, and a layer only reaches downwards:

    routers  ->  services  ->  core, schemas, utils        (prompts are used by services only)

Inside services, db_services (the TinyDB store) is a leaf: it reaches only core, schemas and utils.

Every import in the package is read (not run) and checked against that, and the service features are checked for cycles.
"""
import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parents[2] / "ragevalkit"

ALLOWED = {
    "core": {"core"},
    "utils": {"core", "schemas", "utils"},
    "schemas": {"core", "schemas", "utils"},
    "prompts": {"prompts"},
    "services": {"core", "schemas", "utils", "prompts", "services"},
    "routers": {"core", "schemas", "utils", "services", "routers"},
}


SERVICE_GROUPS = {"evaluation", "testcases"}
SERVICE_RANK = {"testcases": 1, "evaluation": 2}                   # everything else in services is a building block: rank 0
FOLDERS_OF_FOLDERS = {"ragevalkit", "ragevalkit.services", "ragevalkit.services.evaluation", "ragevalkit.services.testcases"}


def _imports():
    """(file, layer of the file, layer imported, dotted module) for every ragevalkit import in the package."""
    for path in PACKAGE.rglob("*.py"):
        parts = path.relative_to(PACKAGE).parts
        if parts[0] == "web" or len(parts) == 1:                    # generated files, and the three top-level files
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = []
            if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "ragevalkit":
                modules = [node.module]
                if node.module in FOLDERS_OF_FOLDERS:                   # `from ragevalkit.services import step_recorder`
                    modules += [f"{node.module}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Import):
                modules = [a.name for a in node.names if a.name.split(".")[0] == "ragevalkit"]
            for module in modules:
                segments = module.split(".")
                if len(segments) > 1:
                    yield path.relative_to(PACKAGE.parent), parts[0], segments[1], module


def test_every_folder_is_a_known_layer():
    folders = {p.name for p in PACKAGE.iterdir() if p.is_dir() and p.name not in {"web", "__pycache__"}}
    assert folders == set(ALLOWED)


def test_a_layer_only_imports_from_the_layers_below_it():
    broken = sorted({f"{file}: {layer} must not import {module}" for file, layer, target, module in _imports() if target not in ALLOWED[layer]})
    assert not broken, "\n".join(broken)


def _feature(parts: tuple[str, ...]) -> str | None:
    """The service feature a path or dotted module belongs to ("evaluation/answer_judge", "db_services"), from its segments
    after `ragevalkit/services`."""
    if not parts:
        return None
    if parts[0] in SERVICE_GROUPS:
        return "/".join(parts[:2]) if len(parts) > 1 else parts[0]
    return parts[0]


def _service_imports():
    """(feature of the file, feature imported) for every import between service features."""
    for file, layer, target, module in _imports():
        if layer == "services" and target == "services" and len(file.parts) > 3:
            mine, theirs = _feature(file.parts[2:-1] or file.parts[2:]), _feature(tuple(module.split(".")[2:]))
            if mine and theirs and mine != theirs and not theirs.startswith(mine + "/") and not mine.startswith(theirs + "/"):
                yield mine, theirs


def _rank(feature: str) -> int:
    return SERVICE_RANK.get(feature.split("/")[0], 0)


def test_a_service_group_only_uses_the_groups_below_it():
    """top-level services (db_services, llm_client, text_metrics, app_info) < testcases < evaluation."""
    broken = sorted({f"{mine} must not import {theirs}" for mine, theirs in _service_imports() if _rank(theirs) > _rank(mine)})
    assert not broken, "\n".join(broken)


def test_service_features_do_not_import_each_other_in_a_circle():
    graph: dict[str, set[str]] = {}
    for mine, theirs in _service_imports():
        graph.setdefault(mine, set()).add(theirs)

    def cycle_from(start: str, path: tuple[str, ...] = ()) -> tuple[str, ...] | None:
        if start in path:
            return path[path.index(start):] + (start,)
        for nxt in graph.get(start, ()):
            found = cycle_from(nxt, path + (start,))
            if found:
                return found
        return None

    cycles = [c for c in (cycle_from(feature) for feature in graph) if c]
    assert not cycles, f"services import each other in a circle: {' -> '.join(cycles[0])}"


def test_the_database_code_is_a_leaf_that_knows_nothing_about_the_rest_of_services():
    broken = sorted({f"{file}: db_services must not import {module}" for file, layer, target, module in _imports()
                     if file.parts[1:3] == ("services", "db_services")
                     and (target not in {"core", "schemas", "utils"} and not module.startswith("ragevalkit.services.db_services"))})
    assert not broken, "\n".join(broken)


@pytest.mark.parametrize("folder", sorted(ALLOWED))
def test_every_package_folder_has_an_init_that_says_what_it_is(folder):
    for init in (PACKAGE / folder).rglob("__init__.py"):
        assert init.read_text(encoding="utf-8").strip(), f"{init.relative_to(PACKAGE.parent)} is empty"
