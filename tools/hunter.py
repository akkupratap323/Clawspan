"""Hunter.io email intelligence tool.

Covers all six Hunter.io v2 endpoints:
  - discover          → find people at a company via URL
  - domain_search     → all emails for a domain
  - email_finder      → find one person's email by name + domain
  - email_verifier    → verify deliverability of an email address
  - company_enrichment → full company profile from domain
  - person_enrichment → full person profile from email
  - combined_enrichment → person + company in one call
"""

from __future__ import annotations

import requests

from config import HUNTER_API_KEY

_BASE = "https://api.hunter.io/v2"
_TIMEOUT = 15


def _get(endpoint: str, params: dict) -> dict:
    """Make a GET request to Hunter.io, return parsed JSON or error dict."""
    if not HUNTER_API_KEY:
        return {"error": "HUNTER_API_KEY not set. Add it to your .env file."}
    params["api_key"] = HUNTER_API_KEY
    try:
        r = requests.get(f"{_BASE}/{endpoint}", params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        return {"error": f"Hunter API error {e.response.status_code}: {e.response.text[:300]}"}
    except Exception as e:
        return {"error": str(e)}


def _post(endpoint: str, payload: dict) -> dict:
    """Make a POST request to Hunter.io, return parsed JSON or error dict."""
    if not HUNTER_API_KEY:
        return {"error": "HUNTER_API_KEY not set. Add it to your .env file."}
    payload["api_key"] = HUNTER_API_KEY
    try:
        r = requests.post(f"{_BASE}/{endpoint}", json=payload, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        return {"error": f"Hunter API error {e.response.status_code}: {e.response.text[:300]}"}
    except Exception as e:
        return {"error": str(e)}


# ── Public functions ──────────────────────────────────────────────────────────

def discover(domain: str) -> str:
    """POST /discover — find people listed for a company domain."""
    data = _post("discover", {"domain": domain})
    if "error" in data:
        return data["error"]
    people = data.get("data", {}).get("emails", [])
    if not people:
        return f"No people found for {domain}."
    lines = [f"People at {domain} ({len(people)} found):"]
    for p in people[:20]:
        name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        email = p.get("value", "")
        position = p.get("position", "")
        lines.append(f"  • {name} — {email}" + (f" ({position})" if position else ""))
    return "\n".join(lines)


def domain_search(domain: str, limit: int = 10) -> str:
    """GET /domain-search — list all known emails for a domain."""
    data = _get("domain-search", {"domain": domain, "limit": limit})
    if "error" in data:
        return data["error"]
    d = data.get("data", {})
    emails = d.get("emails", [])
    org = d.get("organization", domain)
    if not emails:
        return f"No emails found for {domain}."
    lines = [f"Emails at {org} ({d.get('total', len(emails))} total, showing {len(emails)}):"]
    for e in emails:
        name = f"{e.get('first_name', '')} {e.get('last_name', '')}".strip()
        addr = e.get("value", "")
        dept = e.get("department", "")
        conf = e.get("confidence", "")
        line = f"  • {addr}"
        if name:
            line += f" — {name}"
        if dept:
            line += f" ({dept})"
        if conf:
            line += f" [{conf}% confidence]"
        lines.append(line)
    return "\n".join(lines)


def email_finder(domain: str, first_name: str, last_name: str) -> str:
    """GET /email-finder — find one person's email by name + domain."""
    data = _get("email-finder", {
        "domain": domain,
        "first_name": first_name,
        "last_name": last_name,
    })
    if "error" in data:
        return data["error"]
    d = data.get("data", {})
    email = d.get("email")
    score = d.get("score", "")
    if not email:
        return f"Could not find email for {first_name} {last_name} at {domain}."
    result = f"Found: {email}"
    if score:
        result += f" (confidence: {score}%)"
    sources = d.get("sources", [])
    if sources:
        result += f"\nSources: {', '.join(s.get('uri', '') for s in sources[:3])}"
    return result


def email_verifier(email: str) -> str:
    """GET /email-verifier — check deliverability and validity of an email."""
    data = _get("email-verifier", {"email": email})
    if "error" in data:
        return data["error"]
    d = data.get("data", {})
    status = d.get("status", "unknown")
    score = d.get("score", "")
    result = d.get("result", "")
    lines = [f"Verification for {email}:"]
    lines.append(f"  Status: {status}")
    if result:
        lines.append(f"  Result: {result}")
    if score:
        lines.append(f"  Score: {score}%")
    mx = d.get("mx_records")
    if mx is not None:
        lines.append(f"  MX records: {'yes' if mx else 'no'}")
    disposable = d.get("disposable")
    if disposable is not None:
        lines.append(f"  Disposable: {'yes' if disposable else 'no'}")
    return "\n".join(lines)


def company_enrichment(domain: str) -> str:
    """GET /companies/find — full company profile from domain."""
    data = _get("companies/find", {"domain": domain})
    if "error" in data:
        return data["error"]
    d = data.get("data", {})
    if not d:
        return f"No company data found for {domain}."
    lines = [f"Company: {d.get('name', domain)}"]
    for field in ["description", "industry", "size", "founded", "country",
                  "city", "linkedin", "twitter", "phone"]:
        val = d.get(field)
        if val:
            lines.append(f"  {field.capitalize()}: {val}")
    technologies = d.get("technologies", [])
    if technologies:
        lines.append(f"  Technologies: {', '.join(technologies[:10])}")
    return "\n".join(lines)


def person_enrichment(email: str) -> str:
    """GET /people/find — full person profile from email address."""
    data = _get("people/find", {"email": email})
    if "error" in data:
        return data["error"]
    d = data.get("data", {})
    if not d:
        return f"No person data found for {email}."
    name = f"{d.get('first_name', '')} {d.get('last_name', '')}".strip()
    lines = [f"Person: {name or email}"]
    for field in ["position", "seniority", "department", "twitter",
                  "linkedin", "phone_number", "location"]:
        val = d.get(field)
        if val:
            lines.append(f"  {field.replace('_', ' ').capitalize()}: {val}")
    org = d.get("organization", {})
    if org.get("name"):
        lines.append(f"  Company: {org['name']}")
    return "\n".join(lines)


def combined_enrichment(email: str) -> str:
    """GET /combined/find — person + company enrichment in one call."""
    data = _get("combined/find", {"email": email})
    if "error" in data:
        return data["error"]
    d = data.get("data", {})
    parts = []

    person = d.get("person", {})
    if person:
        name = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()
        parts.append(f"Person: {name or email}")
        for field in ["position", "seniority", "department", "linkedin"]:
            val = person.get(field)
            if val:
                parts.append(f"  {field.capitalize()}: {val}")

    company = d.get("company", {})
    if company:
        parts.append(f"Company: {company.get('name', 'Unknown')}")
        for field in ["description", "industry", "size", "country"]:
            val = company.get(field)
            if val:
                parts.append(f"  {field.capitalize()}: {val}")

    return "\n".join(parts) if parts else f"No data found for {email}."
