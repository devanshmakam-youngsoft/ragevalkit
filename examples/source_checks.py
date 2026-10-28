"""Check that the right documents were retrieved. The pipeline reports its sources; each test case lists the expected ones."""
import ragevalkit

DOCUMENTS = {
    "refunds.pdf": "Refunds are allowed within 30 days of purchase.",
    "shipping.pdf": "Orders ship within 2 business days.",
    "tracking.pdf": "Use the tracking link in the shipping email.",
}


def pipeline(question: str) -> str:
    words = [word for word in question.lower().replace("?", "").split() if len(word) > 3]
    with ragevalkit.step("retrieval") as s:
        found = {name: text for name, text in DOCUMENTS.items() if any(word in text.lower() for word in words)}
        s.material = "\n".join(found.values())
        s.sources = list(found)          # what the check compares with the test case's expected_sources
    return next(iter(found.values()), "I could not find that.")


# In the test case's expected_sources column:
#   refunds.pdf                    that document must be retrieved
#   shipping.pdf | tracking.pdf    BOTH are needed ("|" means AND)
#   tracking.pdf , tracking_v2.pdf EITHER is enough ("," means OR)
# The default "keyword" check ignores case, folders and extensions ("docs/Refunds.PDF" matches "refunds").
# "llm" asks the judge model, which also copes with different spellings of a name.
if __name__ == "__main__":
    ragevalkit.serve(pipeline, source_check_mode="keyword")
