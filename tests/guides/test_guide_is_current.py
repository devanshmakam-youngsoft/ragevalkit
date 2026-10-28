"""The packaged guide is built from docs/guide.template.html, the tested files in examples/ and the serve() signature,
so it cannot say something the code does not do. When this fails, run: python scripts/build_guide.py"""
import importlib.util
from pathlib import Path

from ragevalkit.guides import GUIDE_PATH

ROOT = Path(__file__).parents[2]


def _builder():
    spec = importlib.util.spec_from_file_location("build_guide", ROOT / "scripts" / "build_guide.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_packaged_guide_is_up_to_date():
    built = _builder().build()
    packaged = GUIDE_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert packaged == built, "ragevalkit/guides/developer-guide.html is out of date: run python scripts/build_guide.py"


def test_every_example_in_the_guide_is_a_file_that_the_tests_run():
    guide = GUIDE_PATH.read_text(encoding="utf-8")
    shown = {path.name for path in (ROOT / "examples").glob("*.py") if f"examples/{path.name}" in guide}
    tested = (ROOT / "tests" / "examples" / "test_examples.py").read_text(encoding="utf-8")
    assert shown and all(name in tested for name in shown)


def test_the_guide_documents_every_serve_option():
    import inspect

    import ragevalkit

    guide = GUIDE_PATH.read_text(encoding="utf-8")
    assert all(f"<code>{name}</code>" in guide for name in inspect.signature(ragevalkit.serve).parameters)


def test_every_link_between_pages_points_at_a_page_that_exists():
    import re

    guide = GUIDE_PATH.read_text(encoding="utf-8")
    pages = set(re.findall(r'<article class="page" id="page-([\w-]+)"', guide))
    linked = set(re.findall(r'href="#/([\w-]+)(?:/[\w-]+)?"', guide))
    assert len(pages) >= 15 and linked <= pages, f"links to missing pages: {sorted(linked - pages)}"


def test_every_page_has_a_title_a_part_and_a_place_in_the_navigation():
    import re

    guide = GUIDE_PATH.read_text(encoding="utf-8")
    slugs = re.findall(r'<article class="page" id="page-([\w-]+)"', guide)
    nav = re.findall(r'class="nav-link" href="#/([\w-]+)"', guide)
    assert slugs == nav and len(set(slugs)) == len(slugs)
