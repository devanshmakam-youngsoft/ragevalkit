"""Builds ragevalkit/guides/developer-guide.html from docs/guide/ (a shell and one file per page in docs/guide/pages/).

A page starts with a comment giving its part, title, lead sentence and reading time. The guide's code comes from the
files in examples/ (which the tests run), and its serve() reference comes from the function itself, so neither can drift
from the library. Run it after changing a page, an example or serve():

    python scripts/build_guide.py

``tests/guides/test_guide_is_current.py`` fails when the built guide is out of date.
"""
import ast
import builtins
import html
import inspect
import io
import keyword
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GUIDE_SOURCE = ROOT / "docs" / "guide"
EXAMPLES = ROOT / "examples"
OUTPUT = ROOT / "ragevalkit" / "guides" / "developer-guide.html"

MARKER = re.compile(r"\{\{(example:[\w.]+(?:#[\w,]+)?|serve_reference|version)\}\}")
BUILTINS = set(dir(builtins)) - {"None", "True", "False"}
STRING_TOKENS = {tokenize.STRING} | {getattr(tokenize, name) for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END") if hasattr(tokenize, name)}


# ---- code ------------------------------------------------------------------------------------------------------

def highlight(source: str) -> str:
    """Python source as HTML with <span class="..."> around comments, strings, keywords and so on."""
    line_starts = [0]
    for line in source.splitlines(keepends=True):
        line_starts.append(line_starts[-1] + len(line))

    def offset(position: tuple[int, int]) -> int:
        return line_starts[position[0] - 1] + position[1]

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError):
        return html.escape(source)

    pieces, cursor, previous, in_decorator = [], 0, None, False
    for token in tokens:
        if token.type in (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER):
            in_decorator = in_decorator and token.type not in (tokenize.NEWLINE, tokenize.NL)
            continue
        start, end = offset(token.start), offset(token.end)
        pieces.append(html.escape(source[cursor:start]))
        text = html.escape(source[start:end])
        css = None
        if token.type == tokenize.OP and token.string == "@" and not source[line_starts[token.start[0] - 1]:start].strip():
            in_decorator, css = True, "d"
        elif in_decorator and (token.type == tokenize.NAME or token.string == "."):
            css = "d"
        else:
            in_decorator = False
            if token.type == tokenize.COMMENT:
                css = "c"
            elif token.type in STRING_TOKENS:
                css = "s"
            elif token.type == tokenize.NUMBER:
                css = "n"
            elif token.type == tokenize.NAME:
                if keyword.iskeyword(token.string):
                    css = "k"
                elif previous in ("def", "class"):
                    css = "f"
                elif token.string in BUILTINS:
                    css = "b"
        pieces.append(f'<span class="{css}">{text}</span>' if css else text)
        previous = token.string
        cursor = end
    pieces.append(html.escape(source[cursor:]))
    return "".join(pieces)


def excerpt(source: str, names: list[str]) -> str:
    """The top-level definitions called ``names`` (functions, classes, assignments) with the comments above them."""
    lines = source.splitlines()
    tree = ast.parse(source)
    wanted = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            label = node.name
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            label = getattr(target, "id", None)
            first = node.lineno
        else:
            continue
        if label in names:
            while first > 1 and lines[first - 2].lstrip().startswith("#"):
                first -= 1
            wanted.append((label, first, node.end_lineno))
    missing = set(names) - {label for label, *_ in wanted}
    if missing:
        raise SystemExit(f"examples: no top-level definition called {', '.join(sorted(missing))}")
    return "\n\n\n".join("\n".join(lines[first - 1:last]) for _, first, last in wanted) + "\n"


def code_card(source: str, title: str, *, lang: str = "python") -> str:
    body = highlight(source.rstrip("\n")) if lang == "python" else html.escape(source.rstrip("\n"))
    return (
        f'<figure class="code"><figcaption><span>{html.escape(title)}</span>'
        f'<button type="button" class="copy" aria-label="Copy the code">Copy</button></figcaption>'
        f'<pre><code>{body}</code></pre></figure>'
    )


def example_block(spec: str) -> str:
    name, _, selection = spec.removeprefix("example:").partition("#")
    source = (EXAMPLES / name).read_text(encoding="utf-8").replace("\r\n", "\n")
    lang = "python" if name.endswith(".py") else "text"
    if selection:
        return code_card(excerpt(source, selection.split(",")), f"examples/{name}  (excerpt)", lang=lang)
    return code_card(source, f"examples/{name}", lang=lang)


# ---- the serve() reference --------------------------------------------------------------------------------------

