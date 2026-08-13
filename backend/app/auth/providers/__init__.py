"""Pluggable authentication providers.

Batch 2 ships the real Supabase provider; Firebase, Auth0, and custom JWT
providers implement :class:`AuthProvider` and are registered in
:mod:`app.auth.providers.registry`.
"""

from app.auth.providers.base import AuthProvider
from app.auth.providers.not_implemented import NotImplementedAuthProvider
from app.auth.providers.registry import get_auth_provider
from app.auth.providers.supabase import SupabaseAuthProvider

__all__ = [
    "AuthProvider",
    "NotImplementedAuthProvider",
    "SupabaseAuthProvider",
    "get_auth_provider",
]
