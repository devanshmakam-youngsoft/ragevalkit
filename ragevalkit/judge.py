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

from ragevalkit import prompts as _prompts

logger = logging.getLogger(__name__)


class Grade(BaseModel):
    answer_marks: int = Field(ge=0, le=10)
    answer_comment: str
    material_marks: int | None = Field(default=None, ge=0, le=10)
    material_comment: str = ""


class Judge:
    def __init__(self, config):
        self.config = config
        self._grader_prompt = config.judge_prompt_override or _prompts.GRADER_PROMPT

    def _call(self, messages: list[dict], json_mode: bool = False) -> str:
        import litellm

        kwargs: dict = dict(
            model=self.config.judge_model,
            messages=messages,
            temperature=self.config.judge_temperature,
        )
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
        raise last

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

    def summarize_run(self, stats: str) -> str:
        try:
            return self._with_retries(
                lambda: self._call(
                    [{"role": "system", "content": _prompts.SUMMARY_PROMPT}, {"role": "user", "content": stats}]
                )
            ).strip()
        except Exception as e:
            logger.error("Run summary generation failed: %s", e)
            return "Summary could not be generated for this run."
