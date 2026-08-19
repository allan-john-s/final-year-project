"""Tests for the scanner registry.

Module 3B registers the first real engine (Axe); the tests prove the factory
returns it through the ``BaseScanner`` contract and that adding another
engine remains a pure registration concern.
"""

import asyncio

import pytest

from app.scanners.axe import AxeScanner
from app.scanners.base import BaseScanner
from app.scanners.factory import (
    SCANNER_REGISTRY,
    ScannerUnavailableError,
    available_scanners,
    get_scanner,
)
from app.scanners.models import NormalizedScanResult, ScannerType
from app.tests.test_scanner_models import make_metadata, make_result


def test_axe_engine_is_registered() -> None:
    """Module 3B ships the first engine: AXE."""
    assert SCANNER_REGISTRY[ScannerType.AXE] is AxeScanner
    assert available_scanners() == [ScannerType.AXE]


def test_get_scanner_returns_axe_instance() -> None:
    scanner = get_scanner(ScannerType.AXE)
    assert isinstance(scanner, AxeScanner)
    assert scanner.name == "axe-core"
    assert scanner.version == "4.10.2"
    assert scanner.wcag_version == "2.2"
    assert scanner.scanner_type is ScannerType.AXE


def test_get_scanner_raises_for_unregistered_type() -> None:
    for scanner_type in ScannerType:
        if scanner_type is ScannerType.AXE:
            continue
        with pytest.raises(ScannerUnavailableError):
            get_scanner(scanner_type)


class FakeScanner(BaseScanner):
    """A minimal engine implementing the contract — proves the extension point."""

    name = "fake-scanner"
    version = "0.0.1"
    wcag_version = "2.2"
    scanner_type = ScannerType.RESEARCH

    async def scan(self, url: str, *, depth: int = 1) -> NormalizedScanResult:
        return make_result(
            metadata=make_metadata(
                scanner_name=self.name,
                scanner_version=self.version,
                scanner_type=self.scanner_type,
                scan_url=url,
                scan_depth=depth,
            )
        )


def test_registering_another_scanner_makes_it_available() -> None:
    SCANNER_REGISTRY[FakeScanner.scanner_type] = FakeScanner
    try:
        assert available_scanners() == [ScannerType.AXE, ScannerType.RESEARCH]

        scanner = get_scanner(ScannerType.RESEARCH)
        assert isinstance(scanner, FakeScanner)

        result = asyncio.run(scanner.scan("https://example.com", depth=2))
        assert isinstance(result, NormalizedScanResult)
        assert result.metadata.scanner_name == "fake-scanner"
        assert result.metadata.scan_url == "https://example.com"
        assert result.metadata.scan_depth == 2
    finally:
        SCANNER_REGISTRY.pop(FakeScanner.scanner_type, None)


def test_api_contract_does_not_depend_on_axe_or_lighthouse() -> None:
    """Callers receive BaseScanner instances — never engine-specific types."""
    scanner: BaseScanner = get_scanner(ScannerType.AXE)
    assert isinstance(scanner, BaseScanner)
