"""Evaluate a chatbot that is already deployed: your function just calls it over HTTP."""
import json
import os
import urllib.request

import ragevalkit

BOT_URL = os.environ.get("BOT_URL", "http://localhost:9000/chat")


def ask_deployed_bot(question: str, session_id: str) -> str:
    body = json.dumps({"message": question, "session_id": session_id}).encode()
    request = urllib.request.Request(BOT_URL, data=body, headers={"Content-Type": "application/json"})
    with ragevalkit.step("http_call"):
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())["reply"]


if __name__ == "__main__":
    ragevalkit.serve(ask_deployed_bot)
