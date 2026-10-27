"""Reading the JSON a model replies with."""
import json


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
