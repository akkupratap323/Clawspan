"""
Document Creation Engine — create, format, export documents.

Creates professional-quality documents in multiple formats:
  - Markdown (.md) — source of truth, clean and versionable
  - PDF (.pdf) — via weasyprint, print-ready
  - DOCX (.docx) — via python-docx, editable in Word
  - HTML (.html) — clean styled HTML
  - Plain text (.txt) — simple and clean

Templates:
  - Company Research Report
  - Market Analysis Report
  - Meeting Preparation Document
  - Technical Documentation (README, API docs)
  - Proposal / Brief / Memo
  - Custom Document

Auto-organization:
  ~/JARVIS_Docs/
  ├── reports/
  ├── meetings/
  ├── technical/
  ├── proposals/
  └── briefs/
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
from datetime import datetime
from typing import Any


# ── Content Cleaning ─────────────────────────────────────────────────────────

def _clean_content_for_doc(text: str) -> str:
    """Clean raw research content before inserting into a professional document.

    Removes:
    - Markdown sub-headers from scraped content (### Source Title)
    - Remaining UI/navigation artifacts
    - Table formatting garbage
    - Duplicate paragraphs
    - Very short fragments
    """
    if not text:
        return ""

    lines = text.split("\n")
    cleaned = []
    seen = set()

    noise_patterns = [
        "hero section", "skip to content", "javascript is disabled",
        "we have received your inquiry", "copyright", "all rights reserved",
        "powered by", "chrome web store", "firefox extension",
        "tracxn", "prospeo", "logo for", "logo of", "footer-bottom",
        "try our premium", "illustration", "icon", "flag of",
        "view details", "view all", "read more", "learn more",
        "srsltid", "utm_", "pdf illustration", "chrome_extension",
        "navbar", "mobile menu", "back to top", "scroll to top",
        "anniversary-logo", "footer-bottom-logos",
        "overviewemails", "formataboutemployees", "tech stacktrending",
        "view company", "key contacts at", "view all employees",
    ]

    for line in lines:
        stripped = line.strip()

        # Skip sub-headers from scraped content
        if re.match(r'^#{3,}\s+', stripped):
            continue

        # Skip empty
        if not stripped:
            continue

        # Skip lines that are primarily source attribution (contain URL-like patterns or source brands)
        source_brands = ["tracxn.com", "prospeo.io", "crunchbase.com", "linkedin.com/company"]
        if any(b in stripped.lower() for b in source_brands):
            continue
        # Also skip lines that are just source titles
        if re.match(r'^#{1,3}\s+.*\|.*\b(tracxn|prospeo|crunchbase|linkedin)\b', stripped, re.IGNORECASE):
            continue

        # Skip noise
        lower = stripped.lower()
        if any(p in lower for p in noise_patterns):
            continue

        # Skip URLs
        if stripped.startswith("http") or stripped.startswith("www."):
            continue

        # Skip table formatting
        if stripped in ("---", "|", "|---|", "| |"):
            continue

        # Skip very short lines (< 15 chars) unless they look like data
        if len(stripped) < 15 and not any(c.isdigit() for c in stripped):
            continue

        # Deduplicate
        key = stripped.lower().strip(".,!? ")
        if key and len(key) > 20:
            if key in seen:
                continue
            seen.add(key)

        cleaned.append(stripped)

    result = "\n".join(cleaned)
    result = re.sub(r'\n{3,}', '\n\n', result).strip()
    return result

# ── Document Storage ─────────────────────────────────────────────────────────

DOCS_DIR = os.path.expanduser("~/JARVIS_Docs")

DOC_SUBFOLDERS = {
    "report": "reports",
    "meeting": "meetings",
    "technical": "technical",
    "proposal": "proposals",
    "brief": "briefs",
    "default": "documents",
}


def _get_subfolder(doc_type: str) -> str:
    """Get subfolder for document type."""
    for key, folder in DOC_SUBFOLDERS.items():
        if key in doc_type.lower():
            return folder
    return DOC_SUBFOLDERS["default"]


def _generate_filename(title: str, doc_type: str = "document") -> str:
    """Generate a clean, date-stamped filename."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    # Clean title: lowercase, replace spaces/special chars with underscores
    clean = re.sub(r'[^a-zA-Z0-9\s_-]', '', title)
    clean = re.sub(r'[\s]+', '_', clean).strip('_')
    clean = clean[:60]  # Truncate long titles
    if doc_type == "report":
        return f"{date_str}_{clean}_Report.md"
    elif doc_type == "meeting":
        return f"{date_str}_{clean}_Meeting_Prep.md"
    elif doc_type == "technical":
        return f"{clean}.md"
    return f"{date_str}_{clean}.md"


def _ensure_dirs() -> None:
    """Ensure document directories exist."""
    os.makedirs(DOCS_DIR, exist_ok=True)
    for folder in DOC_SUBFOLDERS.values():
        os.makedirs(os.path.join(DOCS_DIR, folder), exist_ok=True)


# ── Document Templates ───────────────────────────────────────────────────────

def create_company_research_doc(company_data: dict, title: str = "") -> str:
    """Create a professional company research report from raw research data.

    Input: dict from research_company() or similar
    Output: Formatted markdown document
    """
    _ensure_dirs()

    company = company_data.get("company", "Unknown Company")
    doc_title = title or f"{company} Company Research Report"
    sections = company_data.get("sections", {})

    lines = []

    # Header
    lines.append(f"# {doc_title}")
    lines.append("")
    lines.append(f"> **Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    lines.append(f"> **Company:** {company}")
    lines.append(f"> **Type:** Company Research Report")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Table of Contents
    lines.append("## Table of Contents")
    lines.append("")
    lines.append("- [Executive Summary](#executive-summary)")
    if "overview" in sections: lines.append("- [Company Overview](#company-overview)")
    if "leadership" in sections: lines.append("- [Leadership & Team](#leadership--team)")
    if "financials" in sections: lines.append("- [Funding & Financials](#funding--financials)")
    if "products" in sections: lines.append("- [Products & Technology](#products--technology)")
    if "news" in sections: lines.append("- [Recent News](#recent-news)")
    if "competitors" in sections: lines.append("- [Competitive Landscape](#competitive-landscape)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Executive Summary — preserve the upstream research's own structure by
    # demoting top-level headings (# / ##) to ### / #### so they nest cleanly
    # under our ## Executive Summary anchor. Previously we stripped every
    # leading # which produced a wall of unformatted text.
    lines.append("## Executive Summary")
    lines.append("")
    exec_summary = company_data.get("executive_summary", "")
    exec_demoted = re.sub(r'^(#{1,4})\s', lambda m: '#' * (len(m.group(1)) + 2) + ' ', exec_summary, flags=re.MULTILINE)
    lines.append(exec_demoted or f"This report provides a comprehensive analysis of {company}.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Sections
    section_map = {
        "overview": ("Company Overview", True),
        "leadership": ("Leadership & Team", True),
        "financials": ("Funding & Financials", True),
        "products": ("Products & Technology", True),
        "news": ("Recent News", True),
        "competitors": ("Competitive Landscape", True),
    }

    for key, (display_name, _) in section_map.items():
        if key in sections:
            section = sections[key]
            lines.append(f"## {display_name}")
            lines.append("")
            content = section.get("content", "")
            # Clean raw scraped content before inserting into document
            content = _clean_content_for_doc(content)[:3000]
            lines.append(content)
            lines.append("")

            # Sources — clean titles, strip tracking params, hide platform names
            if section.get("sources"):
                lines.append("**Sources:**")
                for i, s in enumerate(section["sources"], 1):
                    title = s.get("title", "Source")
                    url = s.get("url", "")
                    # Clean source title — remove platform branding (pipe or hyphen separated)
                    title = re.sub(r'\s*[\-|]\s*\b(Tracxn|Prospeo|Crunchbase|LinkedIn|CB Insights|Glassdoor|IPo Platform|Enablers|Inc42)\b.*$', '', title, flags=re.IGNORECASE)
                    # Remove "NESTERLABS - 2026 Company Profile" patterns
                    title = re.sub(r'^NESTER?LABS?\s*[-–—]\s*\d{4}\s+Company Profile\s*$', 'Company Profile', title, flags=re.IGNORECASE)
                    # Clean URL — remove tracking params
                    url = re.sub(r'[?&](srsltid|utm_[^&]+|ref|fbclid|gclid)=[^&]*', '', url)
                    lines.append(f"{i}. [{title}]({url})")
            lines.append("")
            lines.append("---")
            lines.append("")

    # Footer
    lines.append("")
    lines.append("---")
    lines.append(f"*Report generated by JARVIS Writer on {datetime.now().strftime('%B %d, %Y')}*")
    lines.append("")

    return "\n".join(lines)


def create_market_analysis_doc(market_data: dict, title: str = "") -> str:
    """Create a market analysis report from raw research data."""
    _ensure_dirs()

    subject = market_data.get("subject", "Unknown")
    doc_title = title or f"{subject} Market Analysis Report"
    sections = market_data.get("sections", {})

    lines = []
    lines.append(f"# {doc_title}")
    lines.append("")
    lines.append(f"> **Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    lines.append(f"> **Subject:** {subject}")
    lines.append(f"> **Type:** Market Analysis Report")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Table of Contents
    lines.append("## Table of Contents")
    lines.append("")
    toc_items = ["[Executive Summary](#executive-summary)"]
    section_names = {
        "overview": "Market Overview",
        "financials": "Financial Performance",
        "competitors": "Competitor Analysis",
        "trends": "Market Trends & Outlook",
        "analyst_sentiment": "Analyst Sentiment",
        "news": "Recent Developments",
    }
    for key, name in section_names.items():
        if key in sections:
            toc_items.append(f"- [{name}](#{name.lower().replace(' ', '-')})")
    lines.extend(toc_items)
    lines.append("")
    lines.append("---")
    lines.append("")

    # Executive Summary — same heading-demotion rule as the company template
    # so the upstream research structure survives intact.
    lines.append("## Executive Summary")
    lines.append("")
    exec_summary = market_data.get("executive_summary", "")
    exec_demoted = re.sub(r'^(#{1,4})\s', lambda m: '#' * (len(m.group(1)) + 2) + ' ', exec_summary, flags=re.MULTILINE)
    lines.append(exec_demoted or f"This report provides a market analysis of {subject}.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Sections
    for key, display_name in section_names.items():
        if key in sections:
            section = sections[key]
            lines.append(f"## {display_name}")
            lines.append("")
            content = section.get("content", "")
            content = _clean_content_for_doc(content)[:3000]
            lines.append(content)
            lines.append("")
            lines.append("---")
            lines.append("")

    lines.append("")
    lines.append(f"*Report generated by JARVIS Writer on {datetime.now().strftime('%B %d, %Y')}*")
    lines.append("")

    return "\n".join(lines)


def create_meeting_prep_doc(meeting_data: dict, title: str = "") -> str:
    """Create a meeting preparation document."""
    _ensure_dirs()

    sections = meeting_data.get("sections", {})
    company = ""
    attendee = ""
    topic = ""
    for sec_name, sec_data in sections.items():
        if "company" in sec_name.lower():
            company = sec_data.get("name", "").replace("Company: ", "")
        elif "attendee" in sec_name.lower():
            attendee = sec_data.get("name", "").replace("Attendee: ", "")
        elif "topic" in sec_name.lower():
            topic = sec_data.get("name", "").replace("Topic: ", "")

    doc_title = title or f"Meeting Prep: {company or 'Unknown'}"

    lines = []
    lines.append(f"# {doc_title}")
    lines.append("")
    lines.append(f"> **Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    if company: lines.append(f"> **Company:** {company}")
    if attendee: lines.append(f"> **Attendee:** {attendee}")
    if topic: lines.append(f"> **Topic:** {topic}")
    lines.append(f"> **Type:** Meeting Preparation")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Table of Contents
    lines.append("## Table of Contents")
    lines.append("")
    for sec_data in sections.values():
        name = sec_data.get("name", "")
        anchor = name.lower().replace(" ", "-")
        lines.append(f"- [{name}](#{anchor})")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Sections
    for sec_data in sections.values():
        name = sec_data.get("name", "")
        content = sec_data.get("content", "")
        lines.append(f"## {name}")
        lines.append("")
        content_clean = re.sub(r'^#+\s*.*$', '', content, flags=re.MULTILINE).strip()
        lines.append(content_clean[:2000])
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("")
    lines.append(f"*Prepared by JARVIS Writer on {datetime.now().strftime('%B %d, %Y')}*")
    lines.append("")

    return "\n".join(lines)


def create_technical_doc(content: str, title: str = "", doc_type: str = "README") -> str:
    """Create technical documentation (README, API docs, architecture docs)."""
    _ensure_dirs()

    doc_title = title or f"{doc_type} Document"

    if doc_type.upper() == "README":
        lines = []
        lines.append(f"# {doc_title}")
        lines.append("")
        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append(f"*Generated by JARVIS Writer on {datetime.now().strftime('%B %d, %Y')}*")
        lines.append("")
        return "\n".join(lines)

    # Generic technical doc
    lines = []
    lines.append(f"# {doc_title}")
    lines.append("")
    lines.append(f"> **Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    lines.append(f"> **Type:** {doc_type}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(content)
    lines.append("")
    return "\n".join(lines)


def create_custom_doc(title: str, content: str, doc_type: str = "document") -> str:
    """Create a custom document with the given content."""
    _ensure_dirs()

    lines = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"> **Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    lines.append(f"> **Type:** {doc_type.title()}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(content)
    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by JARVIS Writer on {datetime.now().strftime('%B %d, %Y')}*")
    lines.append("")
    return "\n".join(lines)


# ── Save Document ─────────────────────────────────────────────────────────────

def save_document(content: str, title: str, doc_type: str = "document",
                  folder: str = "") -> str:
    """Save a markdown document to the appropriate folder.

    Returns the full file path.
    """
    _ensure_dirs()

    subfolder = folder or _get_subfolder(doc_type)
    filename = _generate_filename(title, doc_type)
    filepath = os.path.join(DOCS_DIR, subfolder, filename)

    with open(filepath, "w") as f:
        f.write(content)

    return filepath


# ── Export Document ──────────────────────────────────────────────────────────

def export_document(source_path: str, output_format: str = "pdf") -> str:
    """Export a markdown document to another format.

    Formats: pdf, docx, html, txt

    Returns the exported file path.
    """
    if not os.path.exists(source_path):
        return f"Source file not found: {source_path}"

    base = os.path.splitext(source_path)[0]

    if output_format == "pdf":
        output_path = f"{base}.pdf"
        return _export_to_pdf(source_path, output_path)
    elif output_format == "docx":
        output_path = f"{base}.docx"
        return _export_to_docx(source_path, output_path)
    elif output_format == "html":
        output_path = f"{base}.html"
        return _export_to_html(source_path, output_path)
    elif output_format == "txt":
        output_path = f"{base}.txt"
        return _export_to_txt(source_path, output_path)

    return f"Unsupported format: {output_format}. Use: pdf, docx, html, txt"


def _export_to_pdf(source: str, output: str) -> str:
    """Export markdown to PDF via weasyprint."""
    try:
        # Convert md → HTML first (using pandoc for clean output)
        html_content = _md_to_html(source)
        styled_html = _add_pdf_styles(html_content)

        from weasyprint import HTML
        HTML(string=styled_html).write_pdf(output)
        return f"PDF saved: {output}"
    except Exception as e:
        return f"PDF export error: {e}"


def _export_to_docx(source: str, output: str) -> str:
    """Export markdown to DOCX via python-docx (manual parsing for clean output)."""
    try:
        import docx
        from docx.shared import Pt, Inches, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = docx.Document()

        # Set default font
        style = doc.styles['Normal']
        font = style.font
        font.name = 'Calibri'
        font.size = Pt(11)

        with open(source) as f:
            content = f.read()

        lines = content.split("\n")
        for line in lines:
            line = line.rstrip()

            # Empty line
            if not line.strip():
                doc.add_paragraph("")
                continue

            # Headers
            header_match = re.match(r'^(#{1,6})\s+(.*)', line)
            if header_match:
                level = len(header_match.group(1))
                text = header_match.group(2)
                h = doc.add_heading(text, level=level)
                continue

            # Blockquote
            if line.startswith("> "):
                p = doc.add_paragraph(line[2:], style='Intense Quote')
                continue

            # Horizontal rule
            if line.strip() == "---" or line.strip() == "***":
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(6)
                p.paragraph_format.space_after = Pt(6)
                from docx.oxml.ns import qn
                pPr = p._p.get_or_add_pPr()
                pBdr = docx.oxml.OxmlElement('w:pBdr')
                bottom = docx.oxml.OxmlElement('w:bottom')
                bottom.set(qn('w:val'), 'single')
                bottom.set(qn('w:sz'), '12')
                bottom.set(qn('w:space'), '1')
                bottom.set(qn('w:color'), '999999')
                pBdr.append(bottom)
                pPr.append(pBdr)
                continue

            # Bold/italic inline
            text = line
            # Simple: just add as paragraph
            p = doc.add_paragraph(text)

        doc.save(output)
        return f"DOCX saved: {output}"
    except Exception as e:
        return f"DOCX export error: {e}"


def _export_to_html(source: str, output: str) -> str:
    """Export markdown to HTML."""
    try:
        html = _md_to_html(source)
        styled = _add_web_styles(html)
        with open(output, "w") as f:
            f.write(styled)
        return f"HTML saved: {output}"
    except Exception as e:
        return f"HTML export error: {e}"


def _export_to_txt(source: str, output: str) -> str:
    """Export markdown to plain text (strip formatting)."""
    try:
        with open(source) as f:
            content = f.read()
        # Strip markdown formatting
        text = re.sub(r'#{1,6}\s+', '', content)
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        with open(output, "w") as f:
            f.write(text)
        return f"Text saved: {output}"
    except Exception as e:
        return f"Text export error: {e}"


def _md_to_html(source: str) -> str:
    """Convert markdown to HTML via pandoc (or simple regex fallback)."""
    try:
        result = subprocess.run(
            ["pandoc", source, "-f", "markdown", "-t", "html"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Simple regex-based conversion
    with open(source) as f:
        content = f.read()

    lines = content.split("\n")
    html_lines = []

    for line in lines:
        # Headers
        m = re.match(r'^(#{1,6})\s+(.*)', line)
        if m:
            level = len(m.group(1))
            html_lines.append(f"<h{level}>{m.group(2)}</h{level}>")
            continue

        # Blockquotes
        if line.startswith("> "):
            html_lines.append(f"<blockquote>{line[2:]}</blockquote>")
            continue

        # Bold/italic
        line = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', line)
        line = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', line)

        # Links
        line = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', line)

        # Horizontal rules
        if line.strip() in ("---", "***"):
            html_lines.append("<hr>")
            continue

        # Paragraphs
        if line.strip():
            html_lines.append(f"<p>{line}</p>")
        else:
            html_lines.append("")

    return "\n".join(html_lines)


def _add_pdf_styles(html: str) -> str:
    """Add clean print-ready styles for PDF export."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
    font-family: 'Georgia', serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #333;
    max-width: 48rem;
    margin: 0 auto;
    padding: 2rem;
}}
h1 {{ font-size: 24pt; color: #1a1a2e; border-bottom: 2px solid #16213e; padding-bottom: 0.3rem; }}
h2 {{ font-size: 18pt; color: #16213e; border-bottom: 1px solid #ddd; padding-bottom: 0.2rem; margin-top: 2rem; }}
h3 {{ font-size: 14pt; color: #0f3460; }}
blockquote {{
    border-left: 3px solid #16213e;
    margin-left: 0;
    padding-left: 1rem;
    color: #666;
    font-style: italic;
}}
a {{ color: #0f3460; }}
hr {{ border: none; border-top: 1px solid #ddd; margin: 2rem 0; }}
</style>
</head>
<body>
{html}
</body>
</html>"""


def _add_web_styles(html: str) -> str:
    """Add clean web styles for HTML export."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 16px;
    line-height: 1.7;
    color: #24292e;
    max-width: 800px;
    margin: 40px auto;
    padding: 0 20px;
}}
h1 {{ font-size: 2em; border-bottom: 2px solid #eaecef; padding-bottom: 0.3em; }}
h2 {{ font-size: 1.5em; border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; }}
h3 {{ font-size: 1.25em; }}
blockquote {{
    border-left: 4px solid #dfe2e5;
    margin: 0;
    padding: 0 1em;
    color: #6a737d;
}}
code {{
    background: #f6f8fa;
    padding: 0.2em 0.4em;
    border-radius: 3px;
    font-size: 85%;
}}
hr {{ border: 0; border-top: 1px solid #eaecef; margin: 2em 0; }}
a {{ color: #0366d6; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
{html}
</body>
</html>"""


# ── Document Editing ─────────────────────────────────────────────────────────

def edit_document(file_path: str, edit_type: str, value: str = "") -> str:
    """Edit an existing document.

    edit_type: "shorten", "expand", "add_toc", "to_bullets", "to_email",
               "append", "prepend", "replace_section"
    """
    if not os.path.exists(file_path):
        return f"File not found: {file_path}"

    with open(file_path) as f:
        content = f.read()

    if edit_type == "shorten":
        result = _shorten_document(content)
    elif edit_type == "add_toc":
        result = _add_toc_to_document(content)
    elif edit_type == "to_bullets":
        result = _convert_to_bullets(content)
    elif edit_type == "to_email":
        result = _convert_to_email(content, value)
    elif edit_type == "append":
        result = content + "\n\n" + value
    elif edit_type == "prepend":
        result = value + "\n\n" + content
    elif edit_type == "replace_section":
        # value should be "OLD_TEXT|||NEW_TEXT"
        if "|||" in value:
            old, new = value.split("|||", 1)
            result = content.replace(old.strip(), new.strip())
        else:
            return "For replace_section, value should be: old_text|||new_text"
    else:
        return f"Unknown edit type: {edit_type}"

    # Overwrite the file
    with open(file_path, "w") as f:
        f.write(result)

    return f"Document updated: {file_path}"


def _shorten_document(content: str) -> str:
    """Condense document to key points — keeps headers and first paragraph of each section."""
    lines = content.split("\n")
    result = []
    in_paragraph = False
    paragraph_lines = 0

    for line in lines:
        # Keep headers
        if re.match(r'^#{1,6}\s+', line):
            result.append(line)
            in_paragraph = False
            paragraph_lines = 0
            continue

        # Keep first ~3 lines after each header
        if not in_paragraph and line.strip():
            result.append(line)
            paragraph_lines += 1
            in_paragraph = True
            if paragraph_lines >= 3:
                result.append("*...[condensed]*")
            continue

        if line.strip() == "" or line.strip() == "---":
            result.append(line)
            in_paragraph = False
            paragraph_lines = 0
            continue

        if in_paragraph and paragraph_lines < 3:
            result.append(line)
            paragraph_lines += 1

    return "\n".join(result)


def _add_toc_to_document(content: str) -> str:
    """Add a table of contents to a document (after the first header)."""
    lines = content.split("\n")
    toc_lines = []
    first_header_idx = None

    for i, line in enumerate(lines):
        m = re.match(r'^(#{1,6})\s+(.*)', line)
        if m:
            if first_header_idx is None:
                first_header_idx = i
            level = len(m.group(1))
            if level <= 3:  # Only H1-H3 in TOC
                title = m.group(2)
                anchor = title.lower()
                anchor = re.sub(r'[^\w\s-]', '', anchor)
                anchor = anchor.replace(" ", "-")
                indent = "  " * (level - 1)
                toc_lines.append(f"{indent}- [{title}](#{anchor})")

    if first_header_idx is not None:
        # Find where to insert TOC (after first blockquote/metadata section)
        insert_idx = first_header_idx + 1
        while insert_idx < len(lines) and (lines[insert_idx].startswith(">") or lines[insert_idx].strip() == "---" or not lines[insert_idx].strip()):
            insert_idx += 1

        toc_content = "\n\n## Table of Contents\n\n" + "\n".join(toc_lines) + "\n"
        lines.insert(insert_idx, toc_content)

    return "\n".join(lines)


def _convert_to_bullets(content: str) -> str:
    """Convert paragraph-heavy sections to bullet points."""
    lines = content.split("\n")
    result = []

    for line in lines:
        # Keep headers, blockquotes, horizontal rules
        if re.match(r'^#{1,6}\s+', line) or line.startswith(">") or line.strip() == "---" or not line.strip():
            result.append(line)
            continue

        # Convert non-empty, non-header lines to bullets
        if line.strip() and not line.startswith("-") and not line.startswith("*"):
            # Only if it looks like a paragraph (not already a list or code)
            if not line.startswith(" ") and not line.startswith("```"):
                result.append(f"- {line}")
            else:
                result.append(line)
        else:
            result.append(line)

    return "\n".join(result)


def _convert_to_email(content: str, to_address: str = "") -> str:
    """Convert document content to email format."""
    # Extract title (first header)
    title = "Document"
    m = re.match(r'^#\s+(.*)', content)
    if m:
        title = m.group(1)

    # Strip the header and metadata
    body = re.sub(r'^#\s+.*?\n', '', content, count=1)
    body = re.sub(r'^>.*\n', '', body, flags=re.MULTILINE)
    body = re.sub(r'^---\s*\n', '', body)
    body = body.strip()

    lines = [
        f"Subject: {title}",
    ]
    if to_address:
        lines.append(f"To: {to_address}")
    lines.append("")
    lines.append(body)
    lines.append("")

    return "\n".join(lines)


# ── List & Search Documents ──────────────────────────────────────────────────

def list_documents(doc_type: str = "", limit: int = 20) -> str:
    """List saved documents, optionally filtered by type."""
    _ensure_dirs()

    if doc_type:
        folders = [_get_subfolder(doc_type)]
    else:
        folders = list(DOC_SUBFOLDERS.values())

    all_files = []
    for folder in folders:
        folder_path = os.path.join(DOCS_DIR, folder)
        if os.path.exists(folder_path):
            for f in sorted(os.listdir(folder_path), reverse=True):
                if f.endswith((".md", ".pdf", ".docx", ".html", ".txt")):
                    all_files.append((folder, f, os.path.join(folder_path, f)))

    if not all_files:
        return "No documents saved yet."

    all_files.sort(key=lambda x: x[2], reverse=True)
    all_files = all_files[:limit]

    lines = [f"Saved Documents ({len(all_files)}):"]
    lines.append("")
    for folder, filename, filepath in all_files:
        size = os.path.getsize(filepath)
        size_str = f"{size/1024:.1f}KB" if size > 1024 else f"{size}B"
        lines.append(f"📄 [{folder}] {filename} ({size_str})")
        lines.append(f"   {filepath}")

    return "\n".join(lines)


def get_document_info(file_path: str) -> str:
    """Get information about a saved document."""
    if not os.path.exists(file_path):
        return f"File not found: {file_path}"

    stat = os.stat(file_path)
    size = stat.st_size
    created = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M")
    modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")

    ext = os.path.splitext(file_path)[1]
    with open(file_path, encoding="utf-8", errors="replace") as f:
        content = f.read()

    word_count = len(content.split())
    line_count = len(content.split("\n"))

    # Extract title (first header)
    title = "Unknown"
    m = re.match(r'^#\s+(.*)', content)
    if m:
        title = m.group(1)

    return (
        f"Document: {title}\n"
        f"File: {file_path}\n"
        f"Type: {ext}\n"
        f"Size: {size/1024:.1f} KB\n"
        f"Words: {word_count}\n"
        f"Lines: {line_count}\n"
        f"Created: {created}\n"
        f"Modified: {modified}"
    )


def delete_document(file_path: str) -> str:
    """Delete a saved document."""
    if not os.path.exists(file_path):
        return f"File not found: {file_path}"

    os.remove(file_path)
    return f"Deleted: {file_path}"


def read_document(file_path: str, max_chars: int = 5000) -> str:
    """Read a saved document's contents."""
    if not os.path.exists(file_path):
        return f"File not found: {file_path}"

    with open(file_path, encoding="utf-8", errors="replace") as f:
        content = f.read()

    if len(content) > max_chars:
        return content[:max_chars] + f"\n\n...[truncated, {len(content) - max_chars} more chars]"
    return content
