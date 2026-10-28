"""Extra scores, your own spreadsheet columns, and a hook that runs after every evaluation."""
import ragevalkit


def my_pipeline(question: str) -> str:
    return "Refunds are allowed within 30 days of purchase."


# Extra metrics: each receives (expected_answer, generated_answer) and returns a number. They appear in the results
# next to the built-in scores.
def word_overlap(expected: str, generated: str) -> float:
    """Share of the expected answer's words that appear in the generated answer (0 to 1)."""
    wanted = set(expected.lower().split())
    return len(wanted & set(generated.lower().split())) / len(wanted) if wanted else 0.0


def length_ratio(expected: str, generated: str) -> float:
    """How much longer (or shorter) the answer is than expected: 1.0 means the same length."""
    return len(generated) / len(expected) if expected else 0.0


# on_complete runs once after every evaluation, with the run's summary and its rows (summary is None if the run failed).
def check_quality_gate(summary: dict | None, rows: list[dict]) -> None:
    if summary is None:
        print("The evaluation failed.")
        return
    average = summary["avg_answer_marks"]
    print(f"Version {summary['version']}: answer quality {average} over {len(rows)} questions")
    if average is not None and average < 7:
        print("Below the bar of 7: do not release this version.")   # post to Slack, fail a CI job, write to a database...


if __name__ == "__main__":
    ragevalkit.serve(
        my_pipeline,
        extra_metrics={"word_overlap": word_overlap, "length_ratio": length_ratio},
        on_complete=check_quality_gate,
        column_map={"user_query": "question", "gold_answer": "expected_answer"},   # your column names -> ragevalkit's
        extra_columns=["difficulty"],                                                # carried into every result
        session_id_fn=lambda chat_id: f"eval-{chat_id}",                             # your own session ids
    )
