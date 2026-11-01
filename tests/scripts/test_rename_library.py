"""Renaming the library is one command: a copy of the project is renamed and still imports, configures and passes its own checks."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "rename_library.py"


@pytest.fixture
def project_copy(tmp_path):
    """The backend, the settings file and the tests that do not need a running server, copied to a scratch folder."""
    copy = tmp_path / "copy"
    shutil.copytree(ROOT / "ragevalkit", copy / "ragevalkit", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(ROOT / "pyproject.toml", copy / "pyproject.toml")
    for folder in ("core", "architecture"):
        shutil.copytree(ROOT / "tests" / folder, copy / "tests" / folder, ignore=shutil.ignore_patterns("__pycache__"))
    (copy / "tests" / "__init__.py").write_text('"""Tests."""\n', encoding="utf-8")
    return copy


def run(*args, cwd):
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, env={**__import__("os").environ, "PYTHONPATH": str(cwd)})


def test_a_dry_run_lists_the_changes_and_changes_nothing(project_copy):
    result = run(str(SCRIPT), "evalkit", "--root", str(project_copy), cwd=project_copy)
    assert result.returncode == 0, result.stderr
    assert "ragevalkit -> evalkit" in result.stdout and "dry run" in result.stdout
    assert (project_copy / "ragevalkit").is_dir() and not (project_copy / "evalkit").exists()


def test_renaming_a_copy_leaves_a_working_project(project_copy):
    assert run(str(SCRIPT), "evalkit", "--root", str(project_copy), "--apply", cwd=project_copy).returncode == 0
    assert (project_copy / "evalkit" / "core" / "constants" / "library.py").is_file() and not (project_copy / "ragevalkit").exists()
    assert 'name = "evalkit"' in (project_copy / "pyproject.toml").read_text(encoding="utf-8")

    probe = run("-c", "import evalkit; from evalkit.core.config import Config; from evalkit.core.constants.library import LIBRARY_NAME, DATA_DIR_NAME;"
                      "print(LIBRARY_NAME, DATA_DIR_NAME, Config().data_dir, evalkit.__version__)", cwd=project_copy)
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.split()[:3] == ["evalkit", "evalkit_data", "evalkit_data"]

    checks = run("-m", "pytest", "-q", "-p", "no:cacheprovider", "tests", cwd=project_copy)
    assert checks.returncode == 0, checks.stdout[-1500:]


def test_a_bad_name_is_refused(project_copy):
    result = run(str(SCRIPT), "Not-Valid", "--root", str(project_copy), cwd=project_copy)
    assert result.returncode != 0 and "lowercase" in result.stderr
