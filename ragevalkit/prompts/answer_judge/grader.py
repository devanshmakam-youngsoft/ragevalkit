"""The instructions that make the judge grade an answer: the rubric (replaceable) and the reply format (always added)."""
from ragevalkit.prompts.answer_judge.remark_tags import (
    ANSWER_TAGS,
    MATERIAL_TAGS,
    MAX_TAGS_PER_SCORE,
)

grader_prompt = """You are a strict but fair evaluator of an AI assistant or RAG system.
You receive a Question, the Expected Answer (written by a human), the system's Generated Answer, and the
Material (document excerpts or context) the system retrieved.

Wording may differ from the expected answer; judge meaning, not phrasing.

answer_marks (integer 0-10): how well the Generated Answer matches the Expected Answer in facts and intent.
  10 = fully correct and complete; 7-9 = correct with minor omissions/extra detail; 4-6 = partially correct;
  1-3 = mostly wrong or missing the key point; 0 = wrong, hallucinated, empty, or generation failed.
  Penalise facts that are not supported by the Material (hallucination) or that contradict the Expected Answer.
  If the Expected Answer describes a behaviour (e.g. greet politely, decline off-topic), judge that behaviour.

material_marks (integer 0-10, or null): does the Material contain enough information to support the Expected
  Answer? 10 = everything needed is present; 5 = some of it; 0 = nothing relevant. Use null when no material
  applies (conversational / off-topic replies where no retrieval is expected)."""


# Appended to the grading prompt whether or not the developer replaced the rubric above, so a custom rubric only
# has to say how to grade and the reply can always be read.
def _word_list(vocabulary: dict) -> str:
    return "\n".join(f"    {key}: {meaning}" for key, (_, _, meaning) in vocabulary.items())


grader_format = f"""

Respond ONLY with a JSON object with these exact keys:
  answer_marks (integer 0-10), answer_comment, answer_tags,
  material_marks (integer 0-10, or null), material_comment, material_tags

Give a one or two sentence comment for each score.

answer_tags: a list of 1 to {MAX_TAGS_PER_SCORE} words from this list that say briefly why the answer got its mark:
{_word_list(ANSWER_TAGS)}
material_tags: a list of 0 to {MAX_TAGS_PER_SCORE} words from this list that say briefly why the material got its mark
(an empty list when material_marks is null):
{_word_list(MATERIAL_TAGS)}
Use only the words in these lists, written exactly as shown."""
