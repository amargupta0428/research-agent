"""Tools the agent selects among. The agent decides which to call and when —
this module only knows how to *execute* a chosen tool, never what order to use them.

Each tool returns a ToolResult with:
  - observation: the compact text fed back to the control model (what it "sees")
  - quality:    a flag the model uses to judge the result (ok|empty|blocked|error|irrelevant)
  - detail:     richer data kept in the trace for human spot-checking

Budget separation by design:
  - web_search / web_fetch are free-ish (no Apify run) — the everyday path.
  - apify_scrape consumes an Apify run and is capped; the agent reaches for it
    only when structured extraction is needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from . import config
from .extract import extract_page
from .llm import TokenMeter


@dataclass
class ToolResult:
    observation: str
    quality: str = "ok"  # ok|empty|blocked|error|irrelevant
    detail: dict[str, Any] = field(default_factory=dict)
    used_apify: bool = False

    @property
    def ok(self) -> bool:
        return self.quality == "ok"


# =========================================================================
# Anthropic tool schemas — what the control model sees.
# subquestion + rationale are required on every action so the trace stays legible.
# =========================================================================
def tool_schemas(apify_available: bool) -> list[dict]:
    common = {
        "subquestion": {
            "type": "string",
            "description": "The open sub-question this action is meant to make progress on.",
        },
        "rationale": {
            "type": "string",
            "description": "One sentence: why this tool + this input, right now.",
        },
    }
    schemas = [
        {
            "name": "web_search",
            "description": (
                "Search the open web for sources. Use for general/open questions, "
                "discovering candidate sources, competitors, or entities. Returns a "
                "ranked list of {title, url, snippet}. Cheap — prefer this to find leads."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    **common,
                },
                "required": ["query", "subquestion", "rationale"],
            },
        },
        {
            "name": "web_fetch",
            "description": (
                "Fetch and read the main content of ONE specific URL (e.g. a result you "
                "found via web_search). Returns a distilled, source-grounded summary "
                "focused on your sub-question. Cheap — prefer this to read a page."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Absolute URL to fetch."},
                    **common,
                },
                "required": ["url", "subquestion", "rationale"],
            },
        },
        {
            "name": "finish",
            "description": (
                "Conclude the research and return the synthesized answer. Call this when "
                "you judge you have enough coverage and confidence — NOT at a fixed step "
                "count. The answer must use inline [n] citations matching the citations list."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "string",
                        "description": "Markdown answer with inline [n] citations grounded "
                        "ONLY in sources you actually retrieved.",
                    },
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "url": {"type": "string"},
                                "title": {"type": "string"},
                                "note": {"type": "string"},
                            },
                            "required": ["id", "url"],
                        },
                    },
                    "confidence": {
                        "type": "string",
                        "description": "high | medium | low, with a short reason.",
                    },
                    "open_gaps": {
                        "type": "string",
                        "description": "What remains unresolved or uncertain (may be empty).",
                    },
                },
                "required": ["answer", "citations", "confidence"],
            },
        },
    ]
    if apify_available:
        schemas.insert(
            2,
            {
                "name": "apify_scrape",
                "description": (
                    "Structured extraction via Apify, for data the search/fetch path can't get "
                    "cleanly. Use SPARINGLY (runs are capped). mode='content' deep-crawls a "
                    "specific site URL and returns clean text; mode='serp' returns STRUCTURED "
                    "Google results for a query (organic results, related searches) — useful "
                    "for competitor/pricing discovery. Reach for this only when web_fetch was "
                    "blocked or you need structured data from a specific source."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": ["content", "serp"]},
                        "target": {
                            "type": "string",
                            "description": "For mode='content': a URL. For mode='serp': a query.",
                        },
                        **common,
                    },
                    "required": ["mode", "target", "subquestion", "rationale"],
                },
            },
        )
    return schemas


# =========================================================================
# web_search
# =========================================================================
def web_search(query: str, meter: TokenMeter) -> ToolResult:
    results = _tavily(query) if config.TAVILY_API_KEY else None
    engine = "tavily"
    if results is None:
        results, engine = _duckduckgo(query)
    if results is None:
        return ToolResult(
            observation=f"Search engine error for query '{query}'. Try a different query "
            f"or another tool.",
            quality="error",
            detail={"query": query, "engine": engine},
        )
    if not results:
        return ToolResult(
            observation=f"No results for '{query}'. Reformulate the query (broader/different "
            f"keywords) or try another approach.",
            quality="empty",
            detail={"query": query, "engine": engine, "results": []},
        )
    lines = [f"Search results for '{query}' (via {engine}):"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}")
    return ToolResult(
        observation="\n".join(lines),
        quality="ok",
        detail={"query": query, "engine": engine, "results": results},
    )


def _tavily(query: str) -> list[dict] | None:
    try:
        r = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": config.TAVILY_API_KEY,
                "query": query,
                "max_results": config.SEARCH_RESULTS,
                "search_depth": "basic",
            },
            timeout=20,
        )
        r.raise_for_status()
        return [
            {
                "title": x.get("title", ""),
                "url": x.get("url", ""),
                "snippet": (x.get("content", "") or "")[:300],
            }
            for x in r.json().get("results", [])
        ]
    except Exception:
        return None  # fall through to ddg


def _duckduckgo(query: str):
    try:
        from ddgs import DDGS

        with DDGS() as ddg:
            hits = list(ddg.text(query, max_results=config.SEARCH_RESULTS))
        return [
            {
                "title": h.get("title", ""),
                "url": h.get("href") or h.get("url", ""),
                "snippet": (h.get("body", "") or "")[:300],
            }
            for h in hits
        ], "duckduckgo"
    except Exception:
        return None, "duckduckgo"


# =========================================================================
# web_fetch
# =========================================================================
def web_fetch(url: str, subquestion: str, meter: TokenMeter) -> ToolResult:
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=config.FETCH_TIMEOUT,
            headers={"User-Agent": config.USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        ) as c:
            resp = c.get(url)
    except Exception as e:
        return ToolResult(
            observation=f"Could not fetch {url} ({type(e).__name__}). The site may be down "
            f"or blocking. Try another source, or apify_scrape if available.",
            quality="blocked",
            detail={"url": url, "error": str(e)},
        )

    if resp.status_code >= 400:
        return ToolResult(
            observation=f"Fetch of {url} returned HTTP {resp.status_code} "
            f"(blocked/unavailable). Try a different source.",
            quality="blocked",
            detail={"url": url, "status": resp.status_code},
        )

    text = _extract_html(resp.text, url)
    if not text or len(text) < 200:
        return ToolResult(
            observation=f"{url} returned little/no readable content (possible JS wall, "
            f"paywall, or captcha). Try apify_scrape mode='content', or another source.",
            quality="blocked",
            detail={"url": url, "status": resp.status_code, "chars": len(text or "")},
        )

    info = extract_page(text, subquestion, url, meter)
    if not info.get("relevant", True):
        return ToolResult(
            observation=f"Fetched {url} but it does not help with this sub-question: "
            f"{info.get('summary', '')}",
            quality="irrelevant",
            detail={"url": url, "extract": info},
        )
    facts = "\n".join(f"  - {f}" for f in info.get("key_facts", []))
    obs = f"Read {url}:\n{info.get('summary', '')}"
    if facts:
        obs += f"\nKey facts:\n{facts}"
    return ToolResult(observation=obs, quality="ok", detail={"url": url, "extract": info})


def _extract_html(html: str, url: str) -> str:
    try:
        import trafilatura

        out = trafilatura.extract(
            html, url=url, include_comments=False, include_tables=True, favor_recall=True
        )
        return out or ""
    except Exception:
        return ""


# =========================================================================
# apify_scrape (capped, expensive path)
# =========================================================================
def apify_scrape(mode: str, target: str, subquestion: str, meter: TokenMeter) -> ToolResult:
    if not config.APIFY_TOKEN:
        return ToolResult(
            observation="apify_scrape is unavailable (no APIFY_TOKEN). Use web_fetch/web_search.",
            quality="error",
            detail={"reason": "no_token"},
        )
    try:
        from apify_client import ApifyClient

        client = ApifyClient(config.APIFY_TOKEN)
    except Exception as e:
        return ToolResult(
            observation=f"Apify client init failed: {e}", quality="error", detail={"error": str(e)}
        )

    try:
        if mode == "serp":
            return _apify_serp(client, target, subquestion)
        return _apify_content(client, target, subquestion, meter)
    except Exception as e:
        return ToolResult(
            observation=f"Apify run failed ({type(e).__name__}: {e}). Fall back to web_fetch/web_search.",
            quality="error",
            detail={"mode": mode, "target": target, "error": str(e)},
            used_apify=True,
        )


def _apify_content(client, url: str, subquestion: str, meter: TokenMeter) -> ToolResult:
    run = client.actor(config.APIFY_CONTENT_ACTOR).call(
        run_input={
            "startUrls": [{"url": url}],
            "maxCrawlPages": 1,
            "crawlerType": "playwright:firefox",
            "saveMarkdown": True,
        },
        timeout_secs=config.APIFY_TIMEOUT,
    )
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    text = ""
    for it in items:
        text = it.get("markdown") or it.get("text") or ""
        if text:
            break
    if not text:
        return ToolResult(
            observation=f"apify content scrape of {url} returned no content. Try another source.",
            quality="empty",
            detail={"url": url},
            used_apify=True,
        )
    info = extract_page(text, subquestion, url, meter)
    obs = f"Scraped {url} (Apify):\n{info.get('summary', '')}"
    facts = "\n".join(f"  - {f}" for f in info.get("key_facts", []))
    if facts:
        obs += f"\nKey facts:\n{facts}"
    return ToolResult(
        observation=obs, quality="ok", detail={"url": url, "extract": info}, used_apify=True
    )


def _apify_serp(client, query: str, subquestion: str) -> ToolResult:
    run = client.actor(config.APIFY_SERP_ACTOR).call(
        run_input={
            "queries": query,
            "maxPagesPerQuery": 1,
            "resultsPerPage": 10,
            "countryCode": "us",
        },
        timeout_secs=config.APIFY_TIMEOUT,
    )
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    organic, related = [], []
    for it in items:
        organic.extend(it.get("organicResults", []) or [])
        related.extend(it.get("relatedQueries", []) or [])
    if not organic:
        return ToolResult(
            observation=f"apify SERP for '{query}' returned no organic results.",
            quality="empty",
            detail={"query": query},
            used_apify=True,
        )
    lines = [f"Structured Google results for '{query}':"]
    parsed = []
    for i, r in enumerate(organic[:10], 1):
        row = {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "desc": (r.get("description", "") or "")[:300],
        }
        parsed.append(row)
        lines.append(f"{i}. {row['title']}\n   {row['url']}\n   {row['desc']}")
    if related:
        rq = ", ".join(x.get("title", "") if isinstance(x, dict) else str(x) for x in related[:8])
        lines.append(f"Related searches: {rq}")
    return ToolResult(
        observation="\n".join(lines),
        quality="ok",
        detail={"query": query, "organic": parsed, "related": related[:8]},
        used_apify=True,
    )