def _prose(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(r"``([^`]+)``", r"<code>\1</code>", escaped)


def _entry_html(first_line: str, rest: list[str]) -> str:
    """One docstring entry as paragraphs; lines indented four extra spaces are a code block."""
    blocks: list[tuple[str, list[str]]] = [("p", [first_line.strip()])] if first_line.strip() else []
    for line in rest:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        kind = "pre" if indent >= 12 else "p"
        if not stripped:
            if blocks and blocks[-1][0] == "p":
                blocks.append(("p", []))
            continue
        if blocks and blocks[-1][0] == kind:
            blocks[-1][1].append(stripped if kind == "p" else line[12:])
        else:
            blocks.append((kind, [stripped if kind == "p" else line[12:]]))
    out = []
    for kind, content in blocks:
        if not content:
            continue
        if kind == "pre":
            out.append(f"<pre>{html.escape(chr(10).join(content).rstrip())}</pre>")
        else:
            out.append(f"<p>{_prose(' '.join(content))}</p>")
    return "".join(out)


def serve_reference() -> str:
    import ragevalkit

    fn = ragevalkit.serve
    doc_lines = inspect.getdoc(fn).splitlines()
    args_at = doc_lines.index("Args:")
    entries: dict[str, str] = {}
    name, first, rest = None, "", []
    for line in doc_lines[args_at + 1:]:
        found = re.match(r"^    (\w+): ?(.*)$", line)
        if found:
            if name:
                entries[name] = _entry_html(first, rest)
            name, first, rest = found.group(1), found.group(2), []
        elif name:
            rest.append(line)
    entries[name] = _entry_html(first, rest)

    groups: dict[str, str] = {}
    current = "Your function"
    for line in inspect.getsource(fn).splitlines():
        if line.strip().startswith(") ->"):
            break
        comment = re.match(r"^\s+# --- (.+?) ---", line)
        if comment:
            current = comment.group(1)
            continue
        param = re.match(r"^\s{4}(\w+):", line)
        if param:
            groups[param.group(1)] = current

    params = inspect.signature(fn).parameters
    absent = [p for p in params if p not in entries]
    if absent:
        raise SystemExit(f"serve(): no docstring entry for {', '.join(absent)}")

    order: dict[str, list[str]] = {}
    for param in params:
        order.setdefault(groups.get(param, "Your function"), []).append(param)
    tables = []
    for group, names in order.items():
        rows = []
        for param in names:
            default = params[param].default
            shown = "required" if default is inspect.Parameter.empty else html.escape(f'"{default}"' if isinstance(default, str) else repr(default))
            rows.append(f'<tr><td><code>{param}</code></td><td><code>{shown}</code></td><td>{entries[param]}</td></tr>')
        tables.append(
            f'<h3>{html.escape(group.capitalize())}</h3><div class="table-wrap"><table>'
            f'<thead><tr><th>Parameter</th><th>Default</th><th>What it does</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        )
    return "\n".join(tables)


# ---- the page ---------------------------------------------------------------------------------------------------

def _resolve(text: str) -> str:
    import ragevalkit

    def fill(match: re.Match) -> str:
        key = match.group(1)
        if key == "serve_reference":
            return serve_reference()
        if key == "version":
            return ragevalkit.__version__
        return example_block(key)

    return MARKER.sub(fill, text)


def _page_meta(source: str) -> tuple[dict, str]:
    """The ``key: value`` lines of the comment that opens a page, and the page without it."""
    match = re.match(r"\s*<!--(.*?)-->\s*", source, re.S)
    if not match:
        raise SystemExit("a guide page must start with a <!-- part: ... title: ... lead: ... --> comment")
    meta = dict(line.split(":", 1) for line in match.group(1).strip().splitlines() if ":" in line)
    return {key.strip(): value.strip() for key, value in meta.items()}, source[match.end():]


def _plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def _pages() -> list[dict]:
    pages = []
    for path in sorted((GUIDE_SOURCE / "pages").glob("*.html")):
        meta, body = _page_meta(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
        slug = re.sub(r"^\d+-", "", path.stem)
        for needed in ("part", "title", "lead"):
            if needed not in meta:
                raise SystemExit(f"{path.name}: the opening comment needs {needed}:")
        pages.append({"slug": slug, "body": body, **meta})
    return pages


def _render_page(page: dict, previous: dict | None, following: dict | None) -> str:
    def pager_link(target: dict | None, label: str, css: str) -> str:
        if target is None:
            return '<span class="blank"></span>'
        return f'<a class="{css}" href="#/{target["slug"]}"><small>{label}</small><b>{_plain(target["title"])}</b></a>'

    minutes = page.get("minutes", "")
    kicker = f"<span>{html.escape(page['part'])}</span>" + (f"<span>{html.escape(minutes)} min read</span>" if minutes not in ("", "0") else "")
    return (
        f'<article class="page" id="page-{page["slug"]}" data-slug="{page["slug"]}" data-title="{html.escape(_plain(page["title"]))}" '
        f'data-part="{html.escape(page["part"])}" hidden>\n'
        f'<div class="kicker">{kicker}</div>\n<h1>{page["title"]}</h1>\n<p class="lead">{page["lead"]}</p>\n'
        f'{page["body"]}\n'
        f'<nav class="pager">{pager_link(previous, "Previous", "prev")}{pager_link(following, "Next up", "next")}</nav>\n</article>'
    )


def _nav(pages: list[dict]) -> str:
    out, part = [], None
    for page in pages:
        if page["part"] != part:
            part = page["part"]
            out.append(f'<div class="nav-part">{html.escape(part)}</div>')
        out.append(f'<a class="nav-link" href="#/{page["slug"]}" data-slug="{page["slug"]}"><span class="dot"></span>{_plain(page["title"])}</a>')
    return "\n".join(out)


def build() -> str:
    pages = _pages()
    rendered = [
        _render_page(page, pages[i - 1] if i else None, pages[i + 1] if i + 1 < len(pages) else None)
        for i, page in enumerate(pages)
    ]
    shell = (GUIDE_SOURCE / "shell.html").read_text(encoding="utf-8").replace("\r\n", "\n")
    shell = shell.replace("{{nav}}", _nav(pages)).replace("{{pages}}", "\n".join(rendered))
    return _resolve(shell)


def main() -> None:
    OUTPUT.write_text(build(), encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
