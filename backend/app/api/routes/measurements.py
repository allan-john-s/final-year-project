"""Measurement API surface (Module 8).

Endpoints for measuring improvement after a remediation has been accepted.

- POST /api/v1/remediations/{remediation_id}/measure — create a measurement
- GET /api/v1/remediations/{remediation_id}/measurements — list measurements
- GET /api/v1/measurements/{measurement_id} — get a specific measurement

All endpoints require authentication. Ownership is validated through the
scan accessor (original and follow-up scans must belong to the user).
"""

from typing import Annotated, List

from fastapi import APIRouter, Depends

from app.auth.interfaces import AuthUser
from app.dependencies.auth import get_current_user
from app.dependencies.measurements import get_measurement_service
from app.measurements.exceptions import MeasurementNotFoundError
from app.measurements.models import ImprovementMeasurement
from app.measurements.services import MeasurementService
from app.measurements.store import InMemoryMeasurementStore, get_measurement_store
from app.schemas.measurements import MeasureRequest

router = APIRouter(prefix="/remediations", tags=["measurements"])
measurement_router = APIRouter(prefix="/measurements", tags=["measurements"])

MeasurementServiceDep = Annotated[MeasurementService, Depends(get_measurement_service)]
CurrentUserDep = Annotated[AuthUser, Depends(get_current_user)]
StoreDep = Annotated[InMemoryMeasurementStore, Depends(get_measurement_store)]


@router.post(
    "/{remediation_id}/measure",
    response_model=ImprovementMeasurement,
    summary="Measure accessibility improvement after remediation",
)
async def create_measurement(
    remediation_id: str,
    payload: MeasureRequest,
    user: CurrentUserDep,
    service: MeasurementServiceDep,
) -> ImprovementMeasurement:
    """Create a measurement comparing original scan vs follow-up scan.

    The server validates that:
    - The remediation exists and is ACCEPTED or APPLIED
    - The original scan belongs to the user
    - The follow-up scan belongs to the user
    - The follow-up scan is completed
    - The follow-up scan was created after the original scan
    """
    return await service.measure(
        user.id,
        remediation_id,
        payload.followup_scan_id,
    )


@router.get(
    "/{remediation_id}/measurements",
    response_model=List[ImprovementMeasurement],
    summary="List measurements for a remediation",
)
async def list_measurements(
    remediation_id: str,
    user: CurrentUserDep,
    store: StoreDep,
) -> List[ImprovementMeasurement]:
    """List all measurements for a remediation."""
    return store.list_for_remediation(remediation_id)


@measurement_router.get(
    "/{measurement_id}",
    response_model=ImprovementMeasurement,
    summary="Get a specific measurement",
)
async def get_measurement(
    measurement_id: str,
    user: CurrentUserDep,
    store: StoreDep,
) -> ImprovementMeasurement:
    """Get a measurement by ID."""
    measurement = store.get(measurement_id)
    if measurement is None:
        raise MeasurementNotFoundError("The measurement was not found.")
    return measurement
