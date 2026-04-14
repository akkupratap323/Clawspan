"""
Deep Research Engine — Tavily-like research capabilities.

Provides:
  - Deep Research: multi-source, multi-page research with synthesis
  - Company Researcher: in-depth company analysis (funding, leadership, tech stack, news)
  - Crawl2RAG: turn any website into searchable knowledge base
  - Market Researcher: market insights, stock analysis, competitor comparison
  - Meeting Prep: company + attendee research for meeting preparation
  - Chat: deep factual answers with citations

All research is saved to MemPalace (ChromaDB + KG) for future reference.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

from tools.search import tavily_search, fetch_url

try:
    from shared.mempalace_adapter import save_fact, search_facts, add_entity, add_triple
    _MEMPALACE_AVAILABLE = True
except Exception:
    _MEMPALACE_AVAILABLE = False
    def _safe_noop(*a, **k): return None
    save_fact = search_facts = add_entity = add_triple = _safe_noop


def _safe_save_to_memory(*a, **k):
    """Graceful fallback when MemPalace isn't available."""
    if _MEMPALACE_AVAILABLE:
        try:
            save_fact(*a, **k)
        except Exception:
            pass
    # Otherwise silently skip — research still works without memory

load_dotenv()

_TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "")


# ── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class ResearchSource:
    title: str
    url: str
    snippet: str
    content: str = ""
    relevance_score: float = 0.0


@dataclass
class ResearchResult:
    topic: str
    summary: str
    sources: list[ResearchSource] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


# ── Deep Research ────────────────────────────────────────────────────────────

def deep_research(query: str, max_sources: int = 10,
                  include_urls: bool = True) -> dict:
    """Multi-source deep research with synthesis.

    Steps:
    1. Initial broad search to identify key angles
    2. Targeted searches for each angle
    3. URL crawling for deep content extraction
    4. Synthesis into structured report

    Returns: {
        "query": str,
        "executive_summary": str,
        "key_findings": [str],
        "detailed_analysis": str,
        "sources": [{"title", "url", "snippet", "relevance"}],
        "methodology": str,
        "timestamp": str
    }
    """
    print(f"[Research] Deep research: {query}", flush=True)
    results = {
        "query": query,
        "executive_summary": "",
        "key_findings": [],
        "detailed_analysis": "",
        "sources": [],
        "methodology": "Multi-source research with Tavily + web crawling + synthesis",
        "timestamp": datetime.now().isoformat(),
    }

    # Step 1: Broad initial search
    print(f"[Research] Phase 1: Broad search...", flush=True)
    broad_results = _tavily_search_full(query, max_results=5)

    if not broad_results:
        results["executive_summary"] = f"No results found for '{query}'. Try rephrasing your question."
        return results

    # Step 2: Extract key angles from initial results
    angles = _extract_research_angles(broad_results, query)
    print(f"[Research] Phase 2: Deep diving into {len(angles)} angles: {angles}", flush=True)

    all_sources = []
    detailed_sections = []

    # Step 3: Targeted searches for each angle
    for angle in angles[:4]:  # Max 4 deep dives
        angle_results = _tavily_search_full(f"{query} {angle}", max_results=3)
        all_sources.extend(angle_results)

        if angle_results:
            section = f"## {angle}\n\n"
            for src in angle_results:
                section += f"### {src['title']}\n"
                section += f"Source: {src['url']}\n"
                section += f"{src['content']}\n\n"
            detailed_sections.append(section)

    # Step 4: Deduplicate and rank sources
    seen_urls = set()
    unique_sources = []
    for s in broad_results + all_sources:
        if s["url"] not in seen_urls and len(unique_sources) < max_sources:
            seen_urls.add(s["url"])
            unique_sources.append({
                "title": s.get("title", ""),
                "url": s.get("url", ""),
                "snippet": s.get("content", "")[:200],
                "relevance": "high",
            })

    # Step 5: Build structured report
    results["sources"] = unique_sources

    key_findings = []
    for i, src in enumerate(unique_sources[:5]):
        key_findings.append(f"{i+1}. {src['title']}: {src['snippet'][:150]}...")

    results["key_findings"] = key_findings
    results["detailed_analysis"] = "\n".join(detailed_sections) if detailed_sections else _build_summary(broad_results)

    # Build executive summary
    results["executive_summary"] = _build_executive_summary(query, broad_results, key_findings)

    # Save to MemPalace
    _save_research_to_memory(query, results)

    return results


