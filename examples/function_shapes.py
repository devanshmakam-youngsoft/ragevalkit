"""The three shapes of function ragevalkit understands. Pick the one that matches how your chatbot works."""
import ragevalkit


# Shape 1: a question in, an answer out. Every question is answered on its own.
def answer_only(question: str) -> str:
    return "Refunds are allowed within 30 days of purchase."


# Shape 2: a stateless chatbot. You receive the earlier turns of the chat every time and rebuild the prompt from them.
# history looks like [{"question": "...", "answer": "..."}, ...] and is empty on the first turn.
def answer_with_history(question: str, history: list) -> str:
    earlier = [turn["question"] for turn in history]
    if earlier:
        return f"Following up on '{earlier[-1]}': refunds are allowed within 30 days."
    return "Refunds are allowed within 30 days of purchase."


# Shape 3: a stateful chatbot. Your backend remembers the conversation itself, so ragevalkit only passes a session id
# (the same id for every turn of one chat, a new one for the next chat).
SESSIONS: dict[str, list] = {}


def answer_in_session(question: str, session_id: str) -> str:
    turns = SESSIONS.setdefault(session_id, [])
    turns.append(question)
    return f"This is message {len(turns)} of this chat. Refunds are allowed within 30 days."


# Your function may also return a dict (ragevalkit reads the "answer" key; "response", "output", "result" and "text"
# work too), or a Pydantic model with such a field.
def answer_as_dict(question: str) -> dict:
    return {"answer": "Refunds are allowed within 30 days of purchase.", "confidence": 0.92}


# ...or be async.
async def answer_async(question: str) -> str:
    return "Refunds are allowed within 30 days of purchase."


# Parameter names of your own? Tell ragevalkit what they mean:
#     ragevalkit.serve(answer_with_other_names, history_params=["past_chats"], session_params=["chat_token"])
def answer_with_other_names(question: str, past_chats: list) -> str:
    return f"I can see {len(past_chats)} earlier turns."


# With serve(..., history_format="openai") the history arrives as chat messages instead of question/answer pairs.
def answer_with_openai_history(question: str, messages: list) -> str:
    # messages = [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), None)
    return f"Earlier you said: {last_user}" if last_user else "This is the first question."


if __name__ == "__main__":
    ragevalkit.serve(answer_with_history)   # or answer_only, or answer_in_session
