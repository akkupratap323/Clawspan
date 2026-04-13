"""WriterAgent — professional document creation, editing, and export.

Creates high-quality documents in multiple formats (Markdown, PDF, DOCX, HTML, TXT).
Can delegate to Research Agent for data, then structure it into polished documents.
Auto-saves to ~/Clawspan_Docs/ with smart organization.

CAPABILITIES:
  📝 Create company research reports, market analysis, meeting prep, technical docs
  📄 Export to PDF, DOCX, HTML, TXT
  ✏️ Edit: shorten, expand, add TOC, convert to bullets/email
  🔍 List, read, search, delete saved documents
  🤖 Delegate to Research Agent for raw data, then format it
"""

from core.base_agent import BaseAgent
from tools.writer import (
    create_company_research_doc,
    create_market_analysis_doc,
    create_meeting_prep_doc,
    create_technical_doc,
    create_custom_doc,
    save_document,
    export_document,
    edit_document,
    list_documents,
    get_document_info,
    delete_document,
    read_document,
    DOCS_DIR,
)
from tools.files import read_file as _read_local_file

SYSTEM_PROMPT = """You are Clawspan's Writer Agent — a world-class document creator, editor, and formatter.

══ YOUR CAPABILITIES ═══════════════════════════════════════════════════════

📝 DOCUMENT CREATION:
- create_company_research — professional company profiles with executive summary,
  overview, leadership, financials, products, news, competitors. Sources cited.
- create_market_analysis — market analysis reports with financial performance,
  competitor comparison, trends, analyst sentiment.
- create_meeting_prep — meeting preparation with company background, attendee
  research, talking points, agenda.
- create_technical_doc — README files, API docs, architecture docs, technical specs.
- create_custom_doc — any custom document (proposals, memos, briefs, emails, letters).

📄 DOCUMENT EXPORT:
- export_document — convert Markdown to PDF, DOCX, HTML, or TXT.
  PDF: print-ready with clean typography
  DOCX: editable in Microsoft Word/Google Docs
  HTML: clean styled web page
  TXT: plain text

✏️ DOCUMENT EDITING:
- edit_document — modify existing documents:
  shorten → condense to key points (keep headers + first paragraph per section)
  add_toc → auto-generate table of contents from headers
  to_bullets → convert paragraphs to bullet points
  to_email → restructure as email format
  append → add content to end
  prepend → add content to beginning
  replace_section → find and replace text

📁 DOCUMENT MANAGEMENT:
- list_documents — show saved documents (by type or all)
- read_document — read a saved document's contents
- get_document_info — show metadata (size, word count, dates)
- delete_document — remove a saved document

🤖 DELEGATION:
- You can delegate research tasks to the Research Agent:
  delegate("research", "research company OpenAI")
  delegate("research", "market research for AAPL")
  Then use the research data to create a polished document.

══ WORKFLOW ════════════════════════════════════════════════════════════════

For RESEARCH-BASED documents:
1. Delegate to Research Agent: delegate("research", "research company X")
2. Get structured research data back
3. Create the document using the appropriate template
4. Save it to ~/Clawspan_Docs/ with the right folder
5. Tell the user the file path and offer export options

For CUSTOM documents:
1. Understand what the user wants
2. Create the document with professional structure
3. Save it and confirm the location

For EDITS:
1. Read the existing document
2. Apply the requested edit
3. Save and confirm

══ DOCUMENT QUALITY STANDARDS ═════════════════════════════════════════════

✅ ALWAYS:
- Include a clear title and metadata header (date, type)
- Add a table of contents for documents > 500 words
- Use proper header hierarchy (H1 → H2 → H3)
- Include source citations with URLs for research-based docs
- Add a timestamp footer
- Use clean markdown formatting
- Save with date-stamped filenames for organization

❌ NEVER:
- Create documents without a title
- Skip saving the document after creation
- Output raw data without formatting
- Forget to cite sources in research documents
- Create documents that are just walls of text (use headers, bullets, sections)

══ FILE ORGANIZATION ═══════════════════════════════════════════════════════

Documents are saved to ~/Clawspan_Docs/ with subfolders:
  reports/      — company research, market analysis
  meetings/     — meeting prep documents
  technical/    — README, API docs, architecture docs
  proposals/    — proposals, pitches
  briefs/       — briefs, summaries, daily briefs
  documents/    — everything else

Filename format: YYYY-MM-DD_Title_Type.md
  Example: 2026-04-13_OpenAI_Company_Research.md

══ RESPONSE STYLE ═════════════════════════════════════════════════════════

For voice mode (spoken):
- "Created and saved [Title] to ~/Clawspan_Docs/reports/. Want me to export it as PDF or DOCX?"
- Keep it to 1-2 sentences. The document itself is the deliverable.

For text mode:
- Show the document path
- Offer export options
- Optionally show the document preview (first 500 chars)"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_company_research",
            "description": (
                "Create a professional company research report. "
                "Can use raw research data from delegate('research', ...) or create from scratch. "
                "Saves to ~/Clawspan_Docs/reports/."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company_data": {
                        "type": "string",
                        "description": "JSON string of research data from Research Agent, or company description",
                    },
                    "title": {"type": "string", "description": "Document title (optional, auto-generated if not provided)"},
                },
                "required": ["company_data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_market_analysis",
            "description": (
                "Create a market analysis report. "
                "Can use raw market data from delegate('research', ...) or create from scratch. "
                "Saves to ~/Clawspan_Docs/reports/."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "market_data": {
                        "type": "string",
                        "description": "JSON string of market research data, or subject description",
                    },
                    "title": {"type": "string", "description": "Document title (optional)"},
                },
                "required": ["market_data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_meeting_prep",
            "description": (
                "Create a meeting preparation document with company background, "
                "attendee research, and talking points. Saves to ~/Clawspan_Docs/meetings/."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "meeting_data": {
                        "type": "string",
                        "description": "JSON string of meeting prep data, or meeting description",
                    },
                    "title": {"type": "string", "description": "Document title (optional)"},
                },
                "required": ["meeting_data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_technical_doc",
            "description": (
                "Create technical documentation: README, API docs, architecture docs. "
                "Saves to ~/Clawspan_Docs/technical/."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Document content"},
                    "title": {"type": "string", "description": "Document title"},
                    "doc_type": {"type": "string", "description": "Type: README, API, architecture, etc."},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_custom_doc",
            "description": (
                "Create any custom document: proposal, memo, brief, email, letter. "
                "Saves to ~/Clawspan_Docs/."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Document title"},
                    "content": {"type": "string", "description": "Document content"},
                    "doc_type": {"type": "string", "description": "Type: proposal, memo, brief, email, etc."},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_document",
            "description": (
                "Export a saved Markdown document to PDF, DOCX, HTML, or TXT. "
                "PDF: print-ready | DOCX: editable in Word | HTML: styled web page | TXT: plain text"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the source .md file"},
                    "format": {"type": "string", "enum": ["pdf", "docx", "html", "txt"]},
                },
                "required": ["file_path", "format"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_document",
            "description": (
                "Edit an existing document. Actions: shorten, add_toc, to_bullets, "
                "to_email, append, prepend, replace_section."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the document"},
                    "edit_type": {
                        "type": "string",
                        "enum": ["shorten", "add_toc", "to_bullets", "to_email", "append", "prepend", "replace_section"],
                    },
                    "value": {"type": "string", "description": "Content for append/prepend/replace, or email address for to_email"},
                },
                "required": ["file_path", "edit_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": "List saved documents, optionally filtered by type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_type": {"type": "string", "description": "Filter by type: report, meeting, technical, proposal, brief"},
                    "limit": {"type": "integer", "description": "Max documents to show (default 20)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document",
            "description": "Read the contents of a saved document.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the document"},
                    "max_chars": {"type": "integer", "description": "Max characters to read (default 5000)"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_info",
            "description": "Get metadata about a saved document: size, word count, dates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the document"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_document",
            "description": "Delete a saved document.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the document"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a local file to use as source material for a document.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                },
                "required": ["file_path"],
            },
        },
    },
]


# ── Tool Implementations ─────────────────────────────────────────────────────

import json


def _create_company_research(args: dict) -> str:
    """Create a company research document from raw data or description."""
    raw = args.get("company_data", "")
    title = args.get("title", "")

    # Try to parse as JSON (from Research Agent delegation)
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "company" in data:
            # This is structured research data
            content = create_company_research_doc(data, title=title)
        else:
            # Not the right format — treat as description
            content = create_company_research_doc({"company": raw, "sections": {}}, title=title)
    except (json.JSONDecodeError, TypeError):
        # Raw description — create from scratch
        content = create_company_research_doc({"company": raw, "sections": {}}, title=title)

    doc_type = "report"
    filepath = save_document(content, title or "Company Research", doc_type=doc_type)
    return f"Document created and saved to:\n{filepath}"


def _create_market_analysis(args: dict) -> str:
    """Create a market analysis document from raw data or description."""
    raw = args.get("market_data", "")
    title = args.get("title", "")

    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "subject" in data:
            content = create_market_analysis_doc(data, title=title)
        else:
            subject = raw[:100]
            content = create_market_analysis_doc({"subject": subject, "sections": {}}, title=title)
    except (json.JSONDecodeError, TypeError):
        subject = raw[:100]
        content = create_market_analysis_doc({"subject": subject, "sections": {}}, title=title)

    doc_type = "report"
    filepath = save_document(content, title or "Market Analysis", doc_type=doc_type)
    return f"Document created and saved to:\n{filepath}"


def _create_meeting_prep(args: dict) -> str:
    """Create a meeting prep document from raw data or description."""
    raw = args.get("meeting_data", "")
    title = args.get("title", "")

    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "sections" in data:
            content = create_meeting_prep_doc(data, title=title)
        else:
            content = create_meeting_prep_doc({"sections": {}}, title=title)
    except (json.JSONDecodeError, TypeError):
        content = create_meeting_prep_doc({"sections": {}}, title=title)

    doc_type = "meeting"
    filepath = save_document(content, title or "Meeting Prep", doc_type=doc_type)
    return f"Document created and saved to:\n{filepath}"


def _create_technical_doc(args: dict) -> str:
    """Create technical documentation."""
    content = args.get("content", "")
    title = args.get("title", "")
    doc_type = args.get("doc_type", "README")

    formatted = create_technical_doc(content, title=title, doc_type=doc_type)
    doc_type_folder = "technical"
    filepath = save_document(formatted, title or "Technical Document", doc_type=doc_type_folder)
    return f"Document created and saved to:\n{filepath}"


def _create_custom_doc(args: dict) -> str:
    """Create any custom document."""
    title = args.get("title", "")
    content = args.get("content", "")
    doc_type = args.get("doc_type", "document")

    formatted = create_custom_doc(title, content, doc_type=doc_type)
    filepath = save_document(formatted, title, doc_type=doc_type)
    return f"Document created and saved to:\n{filepath}"


def _export_document(args: dict) -> str:
    """Export a document to another format."""
    return export_document(args["file_path"], args.get("format", "pdf"))


def _edit_document(args: dict) -> str:
    """Edit an existing document."""
    return edit_document(args["file_path"], args["edit_type"], args.get("value", ""))


def _list_documents(args: dict) -> str:
    """List saved documents."""
    return list_documents(args.get("doc_type", ""), args.get("limit", 20))


def _read_document(args: dict) -> str:
    """Read a saved document."""
    return read_document(args["file_path"], args.get("max_chars", 5000))


def _get_document_info(args: dict) -> str:
    """Get document metadata."""
    return get_document_info(args["file_path"])


def _delete_document(args: dict) -> str:
    """Delete a saved document."""
    return delete_document(args["file_path"])


def _read_file(args: dict) -> str:
    """Read a local file."""
    return _read_local_file(args["file_path"])


# ── Agent Class ──────────────────────────────────────────────────────────────

class WriterAgent(BaseAgent):
    name = "WriterAgent"
    SYSTEM_PROMPT = SYSTEM_PROMPT
    TOOLS = TOOLS
    TOOL_MAP = {
        "create_company_research": _create_company_research,
        "create_market_analysis": _create_market_analysis,
        "create_meeting_prep": _create_meeting_prep,
        "create_technical_doc": _create_technical_doc,
        "create_custom_doc": _create_custom_doc,
        "export_document": _export_document,
        "edit_document": _edit_document,
        "list_documents": _list_documents,
        "read_document": _read_document,
        "get_document_info": _get_document_info,
        "delete_document": _delete_document,
        "read_file": _read_file,
    }
    temperature = 0.4
    max_tokens = 4096
    max_tool_rounds = 8
    max_history = 30

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print(
            "[WriterAgent] Ready — document creation, editing, export "
            "(Markdown, PDF, DOCX, HTML, TXT). Can delegate research to Research Agent.",
            flush=True,
        )