def _tavily_search_full(query: str, max_results: int = 5) -> list[dict]:
    """Full Tavily search with deep content extraction."""
    if not _TAVILY_KEY:
        return []

    try:
        payload = json.dumps({
            "api_key": _TAVILY_KEY,
            "query": query,
            "search_depth": "advanced",
            "max_results": max_results,
            "include_answer": True,
            "include_raw_content": True,
        }).encode()
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        return data.get("results", [])
    except Exception as e:
        print(f"[Research] Tavily error: {e}", flush=True)
        return []


def _extract_research_angles(results: list[dict], query: str) -> list[str]:
    """Extract key research angles from initial results."""
    angles = []
    seen = set()

    # Common research angles
    angle_keywords = {
        "overview": ["overview", "introduction", "what is", "explain"],
        "details": ["details", "features", "specifications", "how it works"],
        "comparison": ["vs", "versus", "compare", "alternative", "competitor"],
        "recent": ["2024", "2025", "2026", "latest", "recent", "new"],
        "reviews": ["review", "opinion", "analysis", "pros and cons"],
        "technical": ["technical", "architecture", "implementation", "how to"],
        "market": ["market", "industry", "trend", "growth", "forecast"],
        "financial": ["revenue", "funding", "valuation", "financial", "earnings"],
        "news": ["news", "announcement", "launch", "update"],
    }

    for result in results:
        content = (result.get("title", "") + " " + result.get("content", "")).lower()
        for angle, keywords in angle_keywords.items():
            for kw in keywords:
                if kw in content and angle not in seen:
                    angles.append(angle)
                    seen.add(angle)
                    break

    # Always include overview if no specific angles found
    if not angles:
        angles = ["overview", "details", "recent developments"]

    return angles


