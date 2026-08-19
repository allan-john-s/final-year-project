"""Remediation dependencies for route handlers (Module 7).

- :func:`get_remediation_service` — the remediation service built on the
  context builder and the mock provider.
"""

from typing import Annotated

from fastapi import Depends

from app.context.services import ContextBuilderService
from app.dependencies.context import get_context_service
from app.remediations.providers.mock import MockRemediationProvider
from app.remediations.services import RemediationService


def get_remediation_provider() -> MockRemediationProvider:
    """Resolve the remediation provider.

    Returns the mock provider for development/testing. Replace with a
    real provider when LLM_API_KEY is configured.
    """
    return MockRemediationProvider()


def get_remediation_service(
    context_builder: Annotated[ContextBuilderService, Depends(get_context_service)],
    provider: Annotated[MockRemediationProvider, Depends(get_remediation_provider)],
) -> RemediationService:
    """Resolve the remediation service."""
    return RemediationService(context_builder=context_builder, provider=provider)
