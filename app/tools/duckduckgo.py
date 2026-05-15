from __future__ import annotations

import os
import warnings
from typing import Any

import requests
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.services.cache import JsonTTLCache, default_cache

warnings.filterwarnings(
    "ignore",
    message=".*duckduckgo_search.*renamed to.*ddgs.*",
    category=RuntimeWarning,
)


class DuckDuckGoSearchInput(BaseModel):
    query: str = Field(..., description="Search query")
    max_results: int = Field(5, ge=1, le=10, description="Maximum number of results")


def duckduckgo_search(
    query: str,
    max_results: int = 5,
    cache: JsonTTLCache | None = None,
) -> list[dict[str, Any]]:
    cache = cache or default_cache()
    cache_key = cache.make_key("ddg", f"{query}|{max_results}|v2")
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        raw_results = _run_search(query=query, max_results=max_results)
    except Exception as exc:
        return [
            {
                "title": "Search failed",
                "href": "",
                "snippet": "",
                "error": f"Search request failed: {exc}",
            }
        ]

    results: list[dict[str, Any]] = []
    for item in raw_results:
        href = item.get("href") or item.get("url") or ""
        results.append(
            {
                "title": item.get("title", ""),
                "href": href,
                "snippet": item.get("body") or item.get("snippet") or "",
                "error": None,
            }
        )

    cache.set(cache_key, results)
    return results


def _run_search(query: str, max_results: int) -> list[dict[str, Any]]:
    searxng_base_url = os.getenv("SEARXNG_BASE_URL", "").strip().rstrip("/")
    if searxng_base_url:
        try:
            results = _run_searxng_search(searxng_base_url, query=query, max_results=max_results)
            if results:
                return results
        except Exception:
            pass

    return _run_ddg_search(query=query, max_results=max_results)


def _run_searxng_search(base_url: str, query: str, max_results: int) -> list[dict[str, Any]]:
    response = requests.get(
        f"{base_url}/search",
        params={
            "q": query,
            "format": "json",
            "language": "en",
            "categories": "general",
        },
        headers={"User-Agent": "football-fan-agent/0.1"},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()

    results: list[dict[str, Any]] = []
    for item in payload.get("results", [])[:max_results]:
        results.append(
            {
                "title": item.get("title", ""),
                "href": item.get("url", ""),
                "body": item.get("content", ""),
            }
        )
    return results


def _run_ddg_search(query: str, max_results: int) -> list[dict[str, Any]]:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with DDGS(timeout=15) as ddgs:
            errors = []
            for backend in ["duckduckgo", "auto"]:
                try:
                    results = list(
                        ddgs.text(
                            query,
                            region="us-en",
                            safesearch="moderate",
                            backend=backend,
                            max_results=max_results,
                        )
                    )
                    if results:
                        return results
                except Exception as exc:
                    if "No results found" in str(exc):
                        continue
                    errors.append(str(exc))

            if errors:
                raise RuntimeError(" | ".join(errors))
            return []


duckduckgo_search_tool = StructuredTool.from_function(
    func=duckduckgo_search,
    name="duckduckgo_football_search",
    description="Search football news, injuries, suspensions, lineups, previews, and tactics.",
    args_schema=DuckDuckGoSearchInput,
)