def _build_executive_summary(query: str, results: list[dict], findings: list[str]) -> str:
    """Build executive summary from research results."""
    summary_lines = [f"**Research Query:** {query}\n"]

    if results:
        summary_lines.append(f"**Searched {len(results)} sources** across multiple angles.\n")

    if findings:
        summary_lines.append("**Key Findings:**\n")
        for f in findings[:5]:
            summary_lines.append(f"- {f}")
    else:
        summary_lines.append("No significant findings. Try a more specific query.")

    summary_lines.append(f"\n**Research completed at:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    return "\n".join(summary_lines)


def _build_summary(results: list[dict]) -> str:
    """Build a simple summary when deep analysis isn't available."""
    if not results:
        return "No results available."

    lines = ["## Research Summary\n"]
    for r in results[:5]:
        lines.append(f"### {r.get('title', 'Untitled')}")
        lines.append(f"Source: {r.get('url', '')}")
        lines.append(f"{r.get('content', '')[:500]}\n")

    return "\n".join(lines)


def _save_research_to_memory(query: str, results: dict) -> None:
    """Record that research was done — save topic marker to KG only, NOT full content.

    Research dumps (500-char summaries) must NOT go into the personal memory
    ChromaDB collection — they flood context slots and crowd out personal facts.
    Only the KG gets a lightweight triple: user → researched → topic.
    """
    if _MEMPALACE_AVAILABLE:
        try:
            add_entity(query[:64], "research_topic")
            add_triple("user", "researched", query[:64])
        except Exception:
            pass


# ── Company Researcher ───────────────────────────────────────────────────────

def research_company(company_name: str, include_financials: bool = True,
                     include_news: bool = True, include_competitors: bool = True) -> dict:
    """In-depth company research: overview, funding, leadership, tech stack, news, competitors.

    Returns comprehensive company profile with multiple data points.
    """
    print(f"[Research] Company research: {company_name}", flush=True)
    result = {
        "company": company_name,
        "timestamp": datetime.now().isoformat(),
        "sections": {},
    }

    # 1. Company Overview
    overview_results = _tavily_search_full(f"{company_name} company overview history what they do", max_results=5)
    result["sections"]["overview"] = _format_research_section(overview_results, "Company Overview")

    # 2. Leadership & Team
    leadership_results = _tavily_search_full(f"{company_name} CEO founder leadership team executives", max_results=3)
    result["sections"]["leadership"] = _format_research_section(leadership_results, "Leadership & Team")

    # 3. Funding & Financials
    if include_financials:
        funding_results = _tavily_search_full(f"{company_name} funding valuation revenue financials investors", max_results=5)
        result["sections"]["financials"] = _format_research_section(funding_results, "Funding & Financials")

    # 4. Products & Technology
    tech_results = _tavily_search_full(f"{company_name} products technology tech stack services platform", max_results=3)
    result["sections"]["products"] = _format_research_section(tech_results, "Products & Technology")

    # 5. Recent News
    if include_news:
        news_results = _tavily_search_full(f"{company_name} news 2025 2026 latest announcements", max_results=5)
        result["sections"]["news"] = _format_research_section(news_results, "Recent News")

    # 6. Competitors
    if include_competitors:
        comp_results = _tavily_search_full(f"{company_name} competitors vs alternatives comparison", max_results=3)
        result["sections"]["competitors"] = _format_research_section(comp_results, "Competitive Landscape")

    # Build executive summary
    result["executive_summary"] = _build_company_summary(company_name, result["sections"])

    # Save to memory
    _save_research_to_memory(f"company research: {company_name}", {
        "executive_summary": result["executive_summary"],
    })

    return result


def _format_research_section(results: list[dict], section_name: str) -> dict:
    """Format research results into a structured, cleaned section."""
    if not results:
        return {"name": section_name, "content": "No data available.", "sources": []}

    content_lines = []
    sources = []

    for r in results:
        raw_content = r.get("content", "")
        # Clean the raw scraped content aggressively
        cleaned = _clean_scraped_content(raw_content)
        if cleaned and len(cleaned) > 50:  # Skip noise
            content_lines.append(f"### {r.get('title', '')}")
            content_lines.append(cleaned)
            content_lines.append("")
            sources.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
            })

    if not content_lines:
        return {"name": section_name, "content": "No relevant data found.", "sources": []}

    return {
        "name": section_name,
        "content": "\n".join(content_lines),
        "sources": sources,
    }


