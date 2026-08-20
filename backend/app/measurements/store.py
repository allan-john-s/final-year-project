"""In-memory store for measurement results (Module 8).

Provides persistence for measurements during development/testing. In production,
this would be replaced by a Supabase-backed repository with RLS.

This store is NOT safe for concurrent access in production — it's intended
for single-process development and testing only.
"""

from typing import Dict, List, Optional

from app.measurements.models import ImprovementMeasurement
from app.measurements.interfaces import MeasurementStore


class InMemoryMeasurementStore(MeasurementStore):
    """Simple in-memory store for measurements."""

    def __init__(self) -> None:
        self._measurements: Dict[str, ImprovementMeasurement] = {}

    def save(self, measurement: ImprovementMeasurement) -> ImprovementMeasurement:
        """Save a measurement."""
        self._measurements[measurement.id] = measurement
        return measurement

    def get(self, measurement_id: str) -> Optional[ImprovementMeasurement]:
        """Get a measurement by ID."""
        return self._measurements.get(measurement_id)

    def list_for_remediation(
        self, remediation_id: str
    ) -> List[ImprovementMeasurement]:
        """List measurements for a remediation."""
        return [
            m
            for m in self._measurements.values()
            if m.remediation_id == remediation_id
        ]


# Global singleton for development/testing
_measurement_store = InMemoryMeasurementStore()


def get_measurement_store() -> InMemoryMeasurementStore:
    """Get the global measurement store."""
    return _measurement_store
