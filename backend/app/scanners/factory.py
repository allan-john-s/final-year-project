"""Scanner registry.

Concrete engines register their classes here (Axe, Lighthouse, Pa11y, WAVE,
research scanners — Modules 3B+). ``get_scanner`` is the single seam callers
use, so nothing outside this module needs to know which engines exist.

Module 3B ships the first engine: :class:`AxeScanner` is registered for
``ScannerType.AXE``. Adding another engine (e.g. Lighthouse) is purely a
registration concern — no API/service changes required.
"""

from typing import Dict, List, Type

from app.scanners.base import BaseScanner
from app.scanners.models import ScannerType

SCANNER_REGISTRY: Dict[ScannerType, Type[BaseScanner]] = {}


class ScannerUnavailableError(RuntimeError):
    """Requested a scanner type that has no registered engine yet."""


def get_scanner(scanner_type: ScannerType) -> BaseScanner:
    """Return a configured instance of the scanner for ``scanner_type``.

    Raises :class:`ScannerUnavailableError` when no engine is registered for
    that type — the expected behavior until Module 3B ships the first engine.
    """
    scanner_cls = SCANNER_REGISTRY.get(scanner_type)
    if scanner_cls is None:
        raise ScannerUnavailableError(
            f"No scanner engine is registered for {scanner_type.value}. "
            "Scanner implementations arrive in a later module."
        )
    return scanner_cls()


def available_scanners() -> List[ScannerType]:
    """The scanner types that currently have a registered engine."""
    return sorted(SCANNER_REGISTRY)


# --- registered engines -----------------------------------------------------

# Imported at the bottom so the registry module (and everything importing it)
# stays importable even where Playwright is not installed: axe.py only imports
# Playwright lazily inside ``scan()``.
from app.scanners.axe import AxeScanner  # noqa: E402  (intentional bottom import)

SCANNER_REGISTRY[ScannerType.AXE] = AxeScanner
