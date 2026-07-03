"""
Web Search Tool - Internet search via DuckDuckGo + SearXNG (Google, Yandex, Bing)
"""

import logging
from typing import Dict, List, Any, Optional

import httpx

logger = logging.getLogger(__name__)


class WebSearchTool:
    """Search the web using DuckDuckGo and a local SearXNG instance."""

    def __init__(self, searxng_url: str = "http://searxng:8080"):
        self._ddgs = None
        self._searxng_url = searxng_url.rstrip("/")

    def _get_ddgs(self):
        if self._ddgs is None:
            from duckduckgo_search import DDGS
            self._ddgs = DDGS()
        return self._ddgs

    # ── DuckDuckGo (fallback) ──

    def search(self, query: str, max_results: int = 10, region: str = "ru-ru") -> Dict[str, Any]:
        try:
            ddgs = self._get_ddgs()
            results = list(ddgs.text(query, region=region, max_results=max_results))
            formatted = [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")} for r in results]
            return {"success": True, "query": query, "engine": "duckduckgo", "count": len(formatted), "results": formatted}
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return {"error": f"Search failed: {str(e)}"}

    def search_news(self, query: str, max_results: int = 10, region: str = "ru-ru") -> Dict[str, Any]:
        try:
            ddgs = self._get_ddgs()
            results = list(ddgs.news(query, region=region, max_results=max_results))
            formatted = [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("body", ""), "source": r.get("source", ""), "date": r.get("date", "")} for r in results]
            return {"success": True, "query": query, "engine": "duckduckgo", "count": len(formatted), "results": formatted}
        except Exception as e:
            logger.error(f"News search failed: {e}")
            return {"error": f"News search failed: {str(e)}"}

    # ── SearXNG (Google / Yandex / all engines) ──

    def _searxng_search(self, query: str, engines: str = "", max_results: int = 10, language: str = "ru") -> Dict[str, Any]:
        try:
            params: Dict[str, Any] = {
                "q": query,
                "format": "json",
                "language": language,
                "pageno": 1,
            }
            if engines:
                params["engines"] = engines

            resp = httpx.get(
                f"{self._searxng_url}/search",
                params=params,
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()

            raw_results = data.get("results", [])[:max_results]
            formatted = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                    "engine": r.get("engine", ""),
                }
                for r in raw_results
            ]

            engine_label = engines if engines else "all"
            return {
                "success": True,
                "query": query,
                "engine": f"searxng ({engine_label})",
                "count": len(formatted),
                "results": formatted,
            }
        except Exception as e:
            logger.error(f"SearXNG search failed (engines={engines}): {e}")
            return {"error": f"SearXNG search failed: {str(e)}"}

    def search_google(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        return self._searxng_search(query, engines="google", max_results=max_results)

    def search_yandex(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        return self._searxng_search(query, engines="yandex", max_results=max_results)

    def search_multi(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Search across all SearXNG engines simultaneously."""
        return self._searxng_search(query, engines="", max_results=max_results)

    # ── Async wrappers ──

    async def _run_sync(self, fn, *args, **kwargs):
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(None, lambda: fn(*args, **kwargs))

    async def asearch(self, query: str, max_results: int = 10, region: str = "ru-ru") -> Dict[str, Any]:
        return await self._run_sync(self.search, query, max_results, region)

    async def asearch_news(self, query: str, max_results: int = 10, region: str = "ru-ru") -> Dict[str, Any]:
        return await self._run_sync(self.search_news, query, max_results, region)

    async def asearch_google(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        return await self._run_sync(self.search_google, query, max_results)

    async def asearch_yandex(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        return await self._run_sync(self.search_yandex, query, max_results)

    async def asearch_multi(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        return await self._run_sync(self.search_multi, query, max_results)


# Tool definitions for the agent
WEB_SEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Быстрый поиск в интернете через DuckDuckGo. Используй как основной инструмент поиска.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос"},
                    "max_results": {"type": "integer", "description": "Максимум результатов (по умолчанию 10)", "default": 10},
                    "region": {"type": "string", "description": "Регион: 'ru-ru', 'en-us', 'wt-wt'", "default": "ru-ru"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search_news",
            "description": "Поиск новостей через DuckDuckGo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос"},
                    "max_results": {"type": "integer", "description": "Максимум результатов", "default": 10},
                    "region": {"type": "string", "description": "Регион", "default": "ru-ru"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search_google",
            "description": "Поиск в Google. Более качественные и точные результаты. Используй когда DuckDuckGo не нашёл нужного.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос"},
                    "max_results": {"type": "integer", "description": "Максимум результатов", "default": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search_yandex",
            "description": "Поиск в Яндексе. Лучшие результаты для русскоязычных запросов.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос"},
                    "max_results": {"type": "integer", "description": "Максимум результатов", "default": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search_multi",
            "description": "Мультипоиск: одновременно ищет в Google, Yandex, Bing, DuckDuckGo и других. Используй для максимального охвата результатов.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос"},
                    "max_results": {"type": "integer", "description": "Максимум результатов", "default": 10},
                },
                "required": ["query"],
            },
        },
    },
]
