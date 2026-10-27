"""Putting the rules, the passages and the questions already written into the messages sent to the model."""
from __future__ import annotations

from ragevalkit.generation.planning import Task
from ragevalkit.generation.prompts import CATEGORY_PROMPTS, common_rules


def system_prompt(category: str, turns: int) -> str:
    return common_rules + "\n\n" + CATEGORY_PROMPTS[category].replace("{turns}", str(turns))


def build_messages(task: Task, turns: int, avoid: list[str]) -> list[dict]:
    """The conversation sent to the model for one task: the rules, the passages, and what is already written."""
    parts = [f"[Passage {'AB'[i]}] ({c.label})\n" + "\n".join(f"[{'AB'[i]}{n}] {s}" for n, s in enumerate(c.sentences, 1))
             for i, c in enumerate(task.chunks[:2])]
    user = "\n\n".join(parts)
    if avoid:
        user += "\n\nQuestions already written (do not repeat or closely resemble them):\n" + "\n".join(f"- {q}" for q in avoid[-12:])
    return [{"role": "system", "content": system_prompt(task.category, turns)}, {"role": "user", "content": user}]
