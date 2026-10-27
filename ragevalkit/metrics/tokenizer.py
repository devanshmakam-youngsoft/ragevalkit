"""Splitting text into the lower-case words the text metrics compare."""
import re


STOPWORDS = set(
    "a an the and or of to in on for with by at from as is are was were be been being it its this that "
    "these those which who whom will shall may can could should would must not no than then there their "
    "they he she his her you your we our i if but so such any all each other into over under about also "
    "has have had do does did per".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", (text or "").lower()) if t not in STOPWORDS]
