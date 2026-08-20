"""Measurement domain exceptions (Module 8).

Mirrors the existing exception pattern: every error carries an HTTP
``status_code`` and a stable, machine-readable ``code``, rendered as
the uniform ``{code, message}`` envelope.
"""


class MeasurementError(Exception):
    """Base class for all measurement errors."""

    status_code = 500
    code = "measurement_error"


class MeasurementNotFoundError(MeasurementError):
    """The requested measurement does not exist. → 404."""

    status_code = 404
    code = "measurement_not_found"


class MeasurementRemediationError(MeasurementError):
    """The remediation is not in a valid state for measurement. → 409."""

    status_code = 409
    code = "measurement_remediation_invalid"


class MeasurementScanError(MeasurementError):
    """The follow-up scan is invalid or not owned by the user. → 404."""

    status_code = 404
    code = "measurement_scan_not_found"


class MeasurementScanOrderError(MeasurementError):
    """The follow-up scan does not occur after the original scan. → 409."""

    status_code = 409
    code = "measurement_scan_order_invalid"


class MeasurementScanIncompleteError(MeasurementError):
    """The follow-up scan has not completed. → 409."""

    status_code = 409
    code = "measurement_scan_incomplete"


class MeasurementDuplicateError(MeasurementError):
    """A measurement already exists for this remediation + follow-up pair. → 409."""

    status_code = 409
    code = "measurement_duplicate"
