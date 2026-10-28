"""Running ragevalkit for a team: accounts, where things are kept, models, and how the recommendation decides."""
import os

import ragevalkit


def answer_question(question: str) -> str:
    return "Refunds are allowed within 30 days of purchase."


if __name__ == "__main__":
    ragevalkit.serve(
        answer_question,
        # --- where it runs and where things are kept ---
        port=8002,
        store_path="evals/eval_store.json",      # results; copy this file to back it up
        log_dir="evals/logs",                    # default: eval_logs next to the store
        # --- who may open it ---
        users="alice:pw-for-alice,bob:pw-for-bob",
        secret=os.environ.get("EVAL_SECRET", "change-me"),   # fixed, so people stay signed in across restarts
        # --- models ---
        judge_model="openai/gpt-4o-mini",
        generator_model="ollama/llama3",         # writes test cases from documents: the text stays on this machine
        # --- how the recommendation decides ---
        answer_weight=0.7,                       # answer quality counts for 70%...
        material_weight=0.3,                     # ...and context quality for 30%
        recommendation_tolerance=0.2,            # versions this close to the best are tied: the fastest wins
        max_response_time=8.0,                   # versions slower than this (seconds) are never recommended
        source_check_mode="keyword",
        show_guide=True,                         # the Help page
        open_browser=False,
    )