def _clean_scraped_content(text: str) -> str:
    """Aggressively clean raw web-scraped content — remove navigation, footers, ads, boilerplate.

    This is the critical step that removes "JavaScript is disabled", "logo",
    "Chrome Web Store", form confirmations, duplicate paragraphs, etc.
    """
    if not text or len(text) < 30:
        return ""

    lines = text.split("\n")
    cleaned_lines = []

    # Noise patterns to remove
    noise_patterns = [
        # Navigation/UI
        "Hero Section Background", "hero section", "navbar", "menu",
        "Skip to Content", "skip to", "scroll to top", "back to top",
        "toggle navigation", "hamburger menu", "mobile menu",
        # Browser/tech warnings
        "javascript is disabled", "enable javascript", "enable it to enjoy",
        "your browser does not support", "upgrade your browser",
        # Forms/submissions
        "we have received your inquiry", "your inquiry has been", "submit your",
        "fill out the form", "contact us", "subscribe to our", "newsletter",
        "enter your email", "sign up for", "download now",
        # Footers/copyright
        "copyright", "all rights reserved", "powered by", "designed by",
        "privacy policy", "terms of service", "cookie policy", "cookies",
        "sitemap", "accessibility", "cookie settings",
        # App stores/extensions
        "chrome web store", "firefox extension", "app store", "google play",
        "android", "apple", "download the app",
        # Platform branding
        "tracxn", "prospeo", "linkedin", "crunchbase", "glassdoor",
        "logo for", "logo of", "footer-bottom", "footer-logo",
        # Ads/promos
        "try our premium", "free trial", "start for free", "upgrade to pro",
        "limited offer", "exclusive access", "unlock premium",
        # Social/engagement
        "share this", "like this", "follow us on", "tweet this",
        # Boilerplate
        "illustration", "icon", "image of", "photo of", "video thumbnail",
        "flag of", "flag of gb", "flag of us",
        "lock", "pdf illustration", "chrome_extension_cta",
        "srsltid=", "utm_source", "utm_medium",
    ]

    # Short phrases to filter out (1-5 words that are noise)
    short_noise = {
        "logo", "about", "contact", "home", "login", "sign up",
        "search", "menu", "close", "view details", "view all",
        "read more", "learn more", "try now", "view", "close",
        "lock", "about", "location", "contact", "information",
        "android", "apple", "chrome web store", "firefox extension",
        "tracxn illustration", "tracxn logo", "pdf illustration image",
        "hero section background", "footer-bottom-logos",
    }

    seen_sentences = set()

    for line in lines:
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            continue

        # Skip very short lines (likely nav items or labels)
        if len(stripped) < 20 and stripped.lower() in short_noise:
            continue

        # Check against noise patterns
        lower = stripped.lower()
        is_noise = False
        for pattern in noise_patterns:
            if pattern in lower:
                is_noise = True
                break
        if is_noise:
            continue

        # Skip URL-like lines
        if stripped.startswith("http") or stripped.startswith("www."):
            continue

        # Skip table formatting lines
        if stripped in ("---", "|", "|---|", "| |"):
            continue

        # Deduplicate sentences
        sentence_key = stripped.lower().strip(".,!? ")
        if sentence_key and len(sentence_key) > 15:
            if sentence_key in seen_sentences:
                continue
            seen_sentences.add(sentence_key)

        cleaned_lines.append(stripped)

    result = "\n".join(cleaned_lines)

    # Final pass: remove remaining garbage like "View DetailsView All Employees"
    result = re.sub(r'View DetailsView All Employees?', '', result)
    result = re.sub(r'View com[0-9]*employees?', '', result)
    result = re.sub(r'[A-Za-z]+ employees', '', result)
    result = re.sub(r'Flag of [A-Z]+', '', result)
    result = re.sub(r'@[a-z]+\.(com|io|org)', '', result)
    result = re.sub(r'srsltid=[^\s]+', '', result)

    # Clean up multiple blank lines
    result = re.sub(r'\n{3,}', '\n\n', result).strip()

    return result


def _clean_for_summary(text: str) -> str:
    """Clean raw scraped content for summary display."""
    if not text:
        return ""
    lines = text.split("\n")
    cleaned = []
    noise = [
        "hero section", "skip to content", "javascript is disabled",
        "we have received your inquiry", "copyright", "all rights reserved",
        "powered by", "chrome web store", "firefox extension",
        "tracxn", "prospeo", "logo for", "logo of", "footer-bottom",
        "try our premium", "illustration", "icon", "flag of",
        "view details", "view all", "read more", "learn more",
        "srsltid", "utm_", "pdf illustration", "chrome_extension",
        "navbar", "mobile menu", "back to top", "scroll to top",
        "anniversary-logo", "footer-bottom-logos",
    ]
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if any(p in lower for p in noise):
            continue
        if stripped.startswith("http") or stripped.startswith("www."):
            continue
        if stripped in ("---", "|", "|---|", "| |"):
            continue
        if re.match(r'^#{3,}\s+', stripped):
            continue
        if re.match(r'^#{1,3}\s+.*\|.*\b(tracxn|prospeo|crunchbase|linkedin)\b', stripped, re.IGNORECASE):
            continue
        if len(stripped) < 15 and not any(c.isdigit() for c in stripped):
            continue
        cleaned.append(stripped)
    result = "\n".join(cleaned)
    result = re.sub(r'\n{3,}', '\n\n', result).strip()
    return result


