"""
Snapshot Management API endpoints.

Handles listing, creating, validating, and deleting VM snapshots.
"""

import logging
import os
import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException

from api.database import db_manager
from api.models.vm_setup import SnapshotInfo, SnapshotCreate, SnapshotValidation

router = APIRouter()
logger = logging.getLogger("fawkes.web.api.snapshots")


def parse_size_string(size_str: str) -> int:
    """Parse size string like '60G' or '256 MiB' to bytes."""
    size_str = size_str.strip().upper()

    # Handle "0 B" or "0B" case
    if size_str in ['0', '0B', '0 B']:
        return 0

    # Match patterns like "60G", "256 MiB", "1.5 GB"
    match = re.match(r'^([\d.]+)\s*([KMGTP]I?B?)?$', size_str)
    if not match:
        return 0

    value = float(match.group(1))
    unit = match.group(2) or 'B'

    multipliers = {
        'B': 1,
        'K': 1024, 'KB': 1024, 'KIB': 1024,
        'M': 1024**2, 'MB': 1024**2, 'MIB': 1024**2,
        'G': 1024**3, 'GB': 1024**3, 'GIB': 1024**3,
        'T': 1024**4, 'TB': 1024**4, 'TIB': 1024**4,
        'P': 1024**5, 'PB': 1024**5, 'PIB': 1024**5,
    }

    return int(value * multipliers.get(unit, 1))


def get_snapshots(disk_path: Path) -> List[SnapshotInfo]:
    """Get list of snapshots in a disk image."""
    snapshots = []
    try:
        result = subprocess.run(
            ['qemu-img', 'snapshot', '-l', str(disk_path)],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            # Parse qemu-img snapshot output
            # Format: ID  TAG   VM SIZE   DATE   VM CLOCK
            lines = result.stdout.strip().split('\n')
            for line in lines[2:]:  # Skip header lines
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        snap_id = int(parts[0])
                        tag = parts[1]
                        vm_size_str = parts[2]
                        vm_size_bytes = parse_size_string(vm_size_str)

                        # Parse date if available
                        date = None
                        vm_clock = None
                        if len(parts) >= 5:
                            try:
                                date_str = f"{parts[3]} {parts[4]}"
                                date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                            except:
                                pass
                        if len(parts) >= 6:
                            vm_clock = parts[5]

                        snapshots.append(SnapshotInfo(
                            name=tag,
                            id=snap_id,
                            tag=tag,
                            vm_state_size=vm_size_str,
                            vm_state_size_bytes=vm_size_bytes,
                            date=date,
                            vm_clock=vm_clock,
                            has_vm_state=vm_size_bytes > 0,
                            is_valid=vm_size_bytes > 0
                        ))
                    except Exception as e:
                        logger.warning(f"Error parsing snapshot line '{line}': {e}")
    except Exception as e:
        logger.warning(f"Error getting snapshots: {e}")
    return snapshots


@router.get("/", response_model=Dict[str, Any])
async def list_snapshots(disk_path: str):
    """
    List all snapshots in a disk image.

    Args:
        disk_path: Path to the QCOW2 disk image
    """
    try:
        path = Path(os.path.expanduser(disk_path))

        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Disk image not found: {disk_path}")

        if not path.is_file():
            raise HTTPException(status_code=400, detail=f"Not a file: {disk_path}")

        snapshots = get_snapshots(path)

        return {
            "success": True,
            "disk_path": str(path),
            "count": len(snapshots),
            "data": [snap.model_dump() for snap in snapshots]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing snapshots: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{snapshot_name}", response_model=Dict[str, Any])
async def get_snapshot(disk_path: str, snapshot_name: str):
    """
    Get details for a specific snapshot.

    Args:
        disk_path: Path to the QCOW2 disk image
        snapshot_name: Name of the snapshot
    """
    try:
        path = Path(os.path.expanduser(disk_path))

        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Disk image not found: {disk_path}")

        snapshots = get_snapshots(path)
        snapshot = next((s for s in snapshots if s.name == snapshot_name), None)

        if not snapshot:
            raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_name}' not found")

        return {
            "success": True,
            "disk_path": str(path),
            "data": snapshot.model_dump()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting snapshot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=Dict[str, Any])
async def create_snapshot(disk_path: str, request: SnapshotCreate):
    """
    Create a new snapshot in a disk image.

    Note: This creates a disk-only snapshot. To create a snapshot with VM state,
    use the VM installation endpoint while the VM is running.

    Args:
        disk_path: Path to the QCOW2 disk image
        request: Snapshot creation parameters
    """
    try:
        path = Path(os.path.expanduser(disk_path))

        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Disk image not found: {disk_path}")

        # Check if snapshot already exists
        existing = get_snapshots(path)
        if any(s.name == request.name for s in existing):
            raise HTTPException(
                status_code=409,
                detail=f"Snapshot '{request.name}' already exists"
            )

        # Create snapshot using qemu-img
        logger.info(f"Creating snapshot '{request.name}' in {path}")

        result = subprocess.run(
            ['qemu-img', 'snapshot', '-c', request.name, str(path)],
            capture_output=True, text=True, timeout=120
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create snapshot: {result.stderr}"
            )

        # Get info about created snapshot
        snapshots = get_snapshots(path)
        snapshot = next((s for s in snapshots if s.name == request.name), None)

        logger.info(f"Snapshot created: {request.name}")

        return {
            "success": True,
            "message": f"Snapshot '{request.name}' created successfully",
            "warning": "This is a disk-only snapshot. For fuzzing, you need a snapshot with VM state. "
                      "Create the snapshot from a running VM using the QEMU monitor.",
            "data": snapshot.model_dump() if snapshot else None
        }

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Snapshot creation timed out")
    except Exception as e:
        logger.error(f"Error creating snapshot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{snapshot_name}", response_model=Dict[str, Any])
async def delete_snapshot(disk_path: str, snapshot_name: str):
    """
    Delete a snapshot from a disk image.

    Args:
        disk_path: Path to the QCOW2 disk image
        snapshot_name: Name of the snapshot to delete
    """
    try:
        path = Path(os.path.expanduser(disk_path))

        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Disk image not found: {disk_path}")

        # Check if snapshot exists
        snapshots = get_snapshots(path)
        if not any(s.name == snapshot_name for s in snapshots):
            raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_name}' not found")

        # Delete snapshot using qemu-img
        logger.info(f"Deleting snapshot '{snapshot_name}' from {path}")

        result = subprocess.run(
            ['qemu-img', 'snapshot', '-d', snapshot_name, str(path)],
            capture_output=True, text=True, timeout=120
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete snapshot: {result.stderr}"
            )

        logger.info(f"Snapshot deleted: {snapshot_name}")

        return {
            "success": True,
            "message": f"Snapshot '{snapshot_name}' deleted successfully"
        }

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Snapshot deletion timed out")
    except Exception as e:
        logger.error(f"Error deleting snapshot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{snapshot_name}/validate", response_model=Dict[str, Any])
