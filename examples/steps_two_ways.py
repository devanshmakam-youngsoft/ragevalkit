"""The same pipeline recorded two ways: with `with` blocks, and with decorators. Both record the same two steps."""
import ragevalkit

DOCUMENTS = {
    "refunds.pdf": "Refunds are allowed within 30 days of purchase.",
    "shipping.pdf": "Orders ship within 2 business days.",
}


def search(query: str) -> list[tuple[str, str]]:
    """Stand-in for your vector database: returns (source, text) pairs."""
    words = [word for word in query.lower().replace("?", "").split() if len(word) > 3]
    return [(name, text) for name, text in DOCUMENTS.items() if any(word in text.lower() for word in words)]


def write_answer(question: str, context: str) -> str:
    """Stand-in for your LLM call."""
    return context.split("\n")[0] if context else "I could not find that."


# Style 1: `with` blocks. You decide exactly what is material and what the sources are.
def pipeline_with_blocks(question: str) -> str:
    with ragevalkit.step("retrieval") as s:
        passages = search(question)
        context = "\n".join(text for _, text in passages)
        s.material = context                       # the retrieved text: scored as "context quality"
        s.sources = [name for name, _ in passages]  # the documents: checked against expected_sources
    with ragevalkit.step("llm"):
        return write_answer(question, context)


# Style 2: decorators. Inputs and outputs are recorded for you; the return value of a material=True step is the material.
@ragevalkit.step("retrieval", material=True)
def retrieve(question: str) -> str:
    return "\n".join(text for _, text in search(question))


@ragevalkit.step("llm")
def generate(question: str, context: str) -> str:
    return write_answer(question, context)


def pipeline_with_decorators(question: str) -> str:
    return generate(question, retrieve(question))


if __name__ == "__main__":
    ragevalkit.serve(pipeline_with_blocks)   # or pipeline_with_decorators
