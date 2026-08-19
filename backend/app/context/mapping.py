"""Isolated parsing + mapping helpers for the Context Builder.

Everything here is a pure function so the exact behavior is unit-testable
without repositories, a database, or a browser. It deliberately stays small:

- :func:`extract_element_info` — a *best-effort* structured view of the
  affected HTML snippet captured by axe (tag, attributes, ARIA, form fields,
  visible text). It is not a general HTML parser; malformed or hostile
  snippets degrade to empty fields, never to crashes.
- :func:`wcag_criteria` / :func:`format_criterion` / :func:`wcag_principle` —
  derive the WCAG criterion numbers and principle from axe's ``wcagNNNN``
  tags. Only the standard WCAG 2.x principle→criterion mapping is used
  (1=Perceivable, 2=Operable, 3=Understandable, 4=Robust); nothing else is
  invented.

HTML snippets come from crawled pages and are **untrusted input**: treat
every returned string as opaque text.
"""

import re
from typing import Dict, List, Optional

from app.context.models import ElementContext

# --- HTML element extraction --------------------------------------------------

_TAG_RE = re.compile(r"<\s*([a-zA-Z][a-zA-Z0-9-]*)")
_ATTR_RE = re.compile(
    r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))"""
)
_TAG_STRIP_RE = re.compile(r"<[^>]*>")

# Form-related attributes worth surfacing in ElementContext.form.
_FORM_ATTRIBUTES = {
    "name",
    "type",
    "value",
    "placeholder",
    "title",
    "disabled",
    "required",
    "readonly",
    "tabindex",
    "id",
    "for",
    "autocomplete",
    "checked",
    "selected",
    "multiple",
    "pattern",
    "min",
    "max",
    "step",
    "accept",
    "autofocus",
}


def extract_element_info(html: str) -> ElementContext:
    """Best-effort structured view of an HTML snippet.

    ``html`` is the raw (untrusted) snippet from the scanner. All fields are
    derived with simple regexes and never interpreted as executable markup.
    """
    snippet = html or ""
    tag = _extract_tag(snippet)
    attributes = _extract_attributes(snippet)
    return ElementContext(
        html=snippet,
        tag=tag,
        attributes=attributes,
        text_content=_extract_text(snippet),
        role=attributes.get("role"),
        aria={k: v for k, v in attributes.items() if k.startswith("aria-")},
        form={k: v for k, v in attributes.items() if k in _FORM_ATTRIBUTES},
    )


def _extract_tag(html: str) -> Optional[str]:
    match = _TAG_RE.search(html)
    return match.group(1).lower() if match else None


def _extract_attributes(html: str) -> Dict[str, str]:
    attributes: Dict[str, str] = {}
    for match in _ATTR_RE.finditer(html):
        key = match.group(1)
        value = match.group(2) or match.group(3) or match.group(4) or ""
        attributes[key] = value
    return attributes


def _extract_text(html: str) -> str:
    text = _TAG_STRIP_RE.sub(" ", html)
    return " ".join(text.split())


# --- WCAG criterion/principle mapping -----------------------------------------

_WCAG_TAG_RE = re.compile(r"^wcag(\d+)$")

_WCAG_PRINCIPLES: Dict[str, str] = {
    "1": "Perceivable",
    "2": "Operable",
    "3": "Understandable",
    "4": "Robust",
}


def wcag_criteria(tags: List[str]) -> List[str]:
    """WCAG criterion numbers (e.g. ``1.4.3``) from axe ``wcagNNNN`` tags.

    Deterministic: deduplicated, sorted by (principle, number).
    """
    criteria = set()
    for tag in tags:
        match = _WCAG_TAG_RE.match(tag)
        if match:
            formatted = format_criterion(match.group(1))
            if formatted:
                criteria.add(formatted)
    return sorted(criteria, key=_criterion_sort_key)


def format_criterion(digits: str) -> Optional[str]:
    """Format criterion digits as ``principle.section.subsection``.

    ``"143"`` → ``"1.4.3"``; ``"1411"`` → ``"1.4.11"`` (WCAG 2.2+).
    """
    if not digits.isdigit() or len(digits) < 3:
        return None
    if len(digits) == 3:
        return f"{digits[0]}.{digits[1]}.{digits[2]}"
    return f"{digits[0]}.{digits[1]}.{digits[2:]}"


def _criterion_sort_key(criterion: str) -> tuple:
    parts = criterion.split(".")
    return tuple(int(part) for part in parts)


def wcag_principle(criteria: List[str]) -> Optional[str]:
    """Standard WCAG principle for the first criterion (1→4 mapping only)."""
    for criterion in sorted(criteria, key=_criterion_sort_key):
        principle = criterion.split(".")[0]
        if principle in _WCAG_PRINCIPLES:
            return _WCAG_PRINCIPLES[principle]
    return None
