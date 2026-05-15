from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI

from app.prompts import ANSWER_PROMPT, PLANNER_PROMPT, SYSTEM_PROMPT
from app.schemas import AgentPlan, ExecutedStep, FootballFanAnswer, PlanStep, QuestionExtraction
from app.services.extractor import extract_question_info
from app.services.query_builder import build_football_queries
from app.tools.duckduckgo import duckduckgo_search_tool
from app.tools.webpage import fetch_url_text_tool

PROJECT_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_DIR.parent

load_dotenv(PROJECT_DIR / ".env")
load_dotenv(WORKSPACE_DIR / ".env")
load_dotenv()

FORBIDDEN_TERMS = [
    "稳赢",
    "必胜",
    "稳赚",
    "下注",
    "盘口",
    "赔率",
    "稳胆",
    "买入",
    "重仓",
]

LOW_VALUE_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "x.com",
    "twitter.com",
    "youtube.com",
}

ProgressCallback = Callable[[str], None]


def answer_football_question(question: str, progress: ProgressCallback | None = None) -> FootballFanAnswer:
    _progress(progress, "读取 LLM 配置")
    llm = _build_llm()

    _progress(progress, "识别球队、赛事和关注点")
    extraction = extract_question_info(question, llm=llm)
    teams = [team for team in [extraction.team_a, extraction.team_b] if team]
    _progress(progress, f"识别结果：teams={teams}, competition={extraction.competition or '未识别'}")

    fallback_queries = build_football_queries(question, extraction.team_a, extraction.team_b, extraction.competition)

    _progress(progress, "Planner：生成可执行检索计划")
    plan = _create_plan(llm, question, extraction, fallback_queries, progress=progress)
    _progress(progress, f"Planner：生成 {len(plan.steps)} 个执行步骤")
    for step in plan.steps:
        _progress(progress, f"Plan step：{step.id} | {step.query}")

    _progress(progress, "Executor：开始执行计划")
    executed_steps = _execute_plan(plan, progress=progress)

    _progress(progress, "Executor：整理执行材料")
    context = _build_execution_context(plan, executed_steps)
    sources = _collect_sources_from_steps(executed_steps)

    if llm is None:
        _progress(progress, "未检测到 LLM API key，返回降级结果")
        return _fallback_answer(question, extraction, sources, "未配置可用 LLM，仅返回保守降级结果。")

    try:
        _progress(progress, "Synthesizer：调用 LLM 生成 JSON 回答")
        answer = _synthesize_answer(llm, question, extraction, plan, context, sources)
    except Exception as exc:
        _progress(progress, f"Synthesizer：LLM 生成失败：{exc}")
        return _fallback_answer(question, extraction, sources, f"LLM 生成失败：{exc}")

    _progress(progress, "回答生成完成")
    answer.sources = [url for url in answer.sources if url in sources] or sources
    return _sanitize_answer(answer)


def get_llm_status() -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
    model = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL_ID") or "gpt-4o-mini"
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or "OpenAI default"
    return {
        "configured": bool(api_key),
        "model": model,
        "base_url": base_url,
        "api_key_preview": _preview_secret(api_key),
    }


def check_llm_connection() -> dict[str, Any]:
    status = get_llm_status()
    if not status["configured"]:
        return {**status, "ok": False, "error": "未找到 OPENAI_API_KEY 或 LLM_API_KEY"}

    try:
        timeout = int(os.getenv("LLM_CONNECT_TIMEOUT_SECONDS", "15"))
        llm = _build_llm(timeout=timeout)
        if llm is None:
            return {**status, "ok": False, "error": "LLM 客户端未创建"}
        response = llm.invoke("请只回复：连接成功")
        text = getattr(response, "content", "")
        return {**status, "ok": True, "response": str(text)[:80]}
    except Exception as exc:
        return {**status, "ok": False, "error": str(exc)}


def _build_llm(timeout: int = 45) -> ChatOpenAI | None:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
    if not api_key:
        return None
    model = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL_ID") or "gpt-4o-mini"
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL")
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.2,
        timeout=timeout,
        max_retries=2,
    )


