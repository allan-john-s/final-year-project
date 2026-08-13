"""Project domain models.

Provider-agnostic contracts shared by the service, repository, and API layers.
HTTP-layer validation/normalization lives in :mod:`app.schemas.projects`; these
models are the domain boundary between them.
"""

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProjectStatus(str, enum.Enum):
    """Controlled scan lifecycle state of a project."""

    NOT_SCANNED = "NOT_SCANNED"
    SCANNING = "SCANNING"
    SCANNED = "SCANNED"
    FAILED = "FAILED"


class Project(BaseModel):
    """A project as stored/retrieved from persistence."""

    id: str
    user_id: str
    name: str
    description: str = ""
    website_url: str
    status: ProjectStatus = ProjectStatus.NOT_SCANNED
    created_at: datetime
    updated_at: datetime


class ProjectCreateInput(BaseModel):
    """Inputs for creating a project (ownership is added by the service)."""

    name: str
    description: str = ""
    website_url: str


class ProjectCreate(BaseModel):
    """A fully-resolved create command, including the owning user id."""

    user_id: str
    name: str
    description: str = ""
    website_url: str
    status: ProjectStatus = ProjectStatus.NOT_SCANNED


class ProjectUpdate(BaseModel):
    """Partial update; ``None`` fields are left unchanged."""

    name: Optional[str] = None
    description: Optional[str] = None
    website_url: Optional[str] = None
    status: Optional[ProjectStatus] = None
