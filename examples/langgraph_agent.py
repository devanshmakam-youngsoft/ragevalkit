"""A LangGraph app. Steps are recorded from inside nodes, whichever way you place them."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

import ragevalkit

DOCUMENTS = {
    "refunds.pdf": "Refunds are allowed within 30 days of purchase.",
    "shipping.pdf": "Orders ship within 2 business days.",
}


class State(TypedDict, total=False):
    question: str
    query: str
    context: str
    answer: str


# 1. A node that calls a decorated function: the decorator records the call wherever it is made from.
@ragevalkit.step("rewrite")
def rewrite(question: str) -> str:
    return question.lower().replace("?", "")


def rewrite_node(state: State) -> dict:
    return {"query": rewrite(state["question"])}


# 2. A node with a `with` block inside it: use this when you need to say what the material and sources are.
def retrieve_node(state: State) -> dict:
    with ragevalkit.step("retrieval") as s:
        words = [word for word in state["query"].split() if len(word) > 3]
        found = [(name, text) for name, text in DOCUMENTS.items() if any(word in text.lower() for word in words)]
        s.material = "\n".join(text for _, text in found)
        s.sources = [name for name, _ in found]
    return {"context": s.material}


# 3. A decorator on the node itself.
@ragevalkit.step("llm")
def answer_node(state: State) -> dict:
    return {"answer": state["context"].split(".")[0] + "." if state["context"] else "I could not find that."}


graph = StateGraph(State)
graph.add_node("rewrite", rewrite_node)
graph.add_node("retrieve", retrieve_node)
graph.add_node("answer", answer_node)
graph.add_edge(START, "rewrite")
graph.add_edge("rewrite", "retrieve")
graph.add_edge("retrieve", "answer")
graph.add_edge("answer", END)
app = graph.compile()


def pipeline(question: str) -> str:
    return app.invoke({"question": question})["answer"]


if __name__ == "__main__":
    ragevalkit.serve(pipeline)
