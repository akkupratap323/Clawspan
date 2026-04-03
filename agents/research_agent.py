"""ResearchAgent — Deep Research Engine.

Your JARVIS research brain — capable of Tavily-like deep research,
company analysis, market intelligence, meeting prep, and web crawling.

CAPABILITIES:
  🔬 Deep Research — Multi-source, multi-angle research with synthesis
  🏢 Company Researcher — In-depth company profiles (funding, leadership, news, competitors)
  📊 Market Researcher — Stock analysis, market trends, competitor comparison
  🌐 Crawl2RAG — Turn any website into searchable knowledge base
  📅 Meeting Prep — Research companies + attendees before meetings
  💬 Deep Chat — Factual answers with citations
  🔍 Agentic Research — Autonomous multi-iteration research loop
  📄 URL Fetcher — Extract and read content from any URL
  📁 File Reader — Read local documents
  🧠 Memory — Save and recall research findings
"""

from core.base_agent import BaseAgent
from tools.search import tavily_search, duckduckgo_search, fetch_url
from tools.research import (
    deep_research,
    research_company,
    market_research,
    crawl_to_rag,
    meeting_prep,
    deep_chat_answer,
    agentic_research,
)
from tools.files import read_file
from tools import memory as mem_tool

SYSTEM_PROMPT = """You are JARVIS's Deep Research Agent — a world-class research analyst powered by Tavily, web crawling, and AI synthesis.

══ YOUR CAPABILITIES ═══════════════════════════════════════════════════════

🔬 DEEP RESEARCH (deep_research):
  Multi-source, multi-angle research with executive summary, key findings,
  detailed analysis, and ranked sources. Use when user asks "research X",
  "tell me about X in depth", "comprehensive analysis of X".

🏢 COMPANY RESEARCH (research_company):
  Full company profiles: overview, leadership, funding, products, news,
  competitors. Use for "research company X", "tell me about company X",
  "who runs X", "how is X funded".

📊 MARKET RESEARCH (market_research):
  Stock analysis, market trends, competitor comparison, analyst sentiment.
  Use for "analyze stock X", "market trends for X", "how is X stock doing",
  "compare X vs Y".

🌐 CRAWL2RAG (crawl_to_rag):
  Turn any website into a searchable knowledge base. Crawls multiple pages,
  extracts content, saves to memory. Use for "crawl this website",
  "extract content from URL", "save website to knowledge base".

📅 MEETING PREP (meeting_prep):
  Research companies + attendees + generate talking points. Use for
  "prepare for meeting with X", "research before my meeting",
  "what should I know about company X before the meeting".

💬 DEEP CHAT (deep_chat_answer):
  Factual answers with citations and follow-up questions. Use for
  direct questions that need sourced answers.

🔍 AGENTIC RESEARCH (agentic_research):
  Autonomous multi-iteration research that identifies gaps and searches
  deeper. Use for "thorough research on X", "leave no stone unturned on X",
  "deep dive into X".

📄 URL FETCH (fetch_url):
  Extract and read content from any single URL.

📁 FILE READ (read_file):
  Read local documents and files.

🧠 MEMORY (memory_tool):
  Save research findings and recall past research.

══ RESEARCH METHODOLOGY ═══════════════════════════════════════════════════

For DEEP RESEARCH queries:
1. Identify the core question and key angles
2. Search from multiple perspectives (overview, technical, market, news)
3. Extract and synthesize key findings
4. Present executive summary + detailed analysis + ranked sources
5. Save findings to memory for future reference

For COMPANY RESEARCH:
1. Company overview and history
2. Leadership team and key people
3. Funding, valuation, financials
4. Products and technology
5. Recent news and developments
6. Competitive landscape

For MARKET RESEARCH:
1. Stock price and market position
2. Financial performance
3. Competitor analysis
4. Market trends and forecast
5. Analyst sentiment
6. Recent developments

══ RESPONSE QUALITY STANDARDS ═════════════════════════════════════════════

✅ ALWAYS:
- Cite sources with URLs
- Provide executive summary first
- Structure findings logically with headers
- Include both positive and negative perspectives
- Note when information is outdated or uncertain
- Suggest follow-up research directions

❌ NEVER:
- Present opinions as facts
- Cite sources without URLs
- Give shallow one-paragraph answers for research queries
- Skip contradictory information
- Fabricate data or statistics
- Ignore recent developments

══ VOICE MODE ═════════════════════════════════════════════════════════════

When responding via voice (short format):
- Lead with the key finding in 1 sentence
- Mention source count: "Searched 8 sources, here's what I found..."
- Give the most important fact
- Offer to go deeper: "Want me to research any specific aspect?"

For text mode:
- Full structured reports with headers, bullet points, and citations
- Executive summary at the top
- Detailed findings with source links
- Follow-up questions for further exploration"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "deep_research",
            "description": (
                "Multi-source deep research with executive summary, key findings, "
                "detailed analysis, and ranked sources. Searches from multiple angles, "
                "crawls URLs for deep content, and synthesizes a comprehensive report. "
                "Use for: 'research X', 'tell me about X in depth', 'comprehensive analysis of X'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Research topic or question"},
                    "max_sources": {"type": "integer", "description": "Max sources to include (default 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_company",
            "description": (
                "In-depth company research: overview, leadership, funding, products, "
                "news, and competitors. Use for: 'research company X', 'tell me about company X', "
                "'who runs X', 'how is X funded', 'what does company X do'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {"type": "string", "description": "Company name to research"},
                    "include_financials": {"type": "boolean", "description": "Include funding/financial data"},
                    "include_news": {"type": "boolean", "description": "Include recent news"},
                    "include_competitors": {"type": "boolean", "description": "Include competitor analysis"},
                },
                "required": ["company_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "market_research",
            "description": (
                "Comprehensive market research: stock analysis, market trends, "
                "competitor comparison, analyst sentiment. Use for: 'analyze stock X', "
                "'market trends for X', 'how is X stock doing', 'compare X vs Y'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker_or_company": {"type": "string", "description": "Stock ticker or company name"},
                    "include_competitors": {"type": "boolean", "description": "Include competitor analysis"},
                    "include_trends": {"type": "boolean", "description": "Include market trends"},
                },
                "required": ["ticker_or_company"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crawl_to_rag",
            "description": (
                "Turn any website into a searchable knowledge base. Crawls multiple pages, "
                "extracts content, and saves to memory. Use for: 'crawl this website', "
                "'extract content from URL', 'save website to knowledge base'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Website URL to crawl"},
                    "max_pages": {"type": "integer", "description": "Max pages to crawl (default 5)"},
                    "save_to_memory": {"type": "boolean", "description": "Save to knowledge base"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "meeting_prep",
            "description": (
                "Meeting preparation: research companies, attendees, and generate talking points. "
                "Use for: 'prepare for meeting with X', 'research before my meeting', "
                "'what should I know about company X'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {"type": "string", "description": "Company name"},
                    "attendee_name": {"type": "string", "description": "Attendee name"},
                    "meeting_topic": {"type": "string", "description": "Meeting topic or agenda"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deep_chat_answer",
            "description": (
                "Deep factual answer with citations and follow-up questions. "
                "Use for direct questions that need sourced answers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Question to answer"},
                    "include_citations": {"type": "boolean", "description": "Include source citations"},
                    "max_sources": {"type": "integer", "description": "Max sources (default 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agentic_research",
            "description": (
                "Autonomous multi-iteration research that identifies gaps and searches deeper. "
                "Use for: 'thorough research on X', 'leave no stone unturned on X', 'deep dive into X'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Research topic"},
                    "max_iterations": {"type": "integer", "description": "Max research iterations (default 5)"},
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch and read text content of any URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information. Returns top results with titles, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Max results (default 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a local file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "File path to read"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_tool",
            "description": "Save or recall facts. Actions: save, recall, list, forget.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["save", "recall", "list", "forget"]},
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["action"],
            },
        },
    },
]


# ── Tool Implementations ─────────────────────────────────────────────────────

def _deep_research(args: dict) -> str:
    result = deep_research(args["query"], args.get("max_sources", 10))
    return _format_deep_research_result(result)


def _research_company(args: dict) -> str:
    result = research_company(
        args["company_name"],
        include_financials=args.get("include_financials", True),
        include_news=args.get("include_news", True),
        include_competitors=args.get("include_competitors", True),
    )
    return _format_company_result(result)


def _market_research(args: dict) -> str:
    result = market_research(
        args["ticker_or_company"],
        include_competitors=args.get("include_competitors", True),
        include_trends=args.get("include_trends", True),
    )
    return _format_market_result(result)


def _crawl_to_rag(args: dict) -> str:
    result = crawl_to_rag(
        args["url"],
        max_pages=args.get("max_pages", 5),
        save_to_memory=args.get("save_to_memory", True),
    )
    return result.get("summary", "Crawl completed.")


def _meeting_prep(args: dict) -> str:
    result = meeting_prep(
        company_name=args.get("company_name", ""),
        attendee_name=args.get("attendee_name", ""),
        meeting_topic=args.get("meeting_topic", ""),
    )
    return result.get("executive_summary", "Meeting prep completed.")


def _deep_chat_answer(args: dict) -> str:
    result = deep_chat_answer(
        args["query"],
        include_citations=args.get("include_citations", True),
        max_sources=args.get("max_sources", 5),
    )
    return _format_chat_result(result)


def _agentic_research(args: dict) -> str:
    result = agentic_research(args["topic"], args.get("max_iterations", 5))
    return _format_agentic_result(result)


def _web_search(args: dict) -> str:
    return tavily_search(args["query"], args.get("max_results", 5))


def _fetch_url(args: dict) -> str:
    return fetch_url(args["url"])


def _read_file(args: dict) -> str:
    return read_file(args["file_path"])


def _memory_tool(args: dict) -> str:
    action = args["action"]
    if action == "save":
        return mem_tool.save(args.get("key", ""), args.get("value", ""))
    if action == "recall":
        return mem_tool.recall(args.get("query", "") or args.get("key", ""))
    if action == "list":
        return mem_tool.list_all()
    if action == "forget":
        return mem_tool.forget(args.get("key", ""))
    return f"Unknown memory action: {action}"


# ── Result Formatters ────────────────────────────────────────────────────────

def _format_deep_research_result(result: dict) -> str:
    lines = [f"# Research Report: {result['query']}\n"]

    if result.get("executive_summary"):
        lines.append(f"## Executive Summary\n{result['executive_summary']}\n")

    if result.get("key_findings"):
        lines.append("## Key Findings\n")
        for f in result["key_findings"]:
            lines.append(f"- {f}")
        lines.append("")

    if result.get("detailed_analysis"):
        lines.append("## Detailed Analysis\n")
        lines.append(result["detailed_analysis"])

    if result.get("sources"):
        lines.append(f"\n## Sources ({len(result['sources'])})\n")
        for i, s in enumerate(result["sources"], 1):
            lines.append(f"{i}. [{s['title']}]({s['url']})")

    return "\n".join(lines)


def _format_company_result(result: dict) -> str:
    lines = [f"# Company Research: {result['company']}\n"]

    if result.get("executive_summary"):
        lines.append(f"## Executive Summary\n{result['executive_summary']}\n")

    sections = result.get("sections", {})
    for section_key in ["overview", "leadership", "financials", "products", "news", "competitors"]:
        if section_key in sections:
            section = sections[section_key]
            lines.append(f"## {section['name']}\n")
            lines.append(section["content"][:2000])
            if section.get("sources"):
                lines.append("\n**Sources:**")
                for s in section["sources"]:
                    lines.append(f"- [{s['title']}]({s['url']})")
            lines.append("")

    return "\n".join(lines)


def _format_market_result(result: dict) -> str:
    lines = [f"# Market Research: {result['subject']}\n"]

    if result.get("executive_summary"):
        lines.append(f"## Executive Summary\n{result['executive_summary']}\n")

    sections = result.get("sections", {})
    for section_key in ["overview", "financials", "competitors", "trends", "analyst_sentiment", "news"]:
        if section_key in sections:
            section = sections[section_key]
            lines.append(f"## {section['name']}\n")
            lines.append(section["content"][:1500])
            lines.append("")

    return "\n".join(lines)


def _format_chat_result(result: dict) -> str:
    lines = [f"## Answer: {result['query']}\n"]
    lines.append(result["answer"])

    if result.get("citations"):
        lines.append("\n### Citations\n")
        for c in result["citations"]:
            lines.append(f"[{c['number']}] [{c['title']}]({c['url']})")

    if result.get("follow_up_questions"):
        lines.append("\n### Follow-up Questions\n")
        for q in result["follow_up_questions"]:
            lines.append(f"- {q}")

    return "\n".join(lines)


def _format_agentic_result(result: dict) -> str:
    lines = [f"# Agentic Research Report: {result['topic']}\n"]

    if result.get("executive_summary"):
        lines.append(f"## Executive Summary\n{result['executive_summary']}\n")

    lines.append(f"**Sources analyzed:** {result.get('total_sources', 0)}\n")

    if result.get("detailed_findings"):
        lines.append("## Detailed Findings\n")
        lines.append(result["detailed_findings"])

    if result.get("sources"):
        lines.append(f"\n## Sources ({len(result['sources'])})\n")
        for i, s in enumerate(result["sources"], 1):
            lines.append(f"{i}. [{s['title']}]({s['url']})")

    return "\n".join(lines)


# ── Agent Class ──────────────────────────────────────────────────────────────

class ResearchAgent(BaseAgent):
    name = "ResearchAgent"
    SYSTEM_PROMPT = SYSTEM_PROMPT
    TOOLS = TOOLS
    TOOL_MAP = {
        "deep_research": _deep_research,
        "research_company": _research_company,
        "market_research": _market_research,
        "crawl_to_rag": _crawl_to_rag,
        "meeting_prep": _meeting_prep,
        "deep_chat_answer": _deep_chat_answer,
        "agentic_research": _agentic_research,
        "fetch_url": _fetch_url,
        "web_search": _web_search,
        "read_file": _read_file,
        "memory_tool": _memory_tool,
    }
    temperature = 0.3
    max_tokens = 4096  # Large output for research reports
    max_tool_rounds = 12  # Deep research needs more iterations
    max_history = 30

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print(
            "[ResearchAgent] Deep research engine ready — "
            "Tavily search, company research, market analysis, "
            "Crawl2RAG, meeting prep, agentic research.",
            flush=True,
        )
