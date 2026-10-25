"""Talking to the model."""
from __future__ import annotations

import json
import threading

# errors that mean "this provider's JSON mode does not like this", after which asking without it is worth a try
_JSON_MODE_ERRORS = ("response_format", "json_validate_failed", "failed to validate json", "json mode", "json_object")


_import_lock = threading.Lock()


def _litellm():
    """The litellm module. Importing it takes seconds, and several writer threads asking at once deadlock on the
    half-loaded module ("no attribute 'completion'"), so the first import happens under a lock."""
    with _import_lock:
        import litellm
    return litellm


class LiteLLM:
    """The configured model: ``generator_model`` if set, otherwise the judge's model, through LiteLLM."""

    def __init__(self, config):
        self.config = config

    @property
    def model(self) -> str:
        return self.config.generator_model or self.config.judge_model

    def __call__(self, messages: list[dict]) -> str:
        litellm = _litellm()
        kwargs: dict = dict(model=self.model, messages=messages, response_format={"type": "json_object"})
        if self.config.judge_api_key:
            kwargs["api_key"] = self.config.judge_api_key
        try:
            resp = litellm.completion(**kwargs)
        except Exception as e:
            if not any(key in str(e).lower() for key in _JSON_MODE_ERRORS):
                raise
            # this provider has no JSON mode, or its JSON mode rejected the output (Groq: "Failed to validate JSON"):
            # ask again without it. The prompt already requires JSON and the reply is parsed leniently.
            kwargs.pop("response_format")
            resp = litellm.completion(**kwargs)
        return resp.choices[0].message.content


def parse_reply(raw: str | None) -> dict | None:
    """The JSON object in a model's reply, tolerating code fences and chatter around it. None if there is none."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    for candidate in (text, text[text.find("{"): text.rfind("}") + 1] if "{" in text else ""):
        try:
            data = json.loads(candidate)
            return data if isinstance(data, dict) else None
        except ValueError:
            continue
    return None
