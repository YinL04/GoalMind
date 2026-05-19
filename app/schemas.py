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


class PlanStep(BaseModel):
    id: str = Field(..., description="计划步骤 ID，例如 search_injuries_a")
    tool: str = Field("football_search", description="要调用的工具名称：football_search 或 fetch_webpage_text")
    purpose: str = Field(..., description="这一步要回答的信息需求")
    query: str = Field("", description="搜索 query；抓取网页工具可留空")
    url: Optional[str] = Field(None, description="fetch_webpage_text 工具要抓取的 URL")
    max_results: int = Field(5, ge=1, le=10)
    fetch_top_n: int = Field(1, ge=0, le=3)


class AgentPlan(BaseModel):
    objective: str
    teams: list[str] = Field(default_factory=list)
    competition: Optional[str] = None
    assumptions: list[str] = Field(default_factory=list)
    steps: list[PlanStep] = Field(default_factory=list)
    answer_strategy: str


class ExecutedStep(BaseModel):
    id: str
    purpose: str
    query: str
    search_results: list[dict] = Field(default_factory=list)
    fetched_pages: list[dict] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
