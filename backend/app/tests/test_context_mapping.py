"""Tests for the isolated Context Builder parsing/mapping helpers."""

from app.context.mapping import (
    extract_element_info,
    format_criterion,
    wcag_criteria,
    wcag_principle,
)


# --- element extraction ------------------------------------------------------


def test_extract_element_info_parses_snippet() -> None:
    element = extract_element_info('<img src="icon.png" alt="Icon" aria-hidden="true" />')

    assert element.tag == "img"
    assert element.attributes == {"src": "icon.png", "alt": "Icon", "aria-hidden": "true"}
    assert element.aria == {"aria-hidden": "true"}
    assert element.role is None
    assert element.text_content == ""


def test_extract_element_info_extracts_form_fields() -> None:
    element = extract_element_info(
        '<input type="text" name="search" placeholder="Type to search" class="x" />'
    )

    assert element.form == {"type": "text", "name": "search", "placeholder": "Type to search"}
    assert element.tag == "input"


def test_extract_element_info_extracts_role_and_text() -> None:
    element = extract_element_info('<button role="button">Save <span>changes</span></button>')

    assert element.role == "button"
    assert element.text_content == "Save changes"


def test_extract_element_info_handles_empty_and_malformed() -> None:
    empty = extract_element_info("")
    assert empty.tag is None
    assert empty.attributes == {}
    assert empty.html == ""

    malformed = extract_element_info("not html at all")
    assert malformed.tag is None
    assert malformed.attributes == {}
    assert malformed.text_content == "not html at all"


def test_extract_element_info_keeps_untrusted_html_opaque() -> None:
    element = extract_element_info('<p onclick="evil()">&lt;script&gt;alert(1)&lt;/script&gt;</p>')
    assert element.tag == "p"
    # The snippet is preserved verbatim — consumers must escape it, never
    # render it as markup.
    assert element.html == '<p onclick="evil()">&lt;script&gt;alert(1)&lt;/script&gt;</p>'
    # Entities are preserved as text (never decoded into executable markup).
    assert element.text_content == "&lt;script&gt;alert(1)&lt;/script&gt;"


# --- WCAG criteria / principle -----------------------------------------------


def test_wcag_criteria_extracts_and_sorts() -> None:
    assert wcag_criteria(["wcag143", "cat.color", "wcag1411", "wcag143", "wcag244"]) == [
        "1.4.3",
        "1.4.11",
        "2.4.4",
    ]


def test_wcag_criteria_ignores_non_criterion_tags() -> None:
    assert wcag_criteria(["cat.color", "ACT", "best-practice", "section508"]) == []


def test_format_criterion() -> None:
    assert format_criterion("143") == "1.4.3"
    assert format_criterion("111") == "1.1.1"
    assert format_criterion("1411") == "1.4.11"
    assert format_criterion("257") == "2.5.7"
    assert format_criterion("12") is None
    assert format_criterion("abc") is None


def test_wcag_principle_maps_standard_principles() -> None:
    assert wcag_principle(["1.4.3"]) == "Perceivable"
    assert wcag_principle(["2.4.4"]) == "Operable"
    assert wcag_principle(["3.3.7"]) == "Understandable"
    assert wcag_principle(["4.1.2"]) == "Robust"
    assert wcag_principle([]) is None
    assert wcag_principle(["9.1.1.1"]) is None  # unknown principle → None
