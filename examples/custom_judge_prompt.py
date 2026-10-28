"""Keep the AI judge but change how it grades: your own rubric, your own model, your own wording for the findings."""
import ragevalkit


def support_bot(question: str) -> str:
    return "You can return items within 30 days. Would you like me to start a return?"


# Only describe HOW to grade. ragevalkit adds the reply format (the JSON with answer_marks and the comments) itself.
SUPPORT_RUBRIC = """You grade replies from a customer-support assistant for an online shop.
You receive the customer's question, the reply the support team wrote as the expected answer, and the assistant's reply.

answer_marks (0-10):
  10 = states the same facts and the same next step as the expected reply, politely.
  7-9 = correct but missing a small detail or slightly curt.
  4-6 = partly right, or right but rude or confusing.
  0-3 = wrong policy, invented facts, or no help at all.
Never reward a long reply for being long. A reply that promises something the expected reply does not (a refund, a
discount) gets at most 3.
material_marks: use null, this assistant does not retrieve documents."""

# What the AI-written findings of a run should look at. The reply format is added for you here too.
SUMMARY_FOCUS = """You are reviewing one test run of a customer-support assistant for the support manager.
Point out which kinds of questions went worst and what to change in the assistant's instructions. Mention promises
the assistant made that the policy does not allow. Plain language, no technical terms."""


if __name__ == "__main__":
    ragevalkit.serve(
        support_bot,
        judge_model="openai/gpt-4o-mini",      # any LiteLLM model: "groq/...", "gemini/...", "ollama/llama3", ...
        judge_prompt=SUPPORT_RUBRIC,
        summary_prompt=SUMMARY_FOCUS,
        material_weight=0,                     # nothing is retrieved, so the recommendation uses answer quality only
    )
