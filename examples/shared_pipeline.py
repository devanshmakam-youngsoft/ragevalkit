"""Your pipeline module. Production and the evaluation both import it, and it needs no changes for either."""
import ragevalkit

DOCUMENTS = {
    "refunds.pdf": "Refunds are allowed within 30 days of purchase.",
    "shipping.pdf": "Orders ship within 2 business days.",
}


def answer_question(question: str) -> str:
    # Outside an evaluation these do nothing, so they can stay in the code that ships.
    with ragevalkit.step("retrieval") as s:
        words = [word for word in question.lower().replace("?", "").split() if len(word) > 3]
        found = {name: text for name, text in DOCUMENTS.items() if any(word in text.lower() for word in words)}
        s.material = "\n".join(found.values())
        s.sources = list(found)
    with ragevalkit.step("llm"):
        return next(iter(found.values()), "I could not find that.")
