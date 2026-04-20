"""Shared web search tool -- available to any agent via policy."""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Agents allowed to use web search
SEARCH_ALLOWED_AGENTS = frozenset({
    "researcher", "miner", "scheduler", "ingestor",
    "trainer", "reporter", "debugger", "sentinel",
})


def is_search_allowed(agent_name: str) -> bool:
    """Check whether the given agent is permitted to use web search."""
    return agent_name in SEARCH_ALLOWED_AGENTS


def get_search_provider(config: dict[str, Any]) -> str:
    """Return the configured search provider, defaulting to duckduckgo."""
    return config.get("search", {}).get("provider", "duckduckgo")


async def web_search(
    query: str,
    config: dict[str, Any] | None = None,
    max_results: int = 5,
) -> list[dict[str, str]]:
    """Search the web using the configured provider.

    Returns list of {title, url, snippet} dicts.
    """
    cfg = config or {}
    provider = get_search_provider(cfg)

    if provider == "brave":
        api_key = cfg.get("search", {}).get("api_key", "")
        return await _search_brave(query, api_key, max_results)
    elif provider == "tavily":
        api_key = cfg.get("search", {}).get("api_key", "")
        return await _search_tavily(query, api_key, max_results)
    else:
        return await _search_duckduckgo(query, max_results)


async def _search_duckduckgo(
    query: str, max_results: int = 5,
) -> list[dict[str, str]]:
    """Search via DuckDuckGo HTML (no API key needed)."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "QuantClaw/0.1"},
            )
            results: list[dict[str, str]] = []
            text = resp.text
            links = re.findall(
                r'<a rel="nofollow" class="result__a" href="([^"]+)">(.+?)</a>',
                text,
            )
            snippets = re.findall(
                r'<a class="result__snippet"[^>]*>(.+?)</a>',
                text,
            )
            for i, (url, title) in enumerate(links[:max_results]):
                snippet = snippets[i] if i < len(snippets) else ""
                clean_title = re.sub(r"<[^>]+>", "", title).strip()
                clean_snippet = re.sub(r"<[^>]+>", "", snippet).strip()
                results.append({
                    "title": clean_title,
                    "url": url,
                    "snippet": clean_snippet,
                })
            return results
    except Exception:
        logger.exception("DuckDuckGo search failed")
        return []


async def _search_brave(
    query: str, api_key: str, max_results: int = 5,
) -> list[dict[str, str]]:
    """Search via Brave Search API."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={
                    "X-Subscription-Token": api_key,
                    "Accept": "application/json",
                },
            )
            data = resp.json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("description", ""),
                }
                for r in data.get("web", {}).get("results", [])[:max_results]
            ]
    except Exception:
        logger.exception("Brave search failed")
        return []


async def _search_tavily(
    query: str, api_key: str, max_results: int = 5,
) -> list[dict[str, str]]:
    """Search via Tavily API."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "query": query,
                    "max_results": max_results,
                    "api_key": api_key,
                },
            )
            data = resp.json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                }
                for r in data.get("results", [])[:max_results]
            ]
    except Exception:
        logger.exception("Tavily search failed")
        return []