def _create_plan(
    llm: ChatOpenAI | None,
    question: str,
    extraction: QuestionExtraction,
    fallback_queries: list[str],
    progress: ProgressCallback | None = None,
) -> AgentPlan:
    if llm is None:
        _progress(progress, "Planner：无 LLM，使用规则计划")
        return _fallback_plan(question, extraction, fallback_queries)

    planner_chain = RunnableLambda(
        lambda payload: llm.invoke(
            [
                ("system", SYSTEM_PROMPT),
                (
                    "human",
                    PLANNER_PROMPT.format(
                        question=payload["question"],
                        extraction=payload["extraction"],
                        fallback_queries=payload["fallback_queries"],
                    ),
                ),
            ]
        )
    ) | RunnableLambda(lambda message: _loads_json_object(str(getattr(message, "content", "")))) | RunnableLambda(
        AgentPlan.model_validate
    )

    try:
        return planner_chain.invoke(
            {
                "question": question,
                "extraction": extraction.model_dump_json(ensure_ascii=False),
                "fallback_queries": "\n".join(f"- {query}" for query in fallback_queries),
            }
        )
    except Exception as exc:
        _progress(progress, f"Planner：LLM 计划失败，使用规则计划：{exc}")
        return _fallback_plan(question, extraction, fallback_queries)


def _fallback_plan(
    question: str,
    extraction: QuestionExtraction,
    queries: list[str],
) -> AgentPlan:
    teams = [team for team in [extraction.team_a, extraction.team_b] if team]
    steps = [
        PlanStep(
            id=f"search_{index}",
            tool="football_search",
            purpose=_infer_query_purpose(query),
            query=query,
            max_results=int(os.getenv("FOOTBALL_AGENT_MAX_SEARCH_RESULTS", "5")),
            fetch_top_n=1,
        )
        for index, query in enumerate(queries, start=1)
    ]
    return AgentPlan(
        objective=f"回答用户问题：{question}",
        teams=teams,
        competition=extraction.competition,
        assumptions=["LLM planner 不可用或返回格式不合法，使用规则 query 生成器作为计划。"],
        steps=steps,
        answer_strategy="按伤停、阵容、状态、战术和比赛走势组织回答，并明确不确定性。",
    )


def _execute_plan(plan: AgentPlan, progress: ProgressCallback | None = None) -> list[ExecutedStep]:
    executed: list[ExecutedStep] = []
    seen_urls: set[str] = set()

    for index, step in enumerate(plan.steps, start=1):
        _progress(progress, f"Executor：执行 {index}/{len(plan.steps)} | {step.purpose}")
        if step.tool != "football_search":
            executed.append(
                ExecutedStep(
                    id=step.id,
                    purpose=step.purpose,
                    query=step.query,
                    errors=[f"Unsupported tool: {step.tool}"],
                )
            )
            continue

        search_results = duckduckgo_search_tool.invoke(
            {"query": step.query, "max_results": step.max_results}
        )
        if not isinstance(search_results, list):
            search_results = []

        errors = [str(item.get("error")) for item in search_results if isinstance(item, dict) and item.get("error")]
        if errors:
            _progress(progress, f"Executor：搜索错误：{errors[0]}")
        else:
            _progress(progress, f"Executor：搜索得到 {len(search_results)} 条结果")

        urls = _select_urls(search_results, limit=step.fetch_top_n)
        fetched_pages: list[dict[str, Any]] = []
        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            _progress(progress, f"Executor：抓取网页：{url}")
            page = fetch_url_text_tool.invoke({"url": url, "max_chars": 8000})
            if isinstance(page, dict):
                if page.get("error"):
                    errors.append(str(page.get("error")))
                    _progress(progress, f"Executor：网页抓取失败：{page.get('error')}")
                fetched_pages.append(page)

        executed.append(
            ExecutedStep(
                id=step.id,
                purpose=step.purpose,
                query=step.query,
                search_results=search_results,
                fetched_pages=fetched_pages,
                errors=errors,
            )
        )

    return executed


def _synthesize_answer(
    llm: ChatOpenAI,
    question: str,
    extraction: QuestionExtraction,
    plan: AgentPlan,
    context: str,
    sources: list[str],
) -> FootballFanAnswer:
    response = llm.invoke(
        [
            ("system", SYSTEM_PROMPT),
            (
                "human",
                ANSWER_PROMPT.format(
                    question=question,
                    extraction=extraction.model_dump_json(ensure_ascii=False),
                    plan=plan.model_dump_json(ensure_ascii=False),
                    context=context,
                    sources="\n".join(sources) if sources else "无可用 URL",
                ),
            ),
        ]
    )
    content = str(getattr(response, "content", ""))
    data = _loads_json_object(content)
    return FootballFanAnswer.model_validate(data)


def _loads_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError(f"LLM 未返回可解析 JSON：{text[:300]}")
        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError("LLM JSON 顶层不是对象")
    return parsed


