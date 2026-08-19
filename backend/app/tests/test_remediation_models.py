"""Tests for remediation domain models (Module 7).

Covers RemediationProposal field bounds, ProposedChange validation,
RemediationStatus enum and valid transitions, version constant,
and the RemediationRequest/StatusUpdate schemas.
"""

import pytest
from pydantic import ValidationError

from app.remediations.models import (
    REMEDIATION_VERSION,
    ProposedChange,
    RemediationProposal,
    RemediationRequest,
    RemediationStatus,
    RemediationStatusUpdate,
    is_valid_transition,
)


# --- helpers ---------------------------------------------------------------


def make_proposal(**overrides) -> dict:
    """A valid RemediationProposal payload dict."""
    data = {
        "id": "rem-1",
        "scan_id": "scan-1",
        "issue_id": "issue-1",
        "strategy_id": "s-1",
        "rank": 1,
        "title": "Fix color contrast",
        "summary": "Add sufficient contrast to the text.",
        "rationale": "The recommended strategy addresses the issue.",
        "implementation_steps": [
            "Locate the element",
            "Update CSS",
            "Test with screen reader",
        ],
        "proposed_change": {
            "before": "<p>Low contrast</p>",
            "after": '<p style="color: #333">High contrast</p>',
            "explanation": "Changed text color to meet contrast ratio.",
        },
        "affected_element": "#main > p",
        "expected_improvement": "Resolves WCAG 1.4.3 contrast requirement.",
        "risks": ["Visual change may affect design"],
        "validation_steps": ["Run axe scan", "Check with NVDA"],
        "provider": "mock",
        "confidence": 0.85,
        "status": "PROPOSED",
    }
    data.update(overrides)
    return data


# --- model tests -----------------------------------------------------------


def test_proposal_roundtrips():
    proposal = RemediationProposal.model_validate(make_proposal())
    assert proposal.id == "rem-1"
    assert proposal.status is RemediationStatus.PROPOSED
    assert proposal.rank == 1
    assert proposal.confidence == 0.85
    assert proposal.remediation_version == REMEDIATION_VERSION


def test_proposal_title_required_and_bounded():
    with pytest.raises(ValidationError):
        RemediationProposal.model_validate(make_proposal(title=""))
    with pytest.raises(ValidationError):
        RemediationProposal.model_validate(make_proposal(title="x" * 201))


def test_proposal_confidence_range():
    with pytest.raises(ValidationError):
        RemediationProposal.model_validate(make_proposal(confidence=1.5))
    with pytest.raises(ValidationError):
        RemediationProposal.model_validate(make_proposal(confidence=-0.1))
    assert RemediationProposal.model_validate(make_proposal(confidence=1.0)).confidence == 1.0


def test_proposal_rank_bounds():
    with pytest.raises(ValidationError):
        RemediationProposal.model_validate(make_proposal(rank=0))
    with pytest.raises(ValidationError):
        RemediationProposal.model_validate(make_proposal(rank=11))


def test_proposal_implementation_steps_required():
    with pytest.raises(ValidationError):
        RemediationProposal.model_validate(make_proposal(implementation_steps=[]))


def test_proposal_validation_steps_required():
    with pytest.raises(ValidationError):
        RemediationProposal.model_validate(make_proposal(validation_steps=[]))


def test_proposal_text_stripping():
    proposal = RemediationProposal.model_validate(
        make_proposal(title="  Fix contrast  ", summary="  A fix.  ")
    )
    assert proposal.title == "Fix contrast"
    assert proposal.summary == "A fix."


def test_proposal_list_stripping():
    proposal = RemediationProposal.model_validate(
        make_proposal(implementation_steps=["  step 1  ", "", "step 3"])
    )
    assert proposal.implementation_steps == ["step 1", "step 3"]


# --- ProposedChange --------------------------------------------------------


def test_proposed_change_roundtrips():
    change = ProposedChange(
        before="<button>Submit</button>",
        after='<button aria-label="Submit form">Submit</button>',
        explanation="Added aria-label for screen readers.",
    )
    assert change.before.startswith("<button>")


def test_proposed_change_requires_before_and_after():
    with pytest.raises(ValidationError):
        ProposedChange(before="", after="x", explanation="y")
    with pytest.raises(ValidationError):
        ProposedChange(before="x", after="", explanation="y")


def test_proposed_change_optional_fields():
    change = ProposedChange(
        before="x", after="y", explanation="z",
        file_path="src/button.tsx", line_number=42,
    )
    assert change.file_path == "src/button.tsx"
    assert change.line_number == 42


# --- status transitions ----------------------------------------------------


def test_valid_transitions():
    assert is_valid_transition(RemediationStatus.PROPOSED, RemediationStatus.REVIEWED)
    assert is_valid_transition(RemediationStatus.REVIEWED, RemediationStatus.ACCEPTED)
    assert is_valid_transition(RemediationStatus.REVIEWED, RemediationStatus.REJECTED)
    assert is_valid_transition(RemediationStatus.ACCEPTED, RemediationStatus.APPLIED)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RemediationStatus.PROPOSED, RemediationStatus.ACCEPTED),
        (RemediationStatus.PROPOSED, RemediationStatus.REJECTED),
        (RemediationStatus.PROPOSED, RemediationStatus.APPLIED),
        (RemediationStatus.REVIEWED, RemediationStatus.PROPOSED),
        (RemediationStatus.REVIEWED, RemediationStatus.APPLIED),
        (RemediationStatus.ACCEPTED, RemediationStatus.PROPOSED),
        (RemediationStatus.ACCEPTED, RemediationStatus.REJECTED),
        (RemediationStatus.REJECTED, RemediationStatus.PROPOSED),
        (RemediationStatus.REJECTED, RemediationStatus.ACCEPTED),
        (RemediationStatus.APPLIED, RemediationStatus.PROPOSED),
        (RemediationStatus.APPLIED, RemediationStatus.REJECTED),
    ],
)
def test_invalid_transitions(current, target):
    assert not is_valid_transition(current, target)


# --- schemas ---------------------------------------------------------------


def test_remediation_request_requires_fields():
    with pytest.raises(ValidationError):
        RemediationRequest()
    with pytest.raises(ValidationError):
        RemediationRequest(issue_id="i")
    with pytest.raises(ValidationError):
        RemediationRequest(strategy_id="s")


def test_remediation_status_update_requires_status():
    with pytest.raises(ValidationError):
        RemediationStatusUpdate()


# --- version constant ------------------------------------------------------


def test_remediation_version():
    assert REMEDIATION_VERSION == "1.0"
