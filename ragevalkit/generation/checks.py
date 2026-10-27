"""The rules a written question must follow. The model is asked to follow them; this is what makes sure it did.

``validate`` returns the cleaned turns, or the reason the reply was rejected — worded so it can be handed back
to the model for another attempt.
"""
from __future__ import annotations

import re

from ragevalkit.documents.text_cleaning import normalise
from ragevalkit.generation import evidence as evidence_of
from ragevalkit.generation.planning import Task
from ragevalkit.metrics import tokenize

SIMILARITY_LIMIT = 0.75        # two questions this alike count as the same question
RESTATES_LIMIT = 0.6           # a follow-up that repeats this much of the earlier questions is not a follow-up
MIN_DEPENDS_CHARS = 8

# phrases that make a question depend on seeing the document
_NOT_STANDALONE = re.compile(
    r"\b(the|this|that|these|those)\s+(passage|passages|document|text|excerpt|section|paragraph|pdf|file)\b"
    r"|\baccording to (the|this)\b|\bpassage [ab]\b|\bas (stated|mentioned|described) (above|earlier|in)\b|\bprovided (text|context)\b",
    re.I,
)

# how people refer back in a conversation: pronouns, "the same", "the other one". Words that also turn up in
# standalone questions ("above $500", "one of", "the first day") are deliberately not here.
_REFERS_BACK = re.compile(
    r"\b(it|its|it's|they|them|their|theirs|that|those|these|there|then|same|former|latter|previous|earlier|"
    r"instead|otherwise|also|too|as well|the other|the others|that one|this one|this|such|both|either|another|else|rest|mentioned)\b", re.I)
_ELLIPTIC_START = re.compile(r"^\s*(and|but|so|then|also|what about|how about|what if|why|how come|in that case|if so|if not)\b", re.I)


def check_text(question: str, answer: str, *, standalone: bool) -> str | None:
    """Length limits, and (for a question that has to stand alone) no reference to 'the document'."""
    if not 12 <= len(question) <= 400:
        return "the question must be between 12 and 400 characters"
    if not 3 <= len(answer) <= 1200:
        return "the expected answer must be between 3 and 1200 characters"
    if standalone and _NOT_STANDALONE.search(question):
        return 'the question refers to "the passage / document / text"; it must stand on its own'
    return None


def similarity(a: str, b: str) -> float:
    x, y = set(tokenize(a)), set(tokenize(b))
    return len(x & y) / len(x | y) if x | y else 0.0


def _check_indirect(question: str, quotes: list[str], passages: list[str]) -> str | None:
    """An indirect question must not echo the document's wording."""
    joined = " ".join(passages)
    words = normalise(question).split()
    if any(" ".join(words[i:i + 4]) in joined for i in range(len(words) - 3)):
        return "the question copies four or more words in a row from the passages; rephrase it in everyday words"
    q_tokens = set(tokenize(question))
    if q_tokens and len(q_tokens & set(tokenize(" ".join(quotes)))) / len(q_tokens) > RESTATES_LIMIT:
        return "the question uses too many of the evidence's own words; make it more indirect"
    return None


def _check_follow_up(question: str, earlier: list[str]) -> str | None:
    """A follow-up must need the conversation so far: it refers back, and it does not restate the topic."""
    if not (_REFERS_BACK.search(question) or _ELLIPTIC_START.search(question)):
        return (f'this follow-up ("{question}") could be asked on its own, so it is just another direct question; rewrite it so it '
                'depends on the previous answer by referring back to it ("it", "that", "those", "in that case", "and what about ...?") '
                'without naming the topic again')
    q_tokens = set(tokenize(question))
    seen = set(tokenize(" ".join(earlier)))
    if len(q_tokens) >= 4 and len(q_tokens & seen) / len(q_tokens) > RESTATES_LIMIT:
        return 'this follow-up repeats the earlier question\'s words instead of referring back; say "it" or "that" rather than naming the topic again'
    return None


def _depends_on(raw: dict) -> str:
    return str(raw.get("depends_on") or raw.get("relies_on") or raw.get("context") or "").strip()


def _turns_of(task: Task, data: dict, turns: int) -> tuple[list | None, str]:
    raw_turns = data.get("turns") if task.category == "multiturn" else [data]
    if not isinstance(raw_turns, list) or not raw_turns:
        return None, 'the reply must contain "turns" for a conversation' if task.category == "multiturn" else "missing question"
    if task.category == "multiturn" and not 2 <= len(raw_turns) <= max(2, turns):
        return None, f"the conversation must have {turns} turns"
    return raw_turns, ""


def _check_turn(task: Task, raw, index: int, earlier: list[dict], passages: list[str], avoid: list[str]) -> tuple[dict | None, str]:
    """One turn of a reply: (the cleaned turn, "") or (None, the reason it was rejected)."""
    if not isinstance(raw, dict):
        return None, "each turn must be an object with question, expected_answer and evidence"
    question, answer = str(raw.get("question") or "").strip(), str(raw.get("expected_answer") or "").strip()
    problem = check_text(question, answer, standalone=index == 0)
    if problem:
        return None, problem

    proof = evidence_of.extract(evidence_of.raw_evidence(raw), task.chunks)
    if not proof:
        hint = (' Reply with "evidence": ["A2", "B4"]: the numbers of one sentence from each passage.'
                if task.category == "multipart" else ' Reply with "evidence": ["A3"]: the number of the sentence that states the answer.')
        return None, "the evidence does not point at any sentence of the passages; cite sentence numbers exactly as shown, such as A3." + hint
    if task.category == "multipart" and len({e["passage"] for e in proof}) < 2:
        return None, "a multi-part question needs evidence from both Passage A and Passage B"
    if task.category == "indirect":
        problem = _check_indirect(question, [e["quote"] for e in proof], passages)
        if problem:
            return None, problem

    turn = {"question": question, "expected_answer": answer, "evidence": proof}
    if task.category == "multiturn" and index > 0:
        problem = _check_follow_up(question, [t["question"] for t in earlier])
        if problem:
            return None, problem
        needs = _depends_on(raw)
        if len(needs) < MIN_DEPENDS_CHARS:
            return None, 'every follow-up needs "depends_on": one sentence saying what it relies on from the earlier turns'
        turn["needs_context"] = needs

    if any(similarity(question, other) >= SIMILARITY_LIMIT for other in avoid + [t["question"] for t in earlier]):
        return None, "this is too similar to a question already written; ask about something different"
    return turn, ""


def validate(task: Task, data: dict | None, *, turns: int, avoid: list[str]) -> tuple[list[dict] | None, str]:
    """Check one model reply. Returns (turns, "") when it follows every rule, else (None, reason).

    In a conversation the reason names the turn that broke the rule, so the retry can fix just that one."""
    if not data:
        return None, "the reply was not valid JSON in the required shape"
    raw_turns, problem = _turns_of(task, data, turns)
    if raw_turns is None:
        return None, problem
    passages = [normalise(c.text) for c in task.chunks]

    out: list[dict] = []
    for index, raw in enumerate(raw_turns):
        turn, problem = _check_turn(task, raw, index, out, passages, avoid)
        if turn is None:
            return None, f"turn {index + 1}: {problem}" if task.category == "multiturn" else problem
        out.append(turn)
    return out, ""
