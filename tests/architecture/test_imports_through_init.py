"""A folder is used through its ``__init__``: code outside ``ragevalkit/a/b/`` writes ``from ragevalkit.a.b import name``,
never ``from ragevalkit.a.b.some_module import name``. Files inside the folder import each other directly (going through their
own ``__init__`` would be circular), and every name a folder offers is listed in its ``__all__``.
"""
import ast
import importlib
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parents[2] / "ragevalkit"


def _module_name(path: Path) -> str:
    parts = ["ragevalkit", *path.relative_to(PACKAGE).with_suffix("").parts]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package_files() -> list[Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if not {"web", "__pycache__"} & set(p.relative_to(PACKAGE).parts))


def test_other_folders_are_imported_through_their_init():
    module_files = {_module_name(p) for p in _package_files() if p.name != "__init__.py"}
    broken = []
    for path in _package_files():
        me = _module_name(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.ImportFrom) and node.module in module_files):
                continue
            folder = node.module.rsplit(".", 1)[0]
            if folder == "ragevalkit" or me == folder or me.startswith(folder + "."):
                continue
            broken.append(f"{path.relative_to(PACKAGE.parent)}: import from {folder} instead of {node.module}")
    assert not broken, "\n".join(sorted(broken))


@pytest.mark.parametrize("init", [p for p in _package_files() if p.name == "__init__.py" and p.parent != PACKAGE],
                         ids=lambda p: _module_name(p))
def test_everything_a_folder_lists_in_all_exists(init):
    module = importlib.import_module(_module_name(init))
    missing = [name for name in getattr(module, "__all__", []) if not hasattr(module, name)]
    assert not missing, f"{_module_name(init)}.__all__ lists names that are not there: {missing}"
