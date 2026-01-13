"""Job models"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    """Model for creating a new job."""
    name: str = Field(..., description="Job name")
    disk_image: str = Field(..., description="Path to VM disk image")
    snapshot: Optional[str] = Field(None, description="Snapshot name to restore")
    input_dir: str = Field(..., description="Input corpus directory")
    fuzzer_type: Optional[str] = Field(None, description="Fuzzer type (dumb, grammar, network, kernel)")
    fuzzer_config: Optional[Dict[str, Any]] = Field(None, description="Fuzzer-specific configuration")
    max_vms: int = Field(1, description="Maximum VMs to use")
    enable_time_compression: bool = Field(False, description="Enable time compression")
    enable_persistent: bool = Field(False, description="Enable persistent mode")
    enable_corpus_sync: bool = Field(False, description="Enable corpus synchronization")


class JobUpdate(BaseModel):
    """Model for updating a job."""
    status: Optional[str] = Field(None, description="Job status (running, paused, stopped, done)")
    max_vms: Optional[int] = Field(None, description="Maximum VMs to use")


class Job(BaseModel):
    """Model for job response."""
    job_id: int
    name: str
    disk: Optional[str] = None
    snapshot: Optional[str] = None
    status: str
    fuzzer_type: Optional[str] = None
    fuzzer_config: Optional[Dict[str, Any]] = None
    total_testcases: Optional[int] = 0
    generated_testcases: Optional[int] = 0
    create_time: Optional[int] = None
    vm_count: Optional[int] = 0

    class Config:
        from_attributes = True
