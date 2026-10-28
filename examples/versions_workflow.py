"""Two versions of one pipeline. Change a setting, restart, run the same test cases again as the next version."""
import os

import ragevalkit

DOCUMENTS = {
    "returns.pdf": "Items can be returned within 30 days if they are unused.",
    "refunds.pdf": "A refund reaches your account 5 to 7 days after we receive the return.",
    "shipping.pdf": "Orders ship within 2 business days.",
}

# Version 1 reads one passage per question. Version 2 reads three:  TOP_K=3 python versions_workflow.py
TOP_K = int(os.environ.get("TOP_K", "1"))


def search(question: str) -> list[tuple[str, str]]:
    """Stand-in for your vector database: the TOP_K best (source, text) pairs."""
    words = [word for word in question.lower().replace("?", "").replace(",", "").split() if len(word) > 3]
    scored = [(sum(word in text.lower() for word in words), name, text) for name, text in DOCUMENTS.items()]
    return [(name, text) for score, name, text in sorted(scored, reverse=True)[:TOP_K] if score > 0]


def pipeline(question: str) -> str:
    with ragevalkit.step("retrieval") as s:
        passages = search(question)
        s.material = "\n".join(text for _, text in passages)
        s.sources = [name for name, _ in passages]
    with ragevalkit.step("llm"):
        return " ".join(text for _, text in passages) or "I could not find that."


if __name__ == "__main__":
    ragevalkit.serve(pipeline, port=8002, require_login=False)
