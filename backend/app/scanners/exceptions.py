"""Scanner engine exceptions.

The service layer maps every one of these onto a **FAILED** scan row with a
sanitized message — raw exception details (stack traces, absolute paths,
credentials) never reach API clients. The classes exist so the engine can
distinguish failure kinds for logging and future retry logic:

- :class:`ScannerConfigurationError` — the environment can't run a scan
  (Playwright missing, axe source missing, browser launch failure).
- :class:`ScannerTargetError` — the target URL is invalid, unreachable,
  timed out, or answered with an HTTP error status.
- :class:`ScannerRuntimeError` — anything unexpected while executing.
"""


class ScannerError(Exception):
    """Base class for all scanner engine errors."""


class ScannerConfigurationError(ScannerError):
    """The scanner could not be set up (missing dependency/browser/source)."""


class ScannerTargetError(ScannerError):
    """The target URL is invalid or could not be scanned."""


class ScannerRuntimeError(ScannerError):
    """The scanner crashed while executing against a valid target."""
