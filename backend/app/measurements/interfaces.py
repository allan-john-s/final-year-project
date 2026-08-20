"""Measurement domain interfaces (Module 8).

Defines the data-access contracts the measurement service depends on.
Following the existing pattern (e.g. ContextBuilder in context/interfaces.py),
these are abstract interfaces that the concrete services implement.
"""

from abc import ABC, abstractmethod
from typing import Optional

from app.measurements.models import ImprovementMeasurement
from app.scans.models import Scan


class ScanAccessor(ABC):
    """Read-only access to scan data for measurement comparison."""

    @abstractmethod
    async def get_scan(self, user_id: str, scan_id: str) -> Optional[Scan]:
        """Retrieve a scan by ID, validating ownership.

        Returns None if the scan does not exist or does not belong to the user.
        """
        ...


class MeasurementStore(ABC):
    """Storage for measurement results."""

    @abstractmethod
    def save(self, measurement: ImprovementMeasurement) -> ImprovementMeasurement:
        """Persist a measurement."""
        ...

    @abstractmethod
    def get(self, measurement_id: str) -> Optional[ImprovementMeasurement]:
        """Retrieve a measurement by ID."""
        ...

    @abstractmethod
    def list_for_remediation(
        self, remediation_id: str
    ) -> list[ImprovementMeasurement]:
        """List all measurements for a remediation."""
        ...
