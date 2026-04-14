"""Writer voice tools: create, export, edit, list, read, delete documents."""

from __future__ import annotations

from tools.writer import (
    create_company_research_doc as _writer_company,
    create_market_analysis_doc as _writer_market,
    create_meeting_prep_doc as _writer_meeting,
    create_technical_doc as _writer_technical,
    create_custom_doc as _writer_custom,
    save_document as _writer_save,
    export_document as _writer_export,
    edit_document as _writer_edit,
    list_documents as _writer_list,
    read_document as _writer_read,
    delete_document as _writer_delete,
)


def _infer_company_from_title(title: str) -> str:
    """Pull a plausible company name out of a doc title.

    Voice-generated titles tend to look like "Raga AI Deep Research Brief" —
    we strip off the trailing "Deep Research / Research / Brief / Report /
    Profile" boilerplate and whatever's left is the subject.
    """
    import re as _re
    cleaned = _re.sub(
        r"\s*(deep\s+research(\s+brief)?|research(\s+brief)?|brief|report|profile|analysis)\s*$",
        "",
        title,
        flags=_re.IGNORECASE,
    )
    return cleaned.strip() or title.strip()


def exec_writer_create(action: str, title: str = "", content: str = "",
                       doc_type: str = "document", **_kw) -> str:
    """Create a professional document (company research, market analysis, meeting prep, technical, custom).

    For ``company_research`` / ``market_analysis`` the voice LLM usually cannot
    pipe the upstream research output into ``content`` in a single turn, so we
    fetch the research ourselves when ``content`` is missing. That way a user
    saying "research Raga AI and save a doc" produces a filled-in brief
    instead of an empty template.
    """
    if action == "company_research":
        company = (content or _infer_company_from_title(title)).strip()
        if not company:
            return "writer_create: need a company name in title or content."
        from tools.research import research_company as _raw_research_company
        data = _raw_research_company(company, include_financials=True,
                                     include_news=True, include_competitors=True)
        data["company"] = company
        if not data.get("executive_summary"):
            data["executive_summary"] = f"Research on {company}."
        formatted = _writer_company(data, title=title or f"{company} Company Research")
    elif action == "market_analysis":
        subject = (content or _infer_company_from_title(title)).strip()
        if not subject:
            return "writer_create: need a market/topic in title or content."
        from tools.research import market_research as _raw_market_research
        data = _raw_market_research(subject, include_competitors=True, include_trends=True)
        data["subject"] = subject
        if not data.get("executive_summary"):
            data["executive_summary"] = f"Market research on {subject}."
        formatted = _writer_market(data, title=title or f"{subject} Market Analysis")
    elif action == "meeting_prep":
        data = {"sections": {}}
        formatted = _writer_meeting(data, title=title)
    elif action == "technical":
        formatted = _writer_technical(content, title=title, doc_type=doc_type)
    elif action == "custom":
        formatted = _writer_custom(title, content, doc_type=doc_type)
    else:
        return f"Unknown writer action: {action}"
    subfolder = {"company_research": "report", "market_analysis": "report",
                 "meeting_prep": "meeting", "technical": "technical"}.get(action, "default")
    filepath = _writer_save(formatted, title or "Document", doc_type=subfolder)

    # Auto-export to DOCX and open it
    open_path = filepath
    if action in ("company_research", "market_analysis"):
        try:
            export_result = _writer_export(filepath, "docx")
            # _writer_export returns "DOCX saved: /path/to/file.docx"
            if export_result.startswith("DOCX saved:"):
                open_path = export_result.replace("DOCX saved:", "").strip()
        except Exception:
            pass

    # Auto-open the file on macOS
    try:
        import subprocess
        subprocess.Popen(["open", open_path])
    except Exception:
        pass

    return f"Created and saved to:\n{open_path}"


def exec_writer_export(file_path: str, format: str, **_kw) -> str:
    """Export a Markdown document to PDF, DOCX, HTML, or TXT."""
    return _writer_export(file_path, format)


def exec_writer_edit(file_path: str, edit_type: str, value: str = "", **_kw) -> str:
    """Edit a document (shorten, add_toc, to_bullets, to_email, append, prepend)."""
    return _writer_edit(file_path, edit_type, value)


def exec_writer_list(doc_type: str = "", limit: int = 20, **_kw) -> str:
    """List saved documents, optionally filtered by type."""
    return _writer_list(doc_type, limit)


def exec_writer_read(file_path: str, **_kw) -> str:
    """Read a saved document's contents."""
    return _writer_read(file_path)


def exec_writer_delete(file_path: str, **_kw) -> str:
    """Delete a saved document."""
    return _writer_delete(file_path)
