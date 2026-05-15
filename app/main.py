from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.agent import answer_football_question
from app.schemas import AskRequest, FootballFanAnswer

app = FastAPI(
    title="Football Fan Q&A Agent",
    description="Football fan Q&A assistant for match context, team news, tactics, and form. No betting advice.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=FootballFanAnswer)
def ask(request: AskRequest) -> FootballFanAnswer:
    try:
        return answer_football_question(request.question)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Answer generation failed: {exc}") from exc
