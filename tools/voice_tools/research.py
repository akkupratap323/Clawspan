"""Research voice tools: web_search, deep_research, company/market research, Crawl2RAG, meeting prep, agentic."""

from __future__ import annotations

import json
import os
import urllib.request

from tools.search import tavily_search, fetch_url
from tools.research import (
    research_company as _research_company,
    market_research as _market_research,
    crawl_to_rag as _crawl_to_rag,
    meeting_prep as _meeting_prep,
    agentic_research as _agentic_research,
)


def exec_web_search(query: str, max_results: int = 5, **_kw) -> str:
    """Quick web search via Tavily."""
    return tavily_search(query, max_results=max_results)


def exec_deep_research(query: str, max_sources: int = 10, **_kw) -> str:
    """Multi-step research: searches multiple angles, fetches top sources, synthesizes."""
    tavily_key = os.environ.get("TAVILY_API_KEY", "")
    results_all: list[dict] = []

    queries = [query]
    queries.append(f"{query} 2025 2026 latest")

    for q in queries:
        try:
            if tavily_key:
                payload = json.dumps({
                    "api_key": tavily_key,
                    "query": q,
                    "search_depth": "advanced",
                    "max_results": 5,
                    "include_raw_content": False,
                }).encode()
                req = urllib.request.Request(
                    "https://api.tavily.com/search",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
                for r in data.get("results", []):
                    results_all.append({
                        "title": r.get("title", ""),
                        "content": r.get("content", "")[:400],
                        "url": r.get("url", ""),
                    })
            else:
                results_all.append({"title": "search", "content": tavily_search(q), "url": ""})
        except Exception as e:
            print(f"[Research] Query '{q}' failed: {e}", flush=True)

    if not results_all:
        return f"Could not find research results for '{query}'."

    seen_urls: set[str] = set()
    unique = []
    for r in results_all:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique.append(r)

    top = unique[:min(max_sources, len(unique))]
    for r in top[:2]:
        if r["url"]:
            try:
                full = fetch_url(r["url"])
                r["content"] = full[:800]
            except Exception:
                pass

    lines = [f"DEEP RESEARCH: {query}"]
    lines.append(f"Sources found: {len(unique)}\n")
    for i, r in enumerate(top, 1):
        lines.append(f"[{i}] {r['title']}")
        lines.append(f"    {r['content']}")
        if r["url"]:
            lines.append(f"    Source: {r['url']}")
        lines.append("")

    return "\n".join(lines)


def exec_research_company(company_name: str, include_financials: bool = True,
                          include_news: bool = True, include_competitors: bool = True, **_kw) -> str:
    """In-depth company research with leadership, funding, products, news, competitors."""
    result = _research_company(company_name, include_financials=include_financials,
                               include_news=include_news, include_competitors=include_competitors)
    return result.get("executive_summary", "Company research completed.")


def exec_market_research(ticker_or_company: str, include_competitors: bool = True,
                         include_trends: bool = True, **_kw) -> str:
    """Market analysis: stock data, financials, competitors, trends, analyst sentiment."""
    result = _market_research(ticker_or_company, include_competitors=include_competitors,
                              include_trends=include_trends)
    return result.get("executive_summary", "Market research completed.")


def exec_crawl_to_rag(url: str, max_pages: int = 5, **_kw) -> str:
    """Crawl a website and save its content as a searchable knowledge base."""
    result = _crawl_to_rag(url, max_pages=max_pages)
    return result.get("summary", "Crawl completed.")


def exec_meeting_prep(company_name: str = "", attendee_name: str = "",
                      meeting_topic: str = "", **_kw) -> str:
    """Research companies, attendees, and generate talking points for a meeting."""
    result = _meeting_prep(company_name=company_name, attendee_name=attendee_name,
                           meeting_topic=meeting_topic)
    return result.get("executive_summary", "Meeting prep completed.")


def exec_agentic_research(topic: str, max_iterations: int = 5, **_kw) -> str:
    """Autonomous multi-iteration research that identifies gaps and searches deeper."""
    result = _agentic_research(topic, max_iterations=max_iterations)
    summary = result.get("executive_summary", "")
    sources = result.get("total_sources", 0)
    return f"{summary}\n\nSources analyzed: {sources}"
