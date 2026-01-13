"""Crash models"""

from typing import Optional, List
from pydantic import BaseModel, Field


class CrashFilter(BaseModel):
    """Model for crash filtering."""
    severity: Optional[List[str]] = Field(None, description="Filter by severity (HIGH, MEDIUM, LOW)")
    sanitizer: Optional[List[str]] = Field(None, description="Filter by sanitizer type (ASan, UBSan, MSan)")
    unique_only: bool = Field(False, description="Show only unique crashes")
    job_id: Optional[int] = Field(None, description="Filter by job ID")


class Crash(BaseModel):
    """Model for crash response."""
    crash_id: int
    job_id: int
    testcase_path: Optional[str] = None
    crash_type: Optional[str] = None
    details: Optional[str] = None
    signature: Optional[str] = None
    exploitability: Optional[str] = None
    crash_file: Optional[str] = None
    timestamp: Optional[int] = None
    duplicate_count: Optional[int] = 0
    stack_hash: Optional[str] = None
    sanitizer_type: Optional[str] = None
    sanitizer_report: Optional[str] = None
    severity: Optional[str] = None
    is_unique: Optional[bool] = True

    class Config:
        from_attributes = True