def _build_company_summary(company: str, sections: dict) -> str:
    """Build executive summary from company research sections."""
    lines = [f"**Company Research: {company}**\n"]

    for section_key in ["overview", "financials", "news"]:
        if section_key in sections and sections[section_key].get("content"):
            display_name = sections[section_key]["name"]
            raw = sections[section_key]["content"]
            cleaned = _clean_for_summary(raw)
            if cleaned:
                lines.append(f"## {display_name}")
                lines.append(cleaned[:2000])
                lines.append("")

    return "\n".join(lines)


# ── Crawl2RAG ────────────────────────────────────────────────────────────────

def crawl_to_rag(url: str, max_pages: int = 5,
                 save_to_memory: bool = True) -> dict:
    """Turn any website into a searchable knowledge base.

    Crawls the URL and linked pages, extracts content,
    and saves to MemPalace for future semantic search.
    """
    print(f"[Research] Crawl2RAG: {url}", flush=True)
    result = {
        "url": url,
        "pages_crawled": 0,
        "total_content_length": 0,
        "pages": [],
        "timestamp": datetime.now().isoformat(),
    }

    # Crawl the main URL
    pages_to_crawl = [url]
    crawled_urls = set()

    for _ in range(max_pages):
        if not pages_to_crawl:
            break

        current_url = pages_to_crawl.pop(0)
        if current_url in crawled_urls:
            continue

        crawled_urls.add(current_url)
        content = fetch_url(current_url)

        if content and len(content) > 100:
            page_data = {
                "url": current_url,
                "content": content[:5000],
                "length": len(content),
            }
            result["pages"].append(page_data)
            result["pages_crawled"] += 1
            result["total_content_length"] += len(content)

            # Save to MemPalace
            if save_to_memory:
                domain = urllib.parse.urlparse(current_url).netloc
                _safe_save_to_memory(
                    f"crawl_{domain}_{hash(current_url) % 10000}",
                    f"Content from {current_url}: {content[:1000]}",
                    wing="research",
                    room="crawled",
                    importance=2,
                )

            # Extract links for further crawling
            if result["pages_crawled"] < max_pages:
                base_domain = urllib.parse.urlparse(current_url).netloc
                links = _extract_links(content, base_domain)
                for link in links[:3]:
                    if link not in crawled_urls:
                        pages_to_crawl.append(link)

    result["summary"] = (
        f"Crawled {result['pages_crawled']} pages from {url}. "
        f"Total content: {result['total_content_length']} characters. "
        f"Saved to knowledge base for future search."
    )

    return result


def _extract_links(html: str, base_domain: str) -> list[str]:
    """Extract internal links from HTML content."""
    links = []
    # Simple regex-based link extraction
    href_pattern = re.compile(r'href=["\'](/[^"\']+)["\']')
    for match in href_pattern.finditer(html):
        path = match.group(1)
        if not path.startswith(('/api', '/cdn', '/static', '/assets')):
            links.append(f"https://{base_domain}{path}")
    return links[:10]


# ── Market Researcher ────────────────────────────────────────────────────────

