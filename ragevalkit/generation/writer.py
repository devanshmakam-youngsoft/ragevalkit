"""Writing one item: ask, check, and ask again with the reason until it passes."""
from __future__ import annotations

import logging
import time
from typing import Callable

from ragevalkit.generation.exceptions import GenerationError
from ragevalkit.generation.checks import validate
from ragevalkit.generation.reply_parser import parse_reply
from ragevalkit.generation.planning import Task
from ragevalkit.generation.prompts import retry_instruction
from ragevalkit.generation.message_builder import build_messages

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


def generate_item(task: Task, llm: Callable, *, turns: int, avoid: list[str], sleep: Callable | None = None) -> dict:
    """One finished item for a task, retrying with the reason whenever the model's reply is rejected.

    Raises GenerationError with the last reason when every attempt fails."""
    sleep = sleep or time.sleep
    messages = build_messages(task, turns, avoid)
    reason = "no reply"
    for attempt in range(MAX_ATTEMPTS):
        try:
            raw = llm(messages)
        except Exception as e:  # network, rate limit, provider error
            reason = f"the model could not be reached: {e}"
            logger.warning("generation call failed (attempt %d): %s", attempt + 1, e)
            sleep(1.5 * (attempt + 1))
            continue
        checked, reason = validate(task, parse_reply(raw), turns=turns, avoid=avoid)
        if checked is not None:
            return {"category": task.category, "file": task.doc, "number": task.number, "turns": checked}
        messages = messages + [
            {"role": "assistant", "content": raw or ""},
            {"role": "user", "content": retry_instruction.format(reason=reason)},
        ]
    raise GenerationError(reason)
