"""web_search tool — pluggable provider architecture.

Providers:
  - bing_cn: Bing CN scraper (works in mainland China, no API key)
  - ddgs:   DuckDuckGo via ddgs package (no API key, blocked in China)

Active provider resolution:
  1. WEB_SEARCH_BACKEND env var (explicit choice)
  2. Auto-detect: pick the first available provider in preference order
  3. Fallback error message if none available
"""

import asyncio
import json
import logging
import os
import urllib.parse
from abc import ABC, abstractmethod
from typing import Any

import httpx
from lxml import html as lxml_html

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider ABC
# ---------------------------------------------------------------------------


class WebSearchProvider(ABC):
    """Minimal provider interface — each provider implements search()."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable short identifier (lowercase, no spaces)."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when this provider can service calls. No network I/O."""

    def search(self, query: str, limit: int = 8) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} does not implement search")


# ---------------------------------------------------------------------------
# Bing CN provider — scrapes cn.bing.com, works in mainland China, no key
# ---------------------------------------------------------------------------

_BING_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


class BingCNProvider(WebSearchProvider):
    """Scrape Bing CN search results — no API key, works in China."""

    @property
    def name(self) -> str:
        return "bing_cn"

    def is_available(self) -> bool:
        return True  # always available — no env var or key needed

    def search(self, query: str, limit: int = 8) -> dict[str, Any]:
        base_url = os.getenv("BING_CN_URL", "https://cn.bing.com").rstrip("/")
        params = {"q": query, "count": limit}

        headers = {
            "User-Agent": _BING_UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml",
        }

        try:
            resp = httpx.get(
                f"{base_url}/search",
                params=params,
                headers=headers,
                timeout=15,
                follow_redirects=True,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.warning("Bing CN HTTP error: %s", exc)
            return {"success": False, "error": f"Bing CN HTTP {exc.response.status_code}"}
        except httpx.RequestError as exc:
            log.warning("Bing CN request error: %s", exc)
            return {"success": False, "error": f"Could not reach Bing CN: {exc}"}

        try:
            doc = lxml_html.fromstring(resp.text)
        except Exception as exc:
            log.warning("Bing CN HTML parse error: %s", exc)
            return {"success": False, "error": "Could not parse Bing CN response"}

        results = []
        # Bing result items: <li class="b_algo">
        items = doc.xpath('//li[@class="b_algo"]')
        for i, item in enumerate(items[:limit]):
            # Title + URL: <h2><a href="...">
            link = item.xpath('.//h2/a')
            title = link[0].text_content().strip() if link else ""
            url_raw = link[0].get("href", "") if link else ""

            # Bing sometimes wraps URLs with tracking; extract real URL
            url = url_raw
            if url_raw.startswith("/search?q="):
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url_raw).query)
                u_val = parsed.get("u", [url_raw])
                url = u_val[0] if u_val else url_raw

            # Snippet: various containers under b_algo
            snippet_parts = item.xpath('.//div[@class="b_caption"]//p')
            if not snippet_parts:
                snippet_parts = item.xpath('.//p')
            snippet = snippet_parts[0].text_content().strip() if snippet_parts else ""

            if title or url:
                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "position": i + 1,
                })

        log.info("Bing CN search '%s': %d results (limit %d)", query, len(results), limit)
        return {"success": True, "data": {"results": results, "total": len(results)}}


# ---------------------------------------------------------------------------
# DuckDuckGo provider — via ddgs package, no API key, blocked in China
# ---------------------------------------------------------------------------


class DDGSProvider(WebSearchProvider):
    """DuckDuckGo search via ddgs package — no API key, dev/intl fallback."""

    @property
    def name(self) -> str:
        return "ddgs"

    def is_available(self) -> bool:
        try:
            from ddgs import DDGS  # noqa: F401
            return True
        except ImportError:
            return False

    def search(self, query: str, limit: int = 8) -> dict[str, Any]:
        try:
            from ddgs import DDGS
        except ImportError:
            return {"success": False, "error": "ddgs package not installed"}

        try:
            raw = list(DDGS().text(query, max_results=limit))
        except Exception as exc:
            log.warning("DDGS search error: %s", exc)
            return {"success": False, "error": f"DuckDuckGo search failed: {exc}"}

        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "snippet": item.get("body", ""),
                "position": i + 1,
            }
            for i, item in enumerate((raw or [])[:limit])
        ]

        log.info("DDGS search '%s': %d results", query, len(results))
        return {"success": True, "data": {"results": results, "total": len(results)}}


# ---------------------------------------------------------------------------
# Provider registry + resolution
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, WebSearchProvider] = {
    "bing_cn": BingCNProvider(),
    "ddgs": DDGSProvider(),
}

# Preference order: bing_cn first (works in China), ddgs as fallback
_PREFERENCE = ["bing_cn", "ddgs"]


def _resolve_provider() -> WebSearchProvider | None:
    """Resolve active provider:
    1. WEB_SEARCH_BACKEND env var (explicit)
    2. Auto-detect first available in preference order
    """
    configured = os.getenv("WEB_SEARCH_BACKEND", "").strip()
    if configured:
        provider = _PROVIDERS.get(configured)
        if provider:
            return provider
        log.warning("WEB_SEARCH_BACKEND='%s' not found, falling back to auto-detect", configured)

    for name in _PREFERENCE:
        provider = _PROVIDERS[name]
        try:
            if provider.is_available():
                return provider
        except Exception:
            continue

    return None


# ---------------------------------------------------------------------------
# Tool definition + execute
# ---------------------------------------------------------------------------

TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for information. Returns top results with titles, "
            "snippets, and URLs. Works in mainland China."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results to return", "default": 8},
            },
            "required": ["query"],
        },
    },
}


async def execute(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    query = args.get("query", "")
    limit = min(args.get("limit", 8), 20)

    if not query:
        return json.dumps({"error": "query is required"}, ensure_ascii=False)

    provider = _resolve_provider()
    if not provider:
        return json.dumps({
            "error": "No available search provider. Set WEB_SEARCH_BACKEND or ensure bing_cn/ddgs is accessible.",
        }, ensure_ascii=False)

    # Run sync search in thread to avoid blocking async loop
    result = await asyncio.to_thread(provider.search, query, limit)

    if not result.get("success"):
        # Try next provider in preference order as fallback
        for name in _PREFERENCE:
            fallback = _PROVIDERS[name]
            if fallback.name == provider.name:
                continue
            try:
                if not fallback.is_available():
                    continue
            except Exception:
                continue
            log.info("Primary provider '%s' failed, trying fallback '%s'", provider.name, name)
            result = await asyncio.to_thread(fallback.search, query, limit)
            if result.get("success"):
                result["source"] = fallback.name
                break

    # Normalize output for the agent
    if result.get("success") and "data" in result:
        data = result["data"]
        return json.dumps({
            "results": data.get("results", []),
            "total": data.get("total", 0),
            "source": result.get("source", provider.name),
        }, ensure_ascii=False)

    error_msg = result.get("error", "Search failed")
    return json.dumps({"error": error_msg}, ensure_ascii=False)