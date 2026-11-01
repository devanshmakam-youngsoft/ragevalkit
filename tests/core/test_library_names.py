"""The library's name is written in one file, and every name that depends on it is derived from it there."""
import ast
from pathlib import Path

from ragevalkit.core.config import Config
from ragevalkit.core.constants import library

PACKAGE = Path(__file__).parents[2] / "ragevalkit"
NAME_FILE = PACKAGE / "core" / "constants" / "library.py"


def test_every_derived_name_follows_the_library_name():
    assert library.DATA_DIR_NAME == f"{library.LIBRARY_NAME}_data"
    assert library.SESSION_COOKIE_NAME == f"{library.LIBRARY_NAME}_session"
    assert library.LOGGER_NAME == library.API_TITLE == library.LIBRARY_NAME
    assert library.TEMP_FOLDER_PREFIX.startswith(library.LIBRARY_NAME)


def test_the_data_folder_holds_the_store_the_logs_and_the_uploads():
    config = Config()
    assert config.data_dir == Path(library.DATA_DIR_NAME)
    assert config.store_path == config.data_dir / "store.json"
    assert config.logs_dir == config.data_dir / "logs" and config.uploads_dir == config.data_dir / "uploads"
    assert Config(data_dir=Path("somewhere")).store_path == Path("somewhere") / "store.json"
    assert config.session_cookie == library.SESSION_COOKIE_NAME


def test_no_other_file_writes_the_library_name_as_text():
    """Docstrings and comments may mention it; a string the program uses must come from library.py."""
    found = []
    for path in PACKAGE.rglob("*.py"):
        if path == NAME_FILE or "web" in path.relative_to(PACKAGE).parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                      if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                      and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                if library.LIBRARY_NAME in node.value and not node.value.startswith("ragevalkit."):    # dotted module names are imports, not names
                    found.append(f"{path.relative_to(PACKAGE.parent)}: {node.value[:60]!r}")
    assert not found, "write the name only in core/constants/library.py:\n" + "\n".join(found)
