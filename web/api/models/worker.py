"""Worker models (controller mode)"""

from typing import Optional
from pydantic import BaseModel, Field


class WorkerCreate(BaseModel):
    """Model for adding a new worker."""
    ip_address: str = Field(..., description="Worker IP address")


class Worker(BaseModel):
    """Model for worker response."""
    worker_id: int
    ip_address: str
    status: str  # online, offline, busy
    last_seen: Optional[str] = None

    class Config:
        from_attributes = True
