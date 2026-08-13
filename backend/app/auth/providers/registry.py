"""Provider registry — the single seam where providers are swapped.

Supabase is selected as soon as ``SUPABASE_URL`` is set; otherwise the app
runs on the placeholder provider (auth endpoints answer 501) so development
and tests never require credentials. Adding Firebase/Auth0 later means adding
a provider class and one more branch here — no route or service code changes.
"""

from app.auth.interfaces import AuthService
from app.auth.providers.not_implemented import NotImplementedAuthProvider
from app.auth.providers.supabase import SupabaseAuthProvider
from app.core.config import get_settings


def get_auth_provider() -> AuthService:
    """Return the configured authentication provider."""
    settings = get_settings()
    if settings.supabase_url:
        return SupabaseAuthProvider(settings)
    return NotImplementedAuthProvider()
