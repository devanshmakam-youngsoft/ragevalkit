"""Real models copy imperfectly: near-copies are matched and stored as the document's own words."""
from types import SimpleNamespace

import pytest

from ragevalkit.documents.models import Chunk
from ragevalkit.documents.text_cleaning import normalise
from ragevalkit.generation import GenerationModelClient, Task, parse_reply, validate

MARKDOWN_PASSAGE = (
    "## Expenses\n\n**Employees** must submit expense claims within *thirty days* of travel. "
    "Managers approve claims above `five hundred` dollars within five working days.\n\n"
    "- Late claims are paid in the next monthly cycle unless finance grants an exception in writing.\n"
    "- Receipts are required for every item above twenty-five dollars.\n"
)


def chunk(text, file="faq.md", label="section: Expenses"):
    return Chunk(id=f"{file}#1", file=file, text=text, label=label, pages=[(1, normalise(text))])


def reply(**kw):
    base = {"question": "Within how many days must travel expenses be submitted?", "expected_answer": "Within thirty days of travel.",
            "evidence": ["Employees must submit expense claims within thirty days of travel."]}
    return {**base, **kw}


def direct(chunks):
    return Task("direct", "faq.md", chunks, 1)


@pytest.mark.parametrize("quote", [
    "Employees must submit expense claims within thirty days of travel.",                       # markdown marks in the document only
    "**Employees** must submit *expense claims* within thirty days of travel",                  # markdown copied into the quote
    "Employees must submit expense claims ... within thirty days of travel.",                    # ellipsis inside
    "employees must submit expense claims within thirty days of travel",                        # case and punctuation
    "Employees must submit expense claims within thirty days of travel, as required.",          # a few extra words at the end
    "Employees need to submit expense claims within thirty days of travel.",                    # one word changed
])
def test_imperfect_quotes_are_matched_and_stored_as_the_documents_exact_words(quote):
    ch = chunk(MARKDOWN_PASSAGE)
    turns, reason = validate(direct([ch]), reply(evidence=[quote]), turns=3, avoid=[])
    assert reason == "", reason
    stored = [e["quote"] for e in turns[0]["evidence"]]
    assert all(q in ch.cleaned for q in stored)      # always the document's own text, never the model's version
    assert all("*" not in q and "..." not in q for q in stored) and sum(len(q.split()) for q in stored) >= 7


@pytest.mark.parametrize("quote", [
    "Employees can submit claims whenever they feel like it at all.",           # invented
    "Managers decide everything about expense claims in this whole company.",   # invented, shares a few words
    "Employees must",                                                           # too short to prove anything
    "",
])
def test_quotes_that_are_not_in_the_document_are_still_rejected(quote):
    turns, reason = validate(direct([chunk(MARKDOWN_PASSAGE)]), reply(evidence=[quote]), turns=3, avoid=[])
    assert turns is None and "does not point at any sentence" in reason


def test_a_repaired_quote_still_finds_its_page():
    page_one = "Introduction and scope of the policy. " * 12
    page_two = "Managers approve claims above five hundred dollars within five working days of receiving the claim form."
    ch = Chunk(id="h#1", file="h.pdf", text=page_one + "\n\n" + page_two, label="pages 1–2",
               pages=[(1, normalise(page_one)), (2, normalise(page_two))])
    quote = "**Managers** approve claims above five hundred dollars within five working days..."
    turns, _ = validate(Task("direct", "h.pdf", [ch], 1), reply(evidence=[quote]), turns=3, avoid=[])
    assert turns[0]["evidence"][0]["page"] == "page 2"


def test_a_providers_json_mode_error_falls_back_to_asking_without_it(monkeypatch):
    """Groq answers 400 'Failed to validate JSON' when the model's output is not strict JSON."""
    import litellm

    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        if "response_format" in kwargs:
            raise RuntimeError('litellm.BadRequestError: GroqException - {"error":{"message":"Failed to validate JSON.","code":"json_validate_failed"}}')
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='```json\n{"question": "q"}\n```'))])

    monkeypatch.setattr(litellm, "completion", completion)
    llm = GenerationModelClient(SimpleNamespace(generator_model="groq/x", judge_model="groq/y", judge_api_key=""))
    assert llm([{"role": "user", "content": "hi"}]).strip().startswith("```json")
    assert "response_format" in calls[0] and "response_format" not in calls[1] and calls[1]["model"] == "groq/x"

    def other_error(**kwargs):
        raise RuntimeError("rate limit exceeded")

    monkeypatch.setattr(litellm, "completion", other_error)
    with pytest.raises(RuntimeError, match="rate limit"):
        llm([{"role": "user", "content": "hi"}])               # unrelated errors are not hidden by the fallback


def test_replies_with_fences_and_chatter_are_still_read():
    assert parse_reply('Sure! Here it is:\n```json\n{"question": "q", "evidence": []}\n```\nHope that helps.')["question"] == "q"
    assert parse_reply("not json at all") is None


# ---- evidence comes back in many shapes, especially for multi-part questions ---------------------------------

PASSAGE_A = ("Employees must submit expense claims within thirty days of travel. Managers approve claims above five hundred "
             "dollars within five working days of receiving them.")
PASSAGE_B = ("Visitors must sign the register at reception and wear a badge at all times while inside the building. "
             "Contractors collect their badge from the security office before eight in the morning.")
QUOTE_A = "Employees must submit expense claims within thirty days of travel."
QUOTE_B = "Visitors must sign the register at reception and wear a badge at all times while inside the building."


def multipart():
    return Task("multipart", "faq.md", [chunk(PASSAGE_A), chunk(PASSAGE_B)], 1)


def multi_reply(evidence_key="evidence", evidence=None):
    return {"question": "What is the claim deadline, and what must visitors do on arrival?", "expected_answer": "Thirty days; sign the register.",
            evidence_key: evidence}


@pytest.mark.parametrize("key, evidence", [
    ("evidence", [QUOTE_A, QUOTE_B]),                                                       # the asked-for shape
    ("evidence", {"A": QUOTE_A, "B": QUOTE_B}),                                             # a mapping per passage
    ("evidence", {"passage_a": [QUOTE_A], "passage_b": [QUOTE_B]}),                         # a mapping of lists
    ("evidence", [{"passage": "A", "quote": QUOTE_A}, {"passage": "B", "quote": QUOTE_B}]),   # a list of objects
    ("evidence", QUOTE_A + " ... " + QUOTE_B),                                              # one string joining both
    ("evidence", QUOTE_A + " " + QUOTE_B),                                                  # one string, two sentences
    ("quotes", [QUOTE_A, QUOTE_B]),                                                         # another field name
    ("supporting_evidence", [QUOTE_A, QUOTE_B]),
])
def test_multipart_evidence_is_read_whatever_shape_the_model_uses(key, evidence):
    turns, reason = validate(multipart(), multi_reply(key, evidence), turns=3, avoid=[])
    assert reason == "", reason
    assert {e["passage"] for e in turns[0]["evidence"]} == {"A", "B"}


def test_multipart_with_evidence_from_only_one_passage_is_still_rejected():
    turns, reason = validate(multipart(), multi_reply(evidence=[QUOTE_A]), turns=3, avoid=[])
    assert turns is None and "both Passage A and Passage B" in reason


def test_a_reply_with_no_evidence_field_gets_a_retry_hint_in_the_right_shape():
    turns, reason = validate(multipart(), multi_reply(evidence=None), turns=3, avoid=[])
    assert turns is None and "B4" in reason and "each passage" in reason
