"""Rename the library everywhere: the package folder, every import, pyproject, the docs and the name constant.

    python scripts/rename_library.py NEW_NAME            a dry run: lists what would change
    python scripts/rename_library.py NEW_NAME --apply    does it

The new name is a lowercase Python identifier (it becomes ``import NEW_NAME``). Links to the GitHub repository and the
repository folder name (``ragevalkit-lib``) are left alone: rename the repository on GitHub yourself. Afterwards run
``python scripts/build_guide.py`` and ``cd frontend && npm run build``, then the tests.
"""
import argparse
import re
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

TEXT_SUFFIXES = {".py", ".md", ".toml", ".html", ".ts", ".tsx", ".json", ".txt", ".cfg", ".yml", ".yaml", ".gitignore"}
SKIP_PARTS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".claude", ".pytest_cache", ".ruff_cache", "dist", "build"}
COMPILED_DASHBOARD = ("web", "dashboard")


def find_package(root: Path) -> Path:
    """The package folder: the one that holds core/constants/library.py."""
    found = [p.parent.parent.parent for p in root.glob("*/core/constants/library.py")]
    if len(found) != 1:
        raise SystemExit(f"expected exactly one package with core/constants/library.py under {root}, found {len(found)}")
    return found[0]


def text_files(root: Path, skip: Path) -> Iterator[Path]:
    """Yield the text files under ``root`` that can mention the name, leaving out caches, built files and ``skip``."""
    for path in root.rglob("*"):
        if not path.is_file() or path == skip:
            continue
        parts = set(path.relative_to(root).parts)
        if parts & SKIP_PARTS or any(part.endswith(".egg-info") for part in parts):
            continue
        if COMPILED_DASHBOARD == tuple(path.relative_to(root).parts[1:3]):      # built files are rebuilt, not rewritten
            continue
        if path.suffix in TEXT_SUFFIXES or path.name == ".gitignore":
            yield path


def name_pattern(old: str) -> re.Pattern:
    """The name as a word: not part of a longer name, a URL or the repository folder, but also the start of ``<name>_data``."""
    return re.compile(rf"(?<![\w/.-]){re.escape(old)}(?![-\w])|(?<![\w/.-]){re.escape(old)}(?=_data\b)")


def main(argv: list[str] | None = None) -> int:
    """List or make the rename and return the exit code."""
    parser = argparse.ArgumentParser(description="Rename the library everywhere.")
    parser.add_argument("new_name", help="the new import name, lowercase (for example evalkit)")
    parser.add_argument("--apply", action="store_true", help="make the changes (the default only lists them)")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent, help="the repository folder")
    args = parser.parse_args(argv)

    if not re.fullmatch(r"[a-z][a-z0-9_]*", args.new_name):
        raise SystemExit("the new name must be lowercase letters, digits and underscores, starting with a letter")
    root = args.root.resolve()
    package = find_package(root)
    old = package.name
    if args.new_name == old:
        raise SystemExit(f"the library is already called {old}")
    if (root / args.new_name).exists():
        raise SystemExit(f"{root / args.new_name} already exists")

    pattern = name_pattern(old)
    changes = []
    for path in text_files(root, skip=Path(__file__).resolve()):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        count = len(pattern.findall(text))
        if count:
            changes.append((path, count, text))

    print(f"{old} -> {args.new_name}")
    print(f"  rename folder {package.relative_to(root)}/ to {args.new_name}/")
    for path, count, _ in changes:
        print(f"  {count:4} x  {path.relative_to(root)}")
    print(f"  {len(changes)} files, {sum(c for _, c, _ in changes)} replacements")
    if not args.apply:
        print("dry run: nothing changed. Add --apply to do it.")
        return 0

    for path, _, text in changes:
        crlf = "\r\n" in path.read_bytes().decode("utf-8", errors="ignore")
        path.write_bytes(pattern.sub(args.new_name, text).replace("\r\n", "\n").replace("\n", "\r\n" if crlf else "\n").encode("utf-8"))
    shutil.move(str(package), str(root / args.new_name))
    print("done. Next: python scripts/build_guide.py, then cd frontend && npm run build, then the tests.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