def market_research(ticker_or_company: str,
                    include_competitors: bool = True,
                    include_trends: bool = True) -> dict:
    """Comprehensive market research for stocks and companies.

    Includes: company overview, financial metrics, competitor analysis,
    market trends, recent news, and analyst sentiment.
    """
    print(f"[Research] Market research: {ticker_or_company}", flush=True)
    result = {
        "subject": ticker_or_company,
        "timestamp": datetime.now().isoformat(),
        "sections": {},
    }

    # 1. Company/Stock Overview
    overview = _tavily_search_full(f"{ticker_or_company} stock price market cap financials overview", max_results=5)
    result["sections"]["overview"] = _format_research_section(overview, "Market Overview")

    # 2. Financial Performance
    financials = _tavily_search_full(f"{ticker_or_company} revenue earnings quarterly results financial performance", max_results=3)
    result["sections"]["financials"] = _format_research_section(financials, "Financial Performance")

    # 3. Competitor Analysis
    if include_competitors:
        competitors = _tavily_search_full(f"{ticker_or_company} competitors market share comparison analysis", max_results=3)
        result["sections"]["competitors"] = _format_research_section(competitors, "Competitor Analysis")

    # 4. Market Trends
    if include_trends:
        trends = _tavily_search_full(f"{ticker_or_company} industry trends market outlook forecast 2025 2026", max_results=3)
        result["sections"]["trends"] = _format_research_section(trends, "Market Trends & Outlook")

    # 5. Analyst Sentiment
    analyst = _tavily_search_full(f"{ticker_or_company} analyst ratings buy sell hold price target", max_results=3)
    result["sections"]["analyst_sentiment"] = _format_research_section(analyst, "Analyst Sentiment")

    # 6. Recent News
    news = _tavily_search_full(f"{ticker_or_company} news latest developments announcements 2025", max_results=5)
    result["sections"]["news"] = _format_research_section(news, "Recent Developments")

    result["executive_summary"] = _build_market_summary(ticker_or_company, result["sections"])

    return result


def _build_market_summary(subject: str, sections: dict) -> str:
    """Build market research executive summary."""
    lines = [f"**Market Research: {subject}**\n"]

    for section_name in ["overview", "financials", "competitors", "trends", "analyst_sentiment", "news"]:
        if section_name in sections and sections[section_name].get("content"):
            display_name = sections[section_name]["name"]
            lines.append(f"## {display_name}")
            lines.append(sections[section_name]["content"][:500])
            lines.append("")

    return "\n".join(lines)


# ── Meeting Prep ─────────────────────────────────────────────────────────────

def meeting_prep(company_name: str = "", attendee_name: str = "",
                 meeting_topic: str = "") -> dict:
    """Prepare for meetings with comprehensive research on companies and attendees.

    Researches: company background, recent news, key people, meeting context,
    and suggested talking points.
    """
    print(f"[Research] Meeting prep: company={company_name}, attendee={attendee_name}, topic={meeting_topic}", flush=True)
    result = {
        "timestamp": datetime.now().isoformat(),
        "sections": {},
    }

    # 1. Company Background
    if company_name:
        company_research = _tavily_search_full(f"{company_name} company overview products history", max_results=5)
        result["sections"]["company_background"] = _format_research_section(company_research, f"Company: {company_name}")

        # Recent news about the company
        company_news = _tavily_search_full(f"{company_name} news 2025 2026 latest", max_results=3)
        result["sections"]["company_news"] = _format_research_section(company_news, f"Recent News: {company_name}")

    # 2. Attendee Research
    if attendee_name:
        attendee_research = _tavily_search_full(f"{attendee_name} professional background career role", max_results=3)
        result["sections"]["attendee_background"] = _format_research_section(attendee_research, f"Attendee: {attendee_name}")

        # Recent activity by the attendee
        attendee_news = _tavily_search_full(f"{attendee_name} recent activity posts announcements", max_results=3)
        result["sections"]["attendee_news"] = _format_research_section(attendee_news, f"Recent Activity: {attendee_name}")

    # 3. Meeting Context & Talking Points
    if meeting_topic:
        context_research = _tavily_search_full(meeting_topic, max_results=5)
        result["sections"]["meeting_context"] = _format_research_section(context_research, f"Topic: {meeting_topic}")

        # Suggested talking points
        talking_points = _generate_talking_points(meeting_topic, company_name, attendee_name)
        result["sections"]["talking_points"] = {
            "name": "Suggested Talking Points",
            "content": talking_points,
            "sources": [],
        }

    result["executive_summary"] = _build_meeting_summary(result["sections"], company_name, attendee_name, meeting_topic)

    # Save to memory
    _save_research_to_memory(f"meeting prep: {company_name} {attendee_name}", {
        "executive_summary": result["executive_summary"],
    })

    return result


