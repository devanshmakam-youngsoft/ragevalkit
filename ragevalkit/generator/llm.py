"""Talking to the model."""
from __future__ import annotations

import json

from ragevalkit import litellm_loader


class LiteLLM:
    """The configured model: ``generator_model`` if set, otherwise the judge's model, through LiteLLM."""

    def __init__(self, config):
        self.config = config

    @property
    def model(self) -> str:
        return self.config.generator_model or self.config.judge_model

    def __call__(self, messages: list[dict]) -> str:
        return litellm_loader.complete(messages, model=self.model, api_key=self.config.judge_api_key, json_mode=True)


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
