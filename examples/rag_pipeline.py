"""A typical RAG pipeline: rewrite the question, search, re-rank, answer. Only the search declares material."""
import ragevalkit

DOCUMENTS = {
    "refunds.pdf": "Refunds are allowed within 30 days of purchase. Annual plans are refunded pro rata.",
    "shipping.pdf": "Orders ship within 2 business days. Express shipping arrives in 1 business day.",
    "privacy.pdf": "We never sell personal data. You can ask us to delete your account at any time.",
}


def rewrite_query(question: str) -> str:
    """Stand-in for a query-rewriting LLM call."""
    return question.lower().replace("?", "")


def vector_search(query: str, k: int = 2) -> list[tuple[str, str]]:
    """Stand-in for your vector database: (source, text) pairs, best first."""
    words = [word for word in query.split() if len(word) > 3]
    scored = [(sum(word in text.lower() for word in words), name, text) for name, text in DOCUMENTS.items()]
    return [(name, text) for score, name, text in sorted(scored, reverse=True)[:k] if score > 0]


def call_llm(question: str, context: str) -> str:
    """Stand-in for your answer-writing LLM call."""
    return context.split(".")[0] + "." if context else "I could not find that in the documents."


def rag_pipeline(question: str) -> str:
    with ragevalkit.step("rewrite"):                      # timing only
        query = rewrite_query(question)

    with ragevalkit.step("retrieval") as s:               # the one step that declares what was retrieved
        passages = vector_search(query)
        context = "\n\n".join(text for _, text in passages)
        s.material = context
        s.sources = [name for name, _ in passages]

    with ragevalkit.step("rerank"):                       # timing only: it does not set s.material
        passages = sorted(passages, key=lambda p: len(p[1]))

    ragevalkit.note("documents_found", len(passages))     # shown next to the question in the results
    with ragevalkit.step("llm"):
        return call_llm(question, context)


if __name__ == "__main__":
    ragevalkit.serve(rag_pipeline)
