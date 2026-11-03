"""The fixed words the judge uses to say, in a few words, why an answer or its context got its mark.

Each entry is ``key: (label shown in the dashboard, tone, what the judge should mean by it)``. The tone colours the label:
``good``, ``warn`` or ``bad``. A fixed list keeps the wording the same from run to run, so the tags can be counted and filtered.
"""

ANSWER_TAGS: dict[str, tuple[str, str, str]] = {
    "correct": ("Correct", "good", "fully correct and complete"),
    "minor_gaps": ("Minor gaps", "good", "correct, with small omissions or harmless extra detail"),
    "incomplete": ("Incomplete", "warn", "right as far as it goes, but a key part of the expected answer is missing"),
    "partly_correct": ("Partly correct", "warn", "some of it matches the expected answer and some of it does not"),
    "wrong": ("Wrong answer", "bad", "contradicts the expected answer or misses its main point"),
    "made_up": ("Made-up detail", "bad", "states facts that the Material does not support"),
    "off_topic": ("Off topic", "bad", "does not address the question, or shows the wrong behaviour"),
    "no_answer": ("No answer", "bad", "empty, a refusal where an answer was needed, or generation failed"),
}

MATERIAL_TAGS: dict[str, tuple[str, str, str]] = {
    "complete": ("Context complete", "good", "everything needed to answer is present"),
    "partial": ("Context partial", "warn", "only some of what is needed is present"),
    "key_missing": ("Key text missing", "bad", "the text that holds the answer is not there"),
    "irrelevant": ("Irrelevant context", "bad", "the text is about something else"),
    "noisy": ("Too much noise", "warn", "the answer is in there but buried in unrelated text"),
    "empty": ("Nothing retrieved", "bad", "no material was returned"),
}

MAX_TAGS_PER_SCORE = 2
