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

from ragevalkit.judging.exceptions import JudgeError
from ragevalkit.judging.insights import check_insights, parse_insights
from ragevalkit.judging.prompts import (
    grader_prompt,
    run_summary_format,
    run_summary_prompt,
    source_check_prompt,
)
from ragevalkit.judging.schemas import Grade, SourceCheckResult
from ragevalkit.llm import complete

logger = logging.getLogger(__name__)


class Judge:
    def __init__(self, config):
        self.config = config
        self._grader_prompt = config.judge_prompt_override or grader_prompt

    def _call(self, messages: list[dict], json_mode: bool = False) -> str:
        return complete(
            messages, model=self.config.judge_model, api_key=self.config.judge_api_key,
            temperature=self.config.judge_temperature, json_mode=json_mode,
        )

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
                [{"role": "system", "content": source_check_prompt},
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
        """Findings for a finished run: ``{"items": [{"watch_out", "suggestion"}, ...], "pitfalls": [...], "suggestions": [...]}``,
        every watch-out paired with the suggestion that answers it (the two lists repeat the pairs' parts).

        A reply that is not usable (not JSON, or one of the lists empty) is sent back with the reason so the model
        can fix it, up to ``judge_retries`` times (at least twice). If the model never fills both lists, what it did
        give is returned (the caller can add the missing suggestions); None only when nothing usable came back."""
        system = (self.config.summary_prompt or run_summary_prompt) + run_summary_format
        messages = [{"role": "system", "content": system}, {"role": "user", "content": stats}]
        attempts = max(2, self.config.judge_retries)
        partial: dict | None = None
        problem = "no reply"
        for attempt in range(attempts):
            try:
                raw = self._call(messages, json_mode=True)
            except Exception as e:  # network, rate limit, provider error
                problem = f"the model could not be reached: {e}"
                logger.warning("Run summary call failed (attempt %d): %s", attempt + 1, e)
                time.sleep(2 * (attempt + 1))
                continue
            insights, problem = check_insights(raw)
            if insights is not None:
                return insights
            partial = parse_insights(raw) or partial
            logger.warning("Run summary reply rejected (attempt %d): %s", attempt + 1, problem)
            messages = messages + [
                {"role": "assistant", "content": raw or ""},
                {"role": "user", "content": f"That reply was rejected: {problem}. Reply again with JSON only, in the required shape."},
            ]
        if partial is not None:
            logger.warning("Run summary incomplete after %d attempts (%s); using what the model gave", attempts, problem)
            return partial
        logger.error("Run summary generation failed: %s", problem)
        return None
