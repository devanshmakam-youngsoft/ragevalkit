"""Cleaning document text and cutting it into numbered sentences."""
import re

_DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
                         "‘": "'", "’": "'", "“": '"', "”": '"', " ": " ", "­": ""})


def clean(text: str) -> str:
    """Text with the noise models and documents disagree about removed: odd quotes and dashes, line-break
    hyphenation, markdown marks (**bold**, `code`, # headings, > quotes, | tables, list bullets) and spacing."""
    text = (text or "").translate(_DASHES)
    text = re.sub(r"-\s*\n\s*", "", text)                          # "refund-\nable" -> "refundable"
    text = re.sub(r"(?m)^\s*(?:[-*\u2022]|\d+[.)])\s+", "", text)  # list bullets and numbers at the start of a line
    text = re.sub(r"[*`~#>|]+", " ", text)                           # emphasis, code, headings, quotes, table cells
    return re.sub(r"\s+", " ", text).strip()


MIN_SENTENCE_CHARS = 4       # only noise (a stray page number) is left out of the numbering


_BLOCK_START = re.compile(r"^\s*(?:[-*•]\s|\d+[.)]\s|#{1,6}\s|\|)")


_SELF_CONTAINED = re.compile(r"^\s*(?:#{1,6}\s)")        # a heading never runs on into the line after it


_ABBREVIATION = r"(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\betc\.)(?<!\bvs\.)(?<!\bMr\.)(?<!\bMrs\.)(?<!\bDr\.)(?<!\bNo\.)"


_RULE = re.compile(r"[\s|:=_*\-]{3,}")                      # a table's header divider or a horizontal rule


_SENTENCE_END = re.compile(_ABBREVIATION + r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def sentences_of(text: str) -> list[str]:
    """Clean sentences in reading order. Lines are joined (a PDF wraps a sentence over several lines) except
    where a heading or list item starts, which is kept apart; the rows of a table are kept together as one."""
    text = re.sub(r"-\s*\n\s*", "", (text or "").translate(_DASHES))     # "refund-\nable" -> "refundable"
    blocks: list[str] = []
    closed = True                       # whether the last block takes no more lines
    for line in text.splitlines():
        if not line.strip() or _RULE.fullmatch(line):
            continue
        starts = _BLOCK_START.match(line)
        table_row = line.lstrip().startswith("|")
        in_table = bool(blocks) and blocks[-1].lstrip().startswith("|")
        if blocks and not closed and ((not starts and not in_table) or (table_row and in_table)):
            blocks[-1] += " " + line
        else:
            blocks.append(line)
            closed = bool(_SELF_CONTAINED.match(line))
        if starts and not table_row:
            closed = closed or not line[:1].isspace()      # a list item takes only indented continuation lines
    out: list[str] = []
    for block in blocks:
        out.extend(s.strip() for s in _SENTENCE_END.split(clean(block)) if len(s.strip()) >= MIN_SENTENCE_CHARS)
    return out


def normalise(text: str) -> str:
    """``clean`` in lower case: how two pieces of text are compared."""
    return clean(text).lower()
