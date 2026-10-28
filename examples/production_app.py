"""The production API. It never starts ragevalkit: the steps inside the pipeline are simply inactive here."""
from fastapi import FastAPI

from shared_pipeline import answer_question

app = FastAPI()


@app.post("/chat")
def chat(body: dict) -> dict:
    return {"reply": answer_question(body["message"])}