def _select_urls(search_results: list[dict[str, Any]], limit: int) -> list[str]:
    urls: list[str] = []
    for result in search_results:
        url = result.get("href") or result.get("url") or ""
        if not url or result.get("error"):
            continue
        if _is_low_value_url(url):
            continue
        if url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def _is_low_value_url(url: str) -> bool:
    lowered = url.lower()
    return any(domain in lowered for domain in LOW_VALUE_DOMAINS)


def _build_execution_context(plan: AgentPlan, executed_steps: list[ExecutedStep]) -> str:
    parts = [
        "## Agent Plan",
        plan.model_dump_json(ensure_ascii=False, indent=2),
        "\n## Executed Steps",
    ]

    for index, step in enumerate(executed_steps, start=1):
        parts.append(
            "\n".join(
                [
                    f"### Step {index}: {step.id}",
                    f"Purpose: {step.purpose}",
                    f"Query: {step.query}",
                    f"Errors: {step.errors or []}",
                    "Search Results:",
                    _format_search_results(step.search_results),
                    "Fetched Pages:",
                    _format_pages(step.fetched_pages),
                ]
            )
        )

    return "\n\n".join(parts)


def _format_search_results(results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, result in enumerate(results[:8], start=1):
        if result.get("error"):
            lines.append(f"{index}. ERROR: {result.get('error')}")
            continue
        lines.append(
            "\n".join(
                [
                    f"{index}. {result.get('title', '')}",
                    f"URL: {result.get('href', '')}",
                    f"Snippet: {result.get('snippet', '')}",
                ]
            )
        )
    return "\n".join(lines) if lines else "No search results."


def _format_pages(pages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, page in enumerate(pages[:5], start=1):
        if page.get("error"):
            lines.append(f"{index}. URL: {page.get('url', '')}\nFetch error: {page.get('error')}")
            continue
        text = (page.get("text") or "")[:4000]
        lines.append(
            "\n".join(
                [
                    f"{index}. {page.get('title', '')}",
                    f"URL: {page.get('url', '')}",
                    f"Description: {page.get('description', '')}",
                    f"Text: {text}",
                ]
            )
        )
    return "\n".join(lines) if lines else "No fetched pages."


def _collect_sources_from_steps(executed_steps: list[ExecutedStep]) -> list[str]:
    sources: list[str] = []
    for step in executed_steps:
        for page in step.fetched_pages:
            url = page.get("url")
            if url and url not in sources:
                sources.append(url)
        for result in step.search_results:
            url = result.get("href") or result.get("url")
            if url and not result.get("error") and url not in sources:
                sources.append(url)
    return sources[:12]


def _fallback_answer(
    question: str,
    extraction: QuestionExtraction,
    sources: list[str],
    note: str,
) -> FootballFanAnswer:
    teams = [team for team in [extraction.team_a, extraction.team_b] if team]
    match = " vs ".join(teams) if len(teams) == 2 else None
    return FootballFanAnswer(
        short_answer="目前只能给出保守判断：请优先查看来源中的球队新闻、伤停、预计首发和赛前分析；材料不足时不应把走势说得过满。",
        match=match,
        teams=teams,
        competition=extraction.competition,
        confirmed_facts=[],
        likely_but_uncertain=[],
        team_a_strengths=[],
        team_a_concerns=[],
        team_b_strengths=[],
        team_b_concerns=[],
        key_players=[],
        tactical_focus=[],
        likely_game_flow="外部材料或模型调用不足，暂不做具体走势判断。",
        fan_takeaway=f"问题“{question}”需要结合最新伤停、首发和球队近况继续确认。",
        sources=sources,
        uncertainty_note=note,
    )


def _infer_query_purpose(query: str) -> str:
    lowered = query.lower()
    if "injur" in lowered or "suspension" in lowered:
        return "查找伤病和停赛信息"
    if "lineup" in lowered:
        return "查找预计首发和阵容信息"
    if "tactical" in lowered:
        return "查找战术分析"
    if "head to head" in lowered:
        return "查找历史交锋"
    if "recent form" in lowered:
        return "查找近期状态"
    return "查找赛前/赛后分析材料"


def _sanitize_answer(answer: FootballFanAnswer) -> FootballFanAnswer:
    data = answer.model_dump()

    def clean(value: Any) -> Any:
        if isinstance(value, str):
            cleaned = value
            for term in FORBIDDEN_TERMS:
                cleaned = cleaned.replace(term, "[已移除的不适当表述]")
            return cleaned
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return FootballFanAnswer(**{key: clean(value) for key, value in data.items()})


def _progress(progress: ProgressCallback | None, message: str) -> None:
    if progress:
        progress(message)


def _preview_secret(value: str | None) -> str:
    if not value:
        return "未配置"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"
