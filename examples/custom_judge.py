"""Replace the AI judge with your own function. It receives the question, the expected answer, the generated answer
and the retrieved material, and returns the marks (0 to 10) with an optional comment."""
import json

import ragevalkit


def my_pipeline(question: str) -> str:
    return '{"status": "shipped", "eta": "2 days"}'


def contains_expected_answer(question: str, expected: str, generated: str, material: str) -> dict:
    """The simplest judge: full marks when the expected answer appears in the generated one."""
    found = expected.strip().lower() in (generated or "").lower()
    return {
        "answer_marks": 10 if found else 0,
        "answer_comment": "Contains the expected answer." if found else "The expected answer is missing.",
    }


def valid_json_with_fields(question: str, expected: str, generated: str, material: str) -> dict:
    """For a bot that must reply with JSON. The test case's expected answer lists the fields: "status, eta"."""
    try:
        reply = json.loads(generated)
    except (TypeError, ValueError):
        return {"answer_marks": 0, "answer_comment": "The reply is not valid JSON."}
    needed = [name.strip() for name in expected.split(",") if name.strip()]
    missing = [name for name in needed if name not in reply]
    marks = round(10 * (len(needed) - len(missing)) / len(needed)) if needed else 10
    return {
        "answer_marks": marks,
        "answer_comment": f"Missing fields: {', '.join(missing)}." if missing else "All required fields are present.",
    }


def grade_answer_and_context(question: str, expected: str, generated: str, material: str) -> dict:
    """Also grade the retrieved text: add material_marks (or leave it out for a bot with no retrieval)."""
    answer_ok = expected.lower() in (generated or "").lower()
    context_ok = expected.lower() in (material or "").lower()
    return {
        "answer_marks": 10 if answer_ok else 2,
        "answer_comment": "Correct." if answer_ok else "Does not state the expected answer.",
        "material_marks": 10 if context_ok else 0,
        "material_comment": "The retrieved text contains the answer." if context_ok else "The answer is not in the retrieved text.",
    }


if __name__ == "__main__":
    ragevalkit.serve(my_pipeline, judge_fn=valid_json_with_fields)
