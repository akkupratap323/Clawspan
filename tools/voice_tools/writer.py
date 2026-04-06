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


def exec_writer_create(action: str, title: str = "", content: str = "",
                       doc_type: str = "document", **_kw) -> str:
    """Create a professional document (company research, market analysis, meeting prep, technical, custom)."""
    if action == "company_research":
        data = {"company": content, "sections": {}}
        formatted = _writer_company(data, title=title)
    elif action == "market_analysis":
        data = {"subject": content, "sections": {}}
        formatted = _writer_market(data, title=title)
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
    return f"Created and saved to:\n{filepath}"


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
