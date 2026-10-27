"""Turn an exception into a sentence a person running an evaluation can act on."""
from ragevalkit.exceptions import RagevalError

# What went wrong, by the part of the run it happened in
STAGE_SENTENCES = {
    "answer": "Your chatbot or pipeline returned an error for this question, so there is no answer to grade.",
    "grading": "The question was answered, but the AI judge could not grade it.",
    "custom_judge": "Your own judge function returned an error, so this answer was scored 0.",
    "source_check": "Checking the sources with the AI model failed, so a simple keyword check was used instead.",
    "metric": "One of the scores could not be calculated for this question.",
    "summary": "The AI could not write the findings for this run.",
    "save": "The results could not be saved.",
    "callback": "Your on_complete function returned an error. The results themselves are saved.",
    "run": "The run stopped because of an unexpected problem.",
    "generation": "A question could not be written for this part of the document.",
    "generation_run": "Writing test cases stopped because of an unexpected problem.",
}

# (words found in the error, what it usually means). The first match wins, so the more specific come first.
_CAUSES = [
    (("ratelimit", "rate limit", "rate_limit", "too many requests", "429"),
     "The AI service is receiving too many requests. Wait a minute and try again, or lower the number of questions."),
    (("quota", "insufficient_quota", "billing", "credit balance", "out of credit"),
     "The AI account has run out of credit or quota."),
    (("authentication", "unauthorized", "invalid api key", "incorrect api key", "api key", "401", "403", "permission denied"),
     "The AI service did not accept the API key. Check the key and the model name."),
    (("contextwindow", "context length", "maximum context", "too many tokens", "context_length"),
     "The text was too long for the AI model to read."),
    (("contentpolicy", "content_filter", "content policy", "safety"),
     "The AI model refused the request for content-safety reasons."),
    (("timeout", "timed out", "deadline"),
     "It took too long to respond."),
    (("connection", "connect", "unreachable", "name or service not known", "getaddrinfo", "ssl", "dns", "network"),
     "The service could not be reached. Check the network connection and the address."),
    (("notfound", "model_not_found", "does not exist", "unknown model", "not a valid model", "404"),
     "The AI model name was not recognised. Check the model name."),
    (("serviceunavailable", "internalserver", "overloaded", "502", "503", "500", "bad gateway"),
     "The AI service had a problem on its side. Try again in a few minutes."),
]


def _signals(error: BaseException) -> str:
    """Class names and messages of the error and everything it was raised from, lower-cased, for matching."""
    found, seen = [], set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        found.append(" ".join(kind.__name__ for kind in type(error).__mro__))
        found.append(str(error))
        error = error.__cause__ or error.__context__
    return " ".join(found).lower()


def cause_sentence(error: BaseException) -> str:
    """What this kind of error usually means, or an empty string when nothing is recognised."""
    signals = _signals(error)
    return next((sentence for words, sentence in _CAUSES if any(word in signals for word in words)), "")


def explain(error: BaseException, stage: str) -> str:
    """A plain-language message for an error that happened during ``stage`` (a key of ``STAGE_SENTENCES``)."""
    if stage in ("generation", "documents") and isinstance(error, RagevalError) and not cause_sentence(error):
        return str(error)      # reading a document already says why in plain words
    return " ".join(part for part in (STAGE_SENTENCES.get(stage, STAGE_SENTENCES["run"]), cause_sentence(error)) if part)
