from __future__ import annotations

import re

from langchain_openai import ChatOpenAI

from app.prompts import EXTRACTION_PROMPT
from app.schemas import QuestionExtraction


COMMON_TEAMS = {
    "阿森纳": "Arsenal",
    "拜仁": "Bayern Munich",
    "拜仁慕尼黑": "Bayern Munich",
    "曼城": "Manchester City",
    "皇马": "Real Madrid",
    "皇家马德里": "Real Madrid",
    "巴萨": "Barcelona",
    "巴塞罗那": "Barcelona",
    "利物浦": "Liverpool",
    "切尔西": "Chelsea",
    "曼联": "Manchester United",
    "热刺": "Tottenham Hotspur",
    "巴黎": "Paris Saint-Germain",
    "巴黎圣日耳曼": "Paris Saint-Germain",
    "国米": "Inter Milan",
    "国际米兰": "Inter Milan",
    "米兰": "AC Milan",
    "尤文": "Juventus",
    "马竞": "Atletico Madrid",
    "多特": "Borussia Dortmund",
}

COMPETITIONS = {
    "欧冠": "UEFA Champions League",
    "英超": "Premier League",
    "西甲": "La Liga",
    "意甲": "Serie A",
    "德甲": "Bundesliga",
    "法甲": "Ligue 1",
    "足总杯": "FA Cup",
    "国王杯": "Copa del Rey",
    "欧洲杯": "UEFA Euro",
    "世界杯": "FIFA World Cup",
}


def extract_question_info(question: str, llm: ChatOpenAI | None = None) -> QuestionExtraction:
    rule_based = _rule_based_extract(question)
    if llm is None:
        return rule_based

    try:
        structured_llm = llm.with_structured_output(QuestionExtraction)
        extracted = structured_llm.invoke(
            [
                ("system", EXTRACTION_PROMPT),
                ("human", question),
            ]
        )
    except Exception:
        return rule_based

    return _merge_extractions(rule_based, extracted)


def _rule_based_extract(question: str) -> QuestionExtraction:
    found_teams: list[str] = []
    for cn_name, en_name in COMMON_TEAMS.items():
        if cn_name in question and en_name not in found_teams:
            found_teams.append(en_name)

    competition = None
    for cn_name, en_name in COMPETITIONS.items():
        if cn_name in question:
            competition = en_name
            break

    date_match = re.search(r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}月\d{1,2}日|今天|明天|今晚|本周|周末)", question)
    focus = []
    focus_keywords = {
        "伤": "injuries",
        "停赛": "suspension",
        "首发": "expected_lineups",
        "阵容": "expected_lineups",
        "状态": "recent_form",
        "关键球员": "key_players",
        "战术": "tactical_analysis",
        "交锋": "head_to_head",
        "怎么看": "match_preview",
        "优势": "match_preview",
    }
    for keyword, value in focus_keywords.items():
        if keyword in question and value not in focus:
            focus.append(value)

    return QuestionExtraction(
        team_a=found_teams[0] if found_teams else None,
        team_b=found_teams[1] if len(found_teams) > 1 else None,
        competition=competition,
        date=date_match.group(1) if date_match else None,
        focus=focus,
    )


def _merge_extractions(rule_based: QuestionExtraction, llm_based: QuestionExtraction) -> QuestionExtraction:
    return QuestionExtraction(
        team_a=llm_based.team_a or rule_based.team_a,
        team_b=llm_based.team_b or rule_based.team_b,
        competition=llm_based.competition or rule_based.competition,
        date=llm_based.date or rule_based.date,
        focus=llm_based.focus or rule_based.focus,
    )
