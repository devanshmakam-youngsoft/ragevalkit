"""Builds ragevalkit/guides/developer-guide.html from docs/guide.template.html.

The guide's code comes from the files in examples/ (which the tests run), and its serve() reference comes from the
function itself, so neither can drift from the library. Run it after changing either:

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

TEMPLATE = ROOT / "docs" / "guide.template.html"
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
    if selection:
        return code_card(excerpt(source, selection.split(",")), f"examples/{name}  (excerpt)")
    return code_card(source, f"examples/{name}")


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

def build() -> str:
    import ragevalkit

    template = TEMPLATE.read_text(encoding="utf-8").replace("\r\n", "\n")

    def fill(match: re.Match) -> str:
        key = match.group(1)
        if key == "serve_reference":
            return serve_reference()
        if key == "version":
            return ragevalkit.__version__
        return example_block(key)

    return MARKER.sub(fill, template)


def main() -> None:
    OUTPUT.write_text(build(), encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