async def validate_snapshot(disk_path: str, snapshot_name: str):
    """
    Validate a snapshot for use with fuzzing.

    Checks:
    1. Snapshot exists
    2. Snapshot has VM state (not disk-only)
    3. Snapshot can be loaded

    Args:
        disk_path: Path to the QCOW2 disk image
        snapshot_name: Name of the snapshot to validate
    """
    try:
        path = Path(os.path.expanduser(disk_path))

        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Disk image not found: {disk_path}")

        # Check if snapshot exists
        snapshots = get_snapshots(path)
        snapshot = next((s for s in snapshots if s.name == snapshot_name), None)

        if not snapshot:
            return {
                "success": True,
                "data": SnapshotValidation(
                    name=snapshot_name,
                    is_valid=False,
                    has_vm_state=False,
                    can_restore=False,
                    error_message=f"Snapshot '{snapshot_name}' not found"
                ).model_dump()
            }

        warnings = []

        # Check if snapshot has VM state
        if not snapshot.has_vm_state:
            warnings.append(
                "Snapshot has no VM state (disk-only). "
                "Fuzzing requires a snapshot with VM state. "
                "Create the snapshot using 'savevm' in QEMU monitor while VM is running."
            )

        # Try to verify snapshot integrity
        # Note: We can't actually load the snapshot without running QEMU,
        # but we can check the disk image integrity
        result = subprocess.run(
            ['qemu-img', 'check', str(path)],
            capture_output=True, text=True, timeout=60
        )

        can_restore = True
        if result.returncode != 0:
            if 'error' in result.stderr.lower():
                can_restore = False
                warnings.append(f"Disk image may have errors: {result.stderr.strip()}")

        is_valid = snapshot.has_vm_state and can_restore

        validation = SnapshotValidation(
            name=snapshot_name,
            is_valid=is_valid,
            has_vm_state=snapshot.has_vm_state,
            can_restore=can_restore,
            error_message=None if is_valid else "Snapshot is not valid for fuzzing",
            warnings=warnings
        )

        return {
            "success": True,
            "data": validation.model_dump()
        }

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Validation timed out")
    except Exception as e:
        logger.error(f"Error validating snapshot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply", response_model=Dict[str, Any])
async def apply_snapshot(disk_path: str, snapshot_name: str):
    """
    Apply/restore a snapshot to the disk image.

    WARNING: This will revert the disk to the snapshot state.
    Only use on disks that are not currently in use.

    Args:
        disk_path: Path to the QCOW2 disk image
        snapshot_name: Name of the snapshot to apply
    """
    try:
        path = Path(os.path.expanduser(disk_path))

        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Disk image not found: {disk_path}")

        # Check if snapshot exists
        snapshots = get_snapshots(path)
        if not any(s.name == snapshot_name for s in snapshots):
            raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_name}' not found")

        # Apply snapshot using qemu-img
        logger.info(f"Applying snapshot '{snapshot_name}' to {path}")

        result = subprocess.run(
            ['qemu-img', 'snapshot', '-a', snapshot_name, str(path)],
            capture_output=True, text=True, timeout=120
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to apply snapshot: {result.stderr}"
            )

        logger.info(f"Snapshot applied: {snapshot_name}")

        return {
            "success": True,
            "message": f"Snapshot '{snapshot_name}' applied successfully",
            "warning": "Disk has been reverted to snapshot state"
        }

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Snapshot application timed out")
    except Exception as e:
        logger.error(f"Error applying snapshot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
