"""
LLM-as-judge — scores each generated answer against the expected answer.

WHY LiteLLM?
  A single unified API for Groq, Gemini, OpenAI, Ollama, etc.
  The developer changes one string ("groq/..." → "gemini/...") to switch
  providers; no SDK swapping, no credential rework.

WHY json_mode with a prompt-level instruction as fallback?
  Some providers (e.g. older Groq models) reject `response_format` entirely
  and throw an error. The try/except lets the prompt-level "Respond ONLY with
  a JSON object" instruction serve as a silent fallback so grading still works.

WHY Grade is a Pydantic model?
  `json.loads(raw)` gives a dict but doesn't validate types or ranges.
  Grade(...) enforces answer_marks ∈ [0,10] and rejects garbage responses
  before they corrupt the results store.  If the LLM returns bad JSON the
  retry loop (_with_retries) tries again rather than storing broken data.
"""
import json
import logging
import time

from pydantic import BaseModel, Field

from ragevalkit import litellm_loader
from ragevalkit import prompts as _prompts
from ragevalkit.exceptions import JudgeError

logger = logging.getLogger(__name__)


class Grade(BaseModel):
    answer_marks: int = Field(ge=0, le=10)
    answer_comment: str
    material_marks: int | None = Field(default=None, ge=0, le=10)
    material_comment: str = ""


class SourceCheckResult(BaseModel):
    """Outcome of an LLM source check, resolved against the AND/OR groups in expected_sources."""
    source_match: bool
    matched_sources: list[str] = []   # one retrieved alternative per satisfied group
    missing_sources: list[str] = []   # the full group string for each unsatisfied group
    source_score: int = Field(ge=0, le=10)
    source_comment: str = ""


def _clean_items(value, limit: int = 6) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    items = [str(v).strip().lstrip("-•* ").strip() for v in value if str(v).strip()]
    return [i[:400] for i in items][:limit]


def parse_insights(raw: str | None) -> dict | None:
    """Read the model's {"pitfalls": [...], "suggestions": [...]} reply, tolerating code fences and
    surrounding prose. Returns None when it holds neither list."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start:end + 1])
        except ValueError:
            return None
    if not isinstance(data, dict):
        return None
    pitfalls, suggestions = _clean_items(data.get("pitfalls")), _clean_items(data.get("suggestions"))
    if not pitfalls and not suggestions:
        return None
    return {"pitfalls": pitfalls, "suggestions": suggestions}


class Judge:
    def __init__(self, config):
        self.config = config
        self._grader_prompt = config.judge_prompt_override or _prompts.GRADER_PROMPT

    def _call(self, messages: list[dict], json_mode: bool = False) -> str:
        litellm = litellm_loader.load()

        kwargs: dict = dict(
            model=self.config.judge_model,
            messages=messages,
        )
        if self.config.judge_temperature is not None:
            kwargs["temperature"] = self.config.judge_temperature
        if self.config.judge_api_key:
            kwargs["api_key"] = self.config.judge_api_key
        if json_mode:
            try:
                kwargs["response_format"] = {"type": "json_object"}
            except Exception:
                pass  # provider may not support it; prompt-level instruction serves as fallback
        resp = litellm.completion(**kwargs)
        return resp.choices[0].message.content

    def _with_retries(self, fn):
        last = None
        for attempt in range(self.config.judge_retries):
            try:
                return fn()
            except Exception as e:
                last = e
                logger.warning("Judge call failed (attempt %d): %s", attempt + 1, e)
                time.sleep(2 * (attempt + 1))
        raise JudgeError(f"Judge failed after {self.config.judge_retries} attempts: {last}") from last

    def grade(
        self, question: str, expected: str, generated: str | None, material: str, material_applicable: bool
    ) -> Grade:
        user = (
            f"Question: {question}\n\nExpected Answer: {expected}\n\n"
            f"Generated Answer: {generated or 'Generation failed (no answer returned)'}\n\n"
            f"Material:\n{material.strip() or 'No material was retrieved.'}\n\n"
            f"Material applicable: {'yes' if material_applicable else 'no (conversational turn, use null)'}"
        )
        system = self._grader_prompt

        def _invoke():
            raw = self._call(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                json_mode=True,
            )
            data = json.loads(raw)
            return Grade(**data)

        grade: Grade = self._with_retries(_invoke)
        if not material_applicable:
            grade.material_marks = None
            grade.material_comment = "Not applicable (no retrieval expected)."
        return grade

    def check_sources(self, groups: list[list[str]], recorded: list[str]) -> SourceCheckResult:
        """Check retrieved sources against AND-groups of OR-alternatives.

        The LLM only decides which individual expected sources were retrieved; the group
        logic (every group needs at least one retrieved alternative) is applied here so
        ``source_match`` and ``source_score`` are deterministic.
        """
        alternatives = list(dict.fromkeys(alt for group in groups for alt in group))
        recorded_str = "\n".join(f"- {r}" for r in recorded) if recorded else "None retrieved."
        expected_str = "\n".join(f"- {e}" for e in alternatives)
        user = f"Expected sources:\n{expected_str}\n\nRetrieved sources:\n{recorded_str}"

        def _invoke():
            raw = self._call(
                [{"role": "system", "content": _prompts.SOURCE_CHECK_PROMPT},
                 {"role": "user", "content": user}],
                json_mode=True,
            )
            return json.loads(raw)

        data = self._with_retries(_invoke)
        retrieved = {str(s).strip().lower() for s in data.get("matched_sources") or []}

        matched: list[str] = []
        missing: list[str] = []
        for group in groups:
            hit = next((alt for alt in group if alt.lower() in retrieved), None)
            if hit:
                matched.append(hit)
            else:
                missing.append(" , ".join(group))
        return SourceCheckResult(
            source_match=not missing,
            matched_sources=matched,
            missing_sources=missing,
            source_score=round(10 * len(matched) / len(groups)) if groups else 0,
            source_comment=str(data.get("source_comment") or ""),
        )

    def summarize_run(self, stats: str) -> dict | None:
        """Pitfalls and suggestions for a finished run: ``{"pitfalls": [...], "suggestions": [...]}``,
        or None if the summary could not be generated."""
        system = (self.config.summary_prompt or _prompts.SUMMARY_PROMPT) + _prompts.SUMMARY_FORMAT

        def _invoke():
            raw = self._call(
                [{"role": "system", "content": system}, {"role": "user", "content": stats}],
                json_mode=True,
            )
            insights = parse_insights(raw)
            if insights is None:
                raise ValueError("summary was not valid JSON with pitfalls / suggestions")
            return insights

        try:
            return self._with_retries(_invoke)
        except Exception as e:
            logger.error("Run summary generation failed: %s", e)
            return None
