"""
Pydantic models for VM Setup functionality.

Includes models for ISO management, disk images, snapshots,
architectures, and VM profiles.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ============================================================================
# ISO Management Models
# ============================================================================

class ISOFile(BaseModel):
    """Represents an ISO file available for VM installation."""
    filename: str
    path: str
    size_bytes: int
    size_human: str  # e.g., "4.7 GB"
    created_at: datetime
    modified_at: datetime


class ISOUploadResponse(BaseModel):
    """Response after uploading an ISO."""
    success: bool
    filename: str
    path: str
    size_bytes: int
    message: str


# ============================================================================
# Disk Image Models
# ============================================================================

class DiskImageInfo(BaseModel):
    """Information about a QCOW2 disk image."""
    path: str
    filename: str
    format: str = "qcow2"
    virtual_size_bytes: int
    virtual_size_human: str  # e.g., "60 GB"
    actual_size_bytes: int
    actual_size_human: str  # e.g., "2.3 GB"
    created_at: Optional[datetime] = None
    modified_at: datetime
    snapshots: List["SnapshotInfo"] = []
    snapshot_count: int = 0


class DiskImageCreate(BaseModel):
    """Request to create a new disk image."""
    name: str = Field(..., description="Name for the disk image (without extension)")
    size_gb: int = Field(default=60, ge=1, le=2000, description="Size in gigabytes")
    format: str = Field(default="qcow2", description="Disk format (qcow2 recommended)")


class DiskImageCreateResponse(BaseModel):
    """Response after creating a disk image."""
    success: bool
    path: str
    size_gb: int
    message: str


# ============================================================================
# Snapshot Models
# ============================================================================

class SnapshotInfo(BaseModel):
    """Information about a VM snapshot."""
    name: str
    id: int
    tag: str
    vm_state_size: str  # e.g., "256 MiB" or "0 B" for disk-only
    vm_state_size_bytes: int
    date: Optional[datetime] = None
    vm_clock: Optional[str] = None  # e.g., "00:05:32.123"
    has_vm_state: bool  # True if snapshot includes VM memory state
    is_valid: bool = True  # Passes validation checks


class SnapshotCreate(BaseModel):
    """Request to create a snapshot."""
    name: str = Field(..., description="Name for the snapshot")
    description: Optional[str] = Field(None, description="Optional description")


class SnapshotValidation(BaseModel):
    """Result of snapshot validation."""
    name: str
    is_valid: bool
    has_vm_state: bool
    can_restore: bool
    error_message: Optional[str] = None
    warnings: List[str] = []


# ============================================================================
# Architecture Models
# ============================================================================

class ArchitectureInfo(BaseModel):
    """Information about a supported CPU architecture."""
    name: str  # e.g., "x86_64"
    display_name: str  # e.g., "x86 64-bit"
    qemu_binary: str  # e.g., "qemu-system-x86_64"
    gdb_arch: str  # e.g., "i386:x86-64"
    word_size: int  # 32 or 64
    endianness: str  # "little" or "big"
    available: bool  # True if QEMU binary exists on system
    family: str  # e.g., "x86", "arm", "mips"


class ArchitectureCheck(BaseModel):
    """Result of checking architecture availability."""
    arch: str
    available: bool
    qemu_binary: str
    qemu_version: Optional[str] = None
    error_message: Optional[str] = None


# ============================================================================
# VM Profile Models
# ============================================================================

class VMProfile(BaseModel):
    """A saved VM configuration profile."""
    id: Optional[int] = None
    name: str
    description: Optional[str] = None

    # Disk configuration
    disk_image: str
    snapshot_name: str

    # Architecture
    arch: str = "x86_64"

    # Resources
    memory: str = "256M"

    # Features
    enable_time_compression: bool = False
    time_compression_shift: str = "auto"
    enable_vm_screenshots: bool = False
    screenshot_interval: int = 5

    # Sharing
    share_method: str = "smb"  # "smb" or "vfs"

    # Optional
    vm_params: Optional[str] = None

    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class VMProfileCreate(BaseModel):
    """Request to create a VM profile."""
    name: str
    description: Optional[str] = None
    disk_image: str
    snapshot_name: str
    arch: str = "x86_64"
    memory: str = "256M"
    enable_time_compression: bool = False
    time_compression_shift: str = "auto"
    enable_vm_screenshots: bool = False
    screenshot_interval: int = 5
    share_method: str = "smb"
    vm_params: Optional[str] = None


# ============================================================================
# VM Installation Models
# ============================================================================

class VMInstallationStart(BaseModel):
    """Request to start a VM in installation mode."""
    disk_image: str = Field(..., description="Path to the QCOW2 disk image")
    iso_path: str = Field(..., description="Path to the ISO file")
    arch: str = Field(default="x86_64", description="CPU architecture")
    memory: str = Field(default="2G", description="RAM allocation for installation")
    enable_kvm: bool = Field(default=True, description="Enable KVM acceleration")


class VMInstallationStatus(BaseModel):
    """Status of a VM in installation mode."""
    vm_id: int
    pid: int
    status: str  # "running", "stopped"
    disk_image: str
    iso_path: str
    arch: str
    vnc_port: int
    vnc_websocket_port: int  # For noVNC
    monitor_port: int
    uptime_seconds: int
    can_create_snapshot: bool


class VMInstallationStop(BaseModel):
    """Request to stop installation VM and optionally create snapshot."""
    vm_id: int
    create_snapshot: bool = False
    snapshot_name: Optional[str] = None


# ============================================================================
# Storage Location Models
# ============================================================================

class StorageLocation(BaseModel):
    """A configured storage location for ISOs/disk images."""
    id: Optional[int] = None
    name: str
    path: str
    type: str  # "iso", "disk", "both"
    is_default: bool = False
    free_space_bytes: int
    free_space_human: str
    total_space_bytes: int
    total_space_human: str


# Update forward references
DiskImageInfo.model_rebuild()
