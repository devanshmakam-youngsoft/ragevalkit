"""The one place a model is called: ``complete()``, shared by the judge and the test case writer."""
from __future__ import annotations

import logging

from ragevalkit.llm.loader import load_litellm

logger = logging.getLogger(__name__)


# errors that mean "this provider's JSON mode does not like this", after which asking without it is worth a try
JSON_MODE_ERRORS = ("response_format", "json_validate_failed", "failed to validate json", "json mode", "json_object")


def complete(messages: list[dict], *, model: str, api_key: str | None = None, temperature: float | None = None,
             json_mode: bool = False) -> str:
    """One model call, returning the reply text. With ``json_mode`` the provider is asked for a JSON object; one that
    has no JSON mode, or whose JSON mode rejects the output (Groq: "Failed to validate JSON"), is asked again without
    it. The prompts already require JSON and replies are read leniently, so the retry costs nothing in quality."""
    litellm = load_litellm()
    kwargs: dict = dict(model=model, messages=messages)
    if temperature is not None:
        kwargs["temperature"] = temperature
    if api_key:
        kwargs["api_key"] = api_key
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = litellm.completion(**kwargs)
    except Exception as e:
        if not (json_mode and any(key in str(e).lower() for key in JSON_MODE_ERRORS)):
            raise
        logger.info("%s rejected JSON mode (%s); asking again without it", model, str(e).splitlines()[0][:160])
        kwargs.pop("response_format")
        resp = litellm.completion(**kwargs)
    return resp.choices[0].message.content
