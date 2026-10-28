"""A LangChain chain. Steps work inside runnables, including the branches LangChain runs in parallel threads."""
from langchain_core.runnables import RunnableLambda, RunnableParallel

import ragevalkit

DOCUMENTS = {
    "refunds.pdf": "Refunds are allowed within 30 days of purchase.",
    "shipping.pdf": "Orders ship within 2 business days.",
}


@ragevalkit.step("rewrite")
def rewrite(question: str) -> str:
    return question.lower().replace("?", "")


def vector_search(query: str) -> list[tuple[str, str]]:
    with ragevalkit.step("vector_search"):
        return [(name, text) for name, text in DOCUMENTS.items() if any(w in text.lower() for w in query.split() if len(w) > 3)]


def keyword_search(query: str) -> list[tuple[str, str]]:
    with ragevalkit.step("keyword_search"):
        return [(name, text) for name, text in DOCUMENTS.items() if query.split()[-1] in text.lower()]


def merge(results: dict) -> str:
    """Join what the parallel searches found. This is where the retrieved text is declared, once."""
    unique = dict(results["vector"] + results["keyword"])
    with ragevalkit.step("retrieval") as s:
        s.material = "\n".join(unique.values())
        s.sources = list(unique)
    return s.material


def answer(context: str) -> str:
    with ragevalkit.step("llm"):
        return context.split(".")[0] + "." if context else "I could not find that."


chain = (
    RunnableLambda(rewrite)
    | RunnableParallel(vector=RunnableLambda(vector_search), keyword=RunnableLambda(keyword_search))
    | RunnableLambda(merge)
    | RunnableLambda(answer)
)


def pipeline(question: str) -> str:
    return chain.invoke(question)


if __name__ == "__main__":
    ragevalkit.serve(pipeline)
