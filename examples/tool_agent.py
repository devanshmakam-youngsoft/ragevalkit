"""An agent that loops: the model asks for a tool, gets the result, and decides again until it can answer."""
import ragevalkit

ORDERS = {"A100": "shipped on 12 March", "A200": "still being packed"}
RETURN_POLICY = "Items can be returned within 30 days."
MAX_TURNS = 5


def lookup_order(order_id: str) -> str:
    return f"Order {order_id} {ORDERS.get(order_id, 'was not found')}."


def lookup_policy(topic: str) -> str:
    return RETURN_POLICY


TOOLS = {"lookup_order": lookup_order, "lookup_policy": lookup_policy}


def model(question: str, results: list[str]) -> dict:
    """Stand-in for the LLM call: asks for the tools it needs, then writes the answer from what they returned."""
    if "order" in question.lower() and not any(r.startswith("Order") for r in results):
        return {"tool": "lookup_order", "argument": question.rstrip("?").split()[-1]}
    if "return" in question.lower() and RETURN_POLICY not in results:
        return {"tool": "lookup_policy", "argument": "returns"}
    return {"answer": " ".join(results) or "I can help with orders and returns."}


def support_agent(question: str) -> str:
    results: list[str] = []
    tools_used: list[str] = []
    for _ in range(MAX_TURNS):
        with ragevalkit.step("llm"):                      # runs once per loop: its times are added up
            decision = model(question, results)
        if "answer" in decision:
            return decision["answer"]
        with ragevalkit.step(decision["tool"]) as s:      # one step per tool, named after the tool
            result = TOOLS[decision["tool"]](decision["argument"])
            s.material = result                           # the tool results are this agent's "retrieved context"
        results.append(result)
        tools_used.append(decision["tool"])
        ragevalkit.note("tools_used", ", ".join(tools_used))     # shown next to the question in the results
    return "Sorry, I could not finish that."


if __name__ == "__main__":
    ragevalkit.serve(support_agent)
