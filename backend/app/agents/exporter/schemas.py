from uuid import UUID

from pydantic import BaseModel


class ExportRequest(BaseModel):
    session_id: UUID
    format: str = "csv"  # csv | excel
    include_unflagged_only: bool = True


class ExportAccepted(BaseModel):
    job_id: UUID
    status: str  # "queued"


class ExportJobStatus(BaseModel):
    status: str  # queued | completed | failed
    session_id: UUID
    download_url: str | None = None
    row_count: int | None = None
    flagged_excluded: int | None = None
    error: str | None = None


class ExportBlockedError(Exception):
    """Quedan items flaggeados sin is_approved resuelto (CLAUDE.md §3.4)."""


class SessionAlreadyExportedError(Exception):
    """La sesion ya fue exportada — segundo intento debe responder 409."""
