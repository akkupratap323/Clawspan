"""Web search — Tavily (primary) + DuckDuckGo (fallback)."""

import json
import os
import re
import subprocess
import urllib.parse
import urllib.request

from dotenv import load_dotenv

load_dotenv()

_TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "")


def tavily_search(query: str, max_results: int = 3) -> str:
    """High-quality web search via Tavily API."""
    if not _TAVILY_KEY:
        return duckduckgo_search(query, max_results=max_results)

    print(f"[Search] Tavily: {query}", flush=True)
    try:
        payload = json.dumps({
            "api_key": _TAVILY_KEY,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
        }).encode()
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        results = data.get("results", [])
        if not results:
            return f"No results found for '{query}'."

        lines = []
        for r in results[:max_results]:
            lines.append(f"{r.get('title', '')}: {r.get('content', '')[:200]}")
        return "\n".join(lines)

    except Exception as e:
        print(f"[Search] Tavily error: {e}, falling back to DDG", flush=True)
        return duckduckgo_search(query, max_results=max_results)


def duckduckgo_search(query: str, max_results: int = 5) -> str:
    """Free web search via DuckDuckGo instant answer API."""
    print(f"[Search] DuckDuckGo: {query}", flush=True)
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Clawspan/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())

        results = []

        if data.get("Abstract"):
            results.append(f"Answer: {data['Abstract']}\nSource: {data.get('AbstractURL', '')}")

        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"- {topic['Text'][:200]}")
                if topic.get("FirstURL"):
                    results.append(f"  URL: {topic['FirstURL']}")

        if results:
            return "\n".join(results[:max_results * 3])

        return f"No direct results for '{query}'. Try a more specific query."

    except Exception as e:
        return f"Search error: {e}"


def fetch_url(url: str) -> str:
    """Fetch and extract text content from a URL."""
    print(f"[Search] Fetching: {url}", flush=True)
    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", "10", "-A", "Mozilla/5.0", url],
            capture_output=True, text=True, timeout=12,
        )
        raw = result.stdout
        raw = re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r'<style[^>]*>.*?</style>', '', raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r'<[^>]+>', ' ', raw)
        raw = re.sub(r'\s+', ' ', raw).strip()
        if not raw:
            return f"Could not extract text from {url}"
        return raw[:3000] + ("...(truncated)" if len(raw) > 3000 else "")
    except Exception as e:
        return f"Error fetching {url}: {e}"
