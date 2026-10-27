"""Errors are explained in plain words, and secrets never reach a log or the dashboard."""
import pytest

from ragevalkit.documents.exceptions import DocumentError
from ragevalkit.judging.exceptions import JudgeError
from ragevalkit.logs import explain, redact


@pytest.mark.parametrize("error,expected", [
    (RuntimeError("429 Too Many Requests"), "too many requests"),
    (RuntimeError("Incorrect API key provided"), "API key"),
    (TimeoutError("timed out"), "too long to respond"),
    (ConnectionError("Connection refused"), "could not be reached"),
    (RuntimeError("model gpt-9 does not exist"), "model name was not recognised"),
])
def test_known_causes_are_named(error, expected):
    assert expected in explain(error, "answer")


def test_the_cause_behind_a_wrapper_error_is_found():
    try:
        try:
            raise TimeoutError("read timed out")
        except TimeoutError as cause:
            raise JudgeError("Judge failed after 3 attempts") from cause
    except JudgeError as error:
        assert "took too long" in explain(error, "grading").lower() or "too long to respond" in explain(error, "grading")


def test_an_unrecognised_error_still_says_which_part_failed_and_hides_its_text():
    message = explain(ValueError("KeyError: 'choices' at line 80"), "grading")
    assert message.startswith("The question was answered, but the AI judge could not grade it.")
    assert "KeyError" not in message


def test_a_document_that_cannot_be_read_keeps_its_own_plain_message():
    assert explain(DocumentError("report.pdf is password protected"), "generation") == "report.pdf is password protected"


def test_secrets_are_hidden():
    text = redact("key sk-abcdefghijklmnopqrstuv, api_key=abc12345, Authorization: Bearer abcdefghijklmnop")
    assert "abcdefghij" not in text and "abc12345" not in text
