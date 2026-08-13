"""Provider base contract.

A *provider* is a concrete :class:`AuthService` that knows how to talk to one
external identity system (Supabase, Firebase, Auth0, …). The rest of the
application only ever sees :class:`AuthService`; providers are registered in
:mod:`app.auth.providers.registry`.
"""

from typing import Protocol

from app.auth.interfaces import AuthService


class AuthProvider(AuthService, Protocol):
    """Marker for pluggable authentication providers."""

    name: str
