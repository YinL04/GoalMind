from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="用户的足球问答问题")


class FootballFanAnswer(BaseModel):
    short_answer: str
    match: Optional[str] = None
    teams: list[str] = Field(default_factory=list)
    competition: Optional[str] = None
    confirmed_facts: list[str] = Field(default_factory=list)
    likely_but_uncertain: list[str] = Field(default_factory=list)
    team_a_strengths: list[str] = Field(default_factory=list)
    team_a_concerns: list[str] = Field(default_factory=list)
    team_b_strengths: list[str] = Field(default_factory=list)
    team_b_concerns: list[str] = Field(default_factory=list)
    key_players: list[str] = Field(default_factory=list)
    tactical_focus: list[str] = Field(default_factory=list)
    likely_game_flow: str
    fan_takeaway: str
    sources: list[str] = Field(default_factory=list)
    uncertainty_note: str


class SearchResult(BaseModel):
    title: str = ""
    href: str = ""
    snippet: str = ""
    error: Optional[str] = None


class WebPageText(BaseModel):
    url: str
    title: str = ""
    description: str = ""
    text: str = ""
    error: Optional[str] = None


class QuestionExtraction(BaseModel):
    team_a: Optional[str] = None
    team_b: Optional[str] = None
    competition: Optional[str] = None
    date: Optional[str] = None
    focus: list[str] = Field(default_factory=list)
