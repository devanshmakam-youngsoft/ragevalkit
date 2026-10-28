"""A bot with no retrieval (greetings, small talk, a tool that looks up orders). There is no "context" to score."""
import ragevalkit

ORDERS = {"A100": "shipped", "A200": "still being packed"}


def classify(question: str) -> str:
    text = question.lower()
    if "hello" in text or "thanks" in text:
        return "greeting"
    if "order" in text:
        return "order_status"
    return "other"


def support_bot(question: str) -> str:
    with ragevalkit.step("intent"):                        # timing only: nothing here is retrieved text
        intent = classify(question)
    ragevalkit.note("intent", intent)                      # shown next to the question in the results

    if intent == "greeting":
        return "Hello! How can I help you today?"

    if intent == "order_status":
        with ragevalkit.step("order_lookup"):              # a tool call: timing only
            order_id = question.rstrip("?").split()[-1]
            status = ORDERS.get(order_id, "not found")
        ragevalkit.note("tool_called", "order_lookup")
        return f"Order {order_id} is {status}."

    return "Sorry, I can only help with orders."


if __name__ == "__main__":
    # material_weight=0: the recommendation looks at answer quality only, because there is no context to score.
    ragevalkit.serve(support_bot, material_weight=0)
