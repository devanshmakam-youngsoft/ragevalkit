"""The evaluation entry point: run `python eval_entry.py` when you want to evaluate. Production never runs this file."""
import ragevalkit

from shared_pipeline import answer_question

if __name__ == "__main__":
    ragevalkit.serve(answer_question, port=8002, require_login=False)
