from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from app.prompts import ANSWER_PROMPT, SYSTEM_PROMPT
from app.schemas import FootballFanAnswer, QuestionExtraction
from app.services.extractor import extract_question_info
from app.services.query_builder import build_football_queries
from app.tools.duckduckgo import duckduckgo_search
from app.tools.webpage import fetch_url_text

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

    queries = build_football_queries(question, extraction.team_a, extraction.team_b, extraction.competition)
    _progress(progress, f"生成 {len(queries)} 条搜索 query")

    max_results = int(os.getenv("FOOTBALL_AGENT_MAX_SEARCH_RESULTS", "5"))
    fetch_top_n = int(os.getenv("FOOTBALL_AGENT_FETCH_TOP_N", "5"))

    search_results = _search_many(queries, max_results=max_results, progress=progress)
    urls = _select_urls(search_results, limit=fetch_top_n)

    _progress(progress, f"选择 {len(urls)} 个网页抓取正文")
    pages: list[dict[str, Any]] = []
    for index, url in enumerate(urls, start=1):
        _progress(progress, f"抓取网页 {index}/{len(urls)}：{url}")
        page = fetch_url_text(url)
        if page.get("error"):
            _progress(progress, f"网页抓取失败，继续使用搜索摘要：{page.get('error')}")
        pages.append(page)

    _progress(progress, "合并搜索摘要和网页正文")
    context = _build_context(queries, search_results, pages)
    sources = _collect_sources(search_results, pages)

    if llm is None:
        _progress(progress, "未检测到 LLM API key，返回降级结果")
        return _fallback_answer(question, extraction, sources, "未配置可用 LLM，仅返回保守降级结果。")

    try:
        _progress(progress, "调用 LLM 生成 JSON 回答")
        answer = _generate_answer_with_json(llm, question, extraction, context, sources)
    except Exception as exc:
        _progress(progress, f"LLM 生成失败：{exc}")
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


def _generate_answer_with_json(
    llm: ChatOpenAI,
    question: str,
    extraction: QuestionExtraction,
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


def _search_many(
    queries: list[str],
    max_results: int,
    progress: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for index, query in enumerate(queries, start=1):
        _progress(progress, f"搜索 {index}/{len(queries)}：{query}")
        results = duckduckgo_search(query, max_results=max_results)
        error_count = sum(1 for result in results if result.get("error"))
        if error_count:
            _progress(progress, f"搜索返回错误：{results[0].get('error')}")
        else:
            _progress(progress, f"搜索得到 {len(results)} 条结果")
            if not results:
                _progress(progress, "该 query 没有返回结果，将继续尝试下一条 query")

        for result in results:
            item = dict(result)
            item["query"] = query
            href = item.get("href", "")
            key = href or f"{query}:{item.get('title', '')}"
            if key not in seen_urls:
                seen_urls.add(key)
                combined.append(item)
    return combined


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


def _build_context(
    queries: list[str],
    search_results: list[dict[str, Any]],
    pages: list[dict[str, Any]],
) -> str:
    parts = ["## Search Queries", *[f"- {query}" for query in queries], "\n## DuckDuckGo Results"]

    for index, result in enumerate(search_results[:30], start=1):
        error = result.get("error")
        if error:
            parts.append(f"{index}. ERROR: {error}")
            continue
        parts.append(
            "\n".join(
                [
                    f"{index}. {result.get('title', '')}",
                    f"URL: {result.get('href', '')}",
                    f"Snippet: {result.get('snippet', '')}",
                    f"Query: {result.get('query', '')}",
                ]
            )
        )

    parts.append("\n## Webpage Text")
    for index, page in enumerate(pages, start=1):
        if page.get("error"):
            parts.append(f"{index}. URL: {page.get('url', '')}\nFetch error: {page.get('error')}")
            continue
        text = (page.get("text") or "")[:5000]
        parts.append(
            "\n".join(
                [
                    f"{index}. {page.get('title', '')}",
                    f"URL: {page.get('url', '')}",
                    f"Description: {page.get('description', '')}",
                    f"Text: {text}",
                ]
            )
        )

    return "\n\n".join(parts)


def _collect_sources(search_results: list[dict[str, Any]], pages: list[dict[str, Any]]) -> list[str]:
    sources: list[str] = []
    for page in pages:
        url = page.get("url")
        if url and url not in sources:
            sources.append(url)
    for result in search_results:
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