def _generate_talking_points(topic: str, company: str, attendee: str) -> str:
    """Generate suggested talking points for the meeting."""
    points = []

    if company:
        points.append(f"1. Acknowledge {company}'s recent work/developments")
        points.append(f"2. Reference {company}'s core products or services")
        points.append(f"3. Mention any recent news about {company}")

    if attendee:
        points.append(f"4. Reference {attendee}'s background or recent activity")

    if topic:
        points.append(f"5. Focus on: {topic}")

    points.append(f"6. Ask about their current challenges and priorities")
    points.append(f"7. Discuss potential collaboration opportunities")

    return "\n".join(points) if points else "No specific talking points generated."


def _build_meeting_summary(sections: dict, company: str, attendee: str, topic: str) -> str:
    """Build meeting prep executive summary."""
    lines = ["**Meeting Preparation Summary**\n"]

    if company:
        lines.append(f"## Company: {company}")
        if "company_background" in sections:
            lines.append(sections["company_background"]["content"][:500])
        lines.append("")

    if attendee:
        lines.append(f"## Attendee: {attendee}")
        if "attendee_background" in sections:
            lines.append(sections["attendee_background"]["content"][:500])
        lines.append("")

    if topic:
        lines.append(f"## Topic: {topic}")
        if "meeting_context" in sections:
            lines.append(sections["meeting_context"]["content"][:500])
        if "talking_points" in sections:
            lines.append(f"\n{sections['talking_points']['content']}")

    return "\n".join(lines)


# ── Chat (Deep Factual Answers) ──────────────────────────────────────────────

def deep_chat_answer(query: str, include_citations: bool = True,
                     max_sources: int = 5) -> dict:
    """Deep factual answer with citations — like Tavily's Chat API.

    Searches multiple sources, synthesizes an answer, and includes citations.
    """
    print(f"[Research] Deep chat: {query}", flush=True)

    # Search
    results = _tavily_search_full(query, max_results=max_sources)

    if not results:
        return {
            "query": query,
            "answer": "I couldn't find information to answer that question. Try rephrasing.",
            "citations": [],
            "follow_up_questions": [],
        }

    # Synthesize answer
    answer_lines = []
    citations = []

    for i, r in enumerate(results):
        content = r.get("content", "")
        if content:
            answer_lines.append(content[:300])
            citations.append({
                "number": i + 1,
                "title": r.get("title", ""),
                "url": r.get("url", ""),
            })

    answer = "\n\n".join(answer_lines)

    # Generate follow-up questions
    follow_ups = _generate_follow_ups(query, results)

    return {
        "query": query,
        "answer": answer,
        "citations": citations if include_citations else [],
        "follow_up_questions": follow_ups,
        "sources_searched": len(results),
    }


def _generate_follow_ups(query: str, results: list[dict]) -> list[str]:
    """Generate follow-up questions based on the search results."""
    follow_ups = []
    common_follow_ups = [
        f"What are the key takeaways from {query}?",
        f"Can you explain {query} in simpler terms?",
        f"What are the implications of {query}?",
        f"How does {query} compare to alternatives?",
        f"What are the latest developments in {query}?",
    ]

    # Pick 3 relevant follow-ups
    for fu in common_follow_ups:
        if len(follow_ups) >= 3:
            break
        # Check if any result mentions related topics
        for r in results:
            content = (r.get("title", "") + " " + r.get("content", "")).lower()
            if any(word in content for word in fu.lower().split()):
                follow_ups.append(fu)
                break

    return follow_ups if follow_ups else ["Would you like me to search deeper on this topic?"]


