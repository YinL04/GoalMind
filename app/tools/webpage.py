from __future__ import annotations

from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.services.cache import JsonTTLCache, default_cache


class FetchUrlInput(BaseModel):
    url: str = Field(..., description="要抓取正文的 URL")
    max_chars: int = Field(8000, ge=500, le=20000, description="正文最大字符数")


def fetch_url_text(
    url: str,
    max_chars: int = 8000,
    cache: JsonTTLCache | None = None,
) -> dict:
    cache = cache or default_cache()
    cache_key = cache.make_key("url", f"{url}|{max_chars}")
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    if not _is_http_url(url):
        return {"url": url, "title": "", "description": "", "text": "", "error": "URL 不是 http/https 地址"}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=12)
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"url": url, "title": "", "description": "", "text": "", "error": f"网页抓取失败：{exc}"}

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()

    title = _clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    description_tag = soup.find("meta", attrs={"name": "description"})
    description = ""
    if description_tag and description_tag.get("content"):
        description = _clean_text(str(description_tag["content"]))

    paragraphs = []
    for element in soup.find_all(["p", "li", "h1", "h2", "h3"]):
        text = _clean_text(element.get_text(" ", strip=True))
        if len(text) >= 30:
            paragraphs.append(text)

    body_text = "\n".join(paragraphs)
    if len(body_text) > max_chars:
        body_text = body_text[:max_chars].rsplit("\n", 1)[0] or body_text[:max_chars]

    result = {"url": url, "title": title, "description": description, "text": body_text, "error": None}
    cache.set(cache_key, result)
    return result


def _clean_text(text: str) -> str:
    return " ".join(text.split())


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


fetch_url_text_tool = StructuredTool.from_function(
    func=fetch_url_text,
    name="fetch_webpage_text",
    description="抓取网页正文并清洗 HTML，用于补充 DuckDuckGo 摘要。",
    args_schema=FetchUrlInput,
)
