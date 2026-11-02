"""The fields of a test case row and the header names recognised for each."""


MAX_ROWS = 20_000


MAX_BYTES = 10 * 1024 * 1024


FIELDS = ("chat_id", "turn_no", "type", "question", "expected_answer", "expected_sources", "groups")


FIELD_LABELS = {
    "chat_id": "Chat ID",
    "turn_no": "Turn number",
    "type": "Type",
    "question": "Question",
    "expected_answer": "Expected answer",
    "expected_sources": "Expected sources",
    "groups": "Groups",
}


# Header names we recognise for each field, compared after lower-casing and turning punctuation into "_".
ALIASES: dict[str, tuple[str, ...]] = {
    "chat_id": ("chat_id", "chat", "chatid", "conversation_id", "conversation", "session_id", "session", "thread_id", "thread"),
    "turn_no": ("turn_no", "turn", "turn_number", "turn_num", "turnno", "step", "message_no"),
    "type": ("type", "question_type", "category", "kind"),
    "question": ("question", "query", "user_query", "user_question", "prompt", "input", "user_input", "utterance"),
    "expected_answer": ("expected_answer", "expected", "answer", "gold_answer", "reference_answer", "reference", "ground_truth", "expected_response"),
    "expected_sources": ("expected_sources", "expected_source", "sources", "source", "documents", "expected_documents", "references"),
    "groups": ("groups", "group", "tags", "tag", "labels", "label"),
}