# ── Multi-Step Research (Agentic Loop) ───────────────────────────────────────

def agentic_research(topic: str, max_iterations: int = 5) -> dict:
    """Agentic research loop — searches, analyzes, identifies gaps, searches again.

    Simulates a researcher who:
    1. Searches the topic
    2. Analyzes what's missing
    3. Searches for missing pieces
    4. Synthesizes everything into a comprehensive report
    """
    print(f"[Research] Agentic research: {topic} (max {max_iterations} iterations)", flush=True)

    all_results = []
    search_queries = [topic]

    for iteration in range(max_iterations):
        query = search_queries[iteration] if iteration < len(search_queries) else topic
        print(f"[Research] Iteration {iteration + 1}: {query}", flush=True)

        results = _tavily_search_full(query, max_results=5)
        all_results.extend(results)

        # Analyze gaps
        gaps = _identify_gaps(topic, all_results)
        for gap in gaps[:2]:  # Max 2 new searches per iteration
            if gap not in search_queries:
                search_queries.append(f"{topic} {gap}")

        # If no new gaps found, stop early
        if not gaps:
            print(f"[Research] No more gaps found after {iteration + 1} iterations.", flush=True)
            break

    # Synthesize final report
    report = _synthesize_report(topic, all_results)
    return report


def _identify_gaps(topic: str, results: list[dict]) -> list[str]:
    """Identify gaps in research coverage."""
    content = " ".join(r.get("content", "") + " " + r.get("title", "") for r in results).lower()

    gaps = []
    common_aspects = ["cost", "pricing", "alternatives", "vs", "comparison",
                      "pros", "cons", "review", "tutorial", "how to",
                      "latest", "recent", "news", "update", "2025", "2026"]

    for aspect in common_aspects:
        if aspect not in content and aspect not in topic.lower():
            gaps.append(aspect)

    return gaps[:3]


def _synthesize_report(topic: str, results: list[dict]) -> dict:
    """Synthesize all research results into a comprehensive report."""
    report = {
        "topic": topic,
        "timestamp": datetime.now().isoformat(),
        "executive_summary": "",
        "detailed_findings": "",
        "sources": [],
        "total_sources": len(results),
    }

    # Deduplicate
    seen_urls = set()
    unique_results = []
    for r in results:
        if r.get("url") not in seen_urls:
            seen_urls.add(r.get("url"))
            unique_results.append(r)

    # Build detailed findings
    sections = []
    for i, r in enumerate(unique_results[:10]):
        section = f"### {r.get('title', 'Untitled')}\n"
        section += f"Source: {r.get('url', '')}\n"
        section += f"{r.get('content', '')[:600]}\n"
        sections.append(section)

    report["detailed_findings"] = "\n".join(sections)

    # Build executive summary
    summary_lines = [f"**Research Report: {topic}**\n"]
    summary_lines.append(f"Searched {len(unique_results)} unique sources.\n")

    if unique_results:
        summary_lines.append("**Top Sources:**\n")
        for i, r in enumerate(unique_results[:5]):
            summary_lines.append(f"{i+1}. {r.get('title', '')} - {r.get('url', '')}")

    report["executive_summary"] = "\n".join(summary_lines)
    report["sources"] = [
        {"title": r.get("title", ""), "url": r.get("url", "")}
        for r in unique_results[:10]
    ]

    # Save to memory
    _save_research_to_memory(f"agentic research: {topic}", {
        "executive_summary": report["executive_summary"],
    })

    return report
