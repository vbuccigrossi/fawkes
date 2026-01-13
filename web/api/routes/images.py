"""
Disk Image Management API endpoints.

Handles listing, creating, and managing QCOW2 disk images for VMs.
"""

import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from paths import paths

from api.database import db_manager
from api.models.vm_setup import (
    DiskImageInfo, DiskImageCreate, DiskImageCreateResponse,
    SnapshotInfo
)

router = APIRouter()
logger = logging.getLogger("fawkes.web.api.images")


def get_images_directory() -> Path:
    """Get the disk images storage directory from centralized paths."""
    return paths.images_dir


def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def parse_size_string(size_str: str) -> int:
    """Parse size string like '60G' or '256 MiB' to bytes."""
    size_str = size_str.strip().upper()

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


def get_qemu_img_info(path: Path) -> Dict[str, Any]:
    """Get disk image info using qemu-img."""
    try:
        result = subprocess.run(
            ['qemu-img', 'info', '--output=json', str(path)],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            import json
            return json.loads(result.stdout)
    except Exception as e:
        logger.warning(f"Error running qemu-img info: {e}")
    return {}


def get_snapshots(path: Path) -> List[SnapshotInfo]:
    """Get list of snapshots in a disk image."""
    snapshots = []
    try:
        result = subprocess.run(
            ['qemu-img', 'snapshot', '-l', str(path)],
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
                if len(parts) >= 4:
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
                            is_valid=vm_size_bytes > 0  # Basic validity check
                        ))
                    except Exception as e:
                        logger.warning(f"Error parsing snapshot line '{line}': {e}")
    except Exception as e:
        logger.warning(f"Error getting snapshots: {e}")
    return snapshots


def get_disk_image_info(path: Path) -> DiskImageInfo:
    """Get comprehensive information about a disk image."""
    stat = path.stat()

    # Get qemu-img info
    qemu_info = get_qemu_img_info(path)
    virtual_size = qemu_info.get('virtual-size', stat.st_size)
    actual_size = qemu_info.get('actual-size', stat.st_size)
    format_type = qemu_info.get('format', 'qcow2')

    # Get snapshots
    snapshots = get_snapshots(path)

    return DiskImageInfo(
        path=str(path),
        filename=path.name,
        format=format_type,
        virtual_size_bytes=virtual_size,
        virtual_size_human=format_size(virtual_size),
        actual_size_bytes=actual_size,
        actual_size_human=format_size(actual_size),
        created_at=datetime.fromtimestamp(stat.st_ctime),
        modified_at=datetime.fromtimestamp(stat.st_mtime),
        snapshots=snapshots,
        snapshot_count=len(snapshots)
    )


@router.get("/", response_model=Dict[str, Any])
async def list_images():
    """
    List all available disk images.

    Returns a list of QCOW2 disk images in the configured directory.
    """
    try:
        images_dir = get_images_directory()
        images: List[DiskImageInfo] = []

        # Find all QCOW2 files
        for pattern in ['*.qcow2', '*.qcow', '*.img']:
            for img_path in images_dir.glob(pattern):
                if img_path.is_file():
                    try:
                        images.append(get_disk_image_info(img_path))
                    except Exception as e:
                        logger.warning(f"Error reading image {img_path}: {e}")

        # Also check alternate locations from centralized paths
        alt_paths = paths.images_search_paths
        for alt_path in alt_paths:
            alt_dir = alt_path if isinstance(alt_path, Path) else Path(os.path.expanduser(alt_path))
            if alt_dir.exists() and alt_dir.is_dir():
                for pattern in ['*.qcow2', '*.qcow', '*.img']:
                    for img_path in alt_dir.glob(pattern):
                        if img_path.is_file():
                            try:
                                img_info = get_disk_image_info(img_path)
                                # Avoid duplicates
                                if not any(i.path == img_info.path for i in images):
                                    images.append(img_info)
                            except Exception as e:
                                logger.warning(f"Error reading image {img_path}: {e}")

        # Sort by modification time (newest first)
        images.sort(key=lambda x: x.modified_at, reverse=True)

        return {
            "success": True,
            "count": len(images),
            "images_directory": str(images_dir),
            "data": [img.model_dump() for img in images]
        }
    except Exception as e:
        logger.error(f"Error listing images: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/info", response_model=Dict[str, Any])
async def get_image_by_path(path: str):
    """
    Get details for a disk image by path.

    Args:
        path: Full path to the disk image
    """
    try:
        img_path = Path(os.path.expanduser(path))

        if not img_path.exists():
            raise HTTPException(status_code=404, detail=f"Image not found: {path}")

        if not img_path.is_file():
            raise HTTPException(status_code=400, detail=f"Not a file: {path}")

        img_info = get_disk_image_info(img_path)

        return {
            "success": True,
            "data": img_info.model_dump()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting image info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create", response_model=Dict[str, Any])
async def create_image(request: DiskImageCreate):
    """
    Create a new QCOW2 disk image.

    Args:
        request: Disk creation parameters (name, size)
    """
    try:
        images_dir = get_images_directory()

        # Sanitize filename
        safe_name = re.sub(r'[^\w\-.]', '_', request.name)
        if not safe_name.endswith('.qcow2'):
            safe_name += '.qcow2'

        dest_path = images_dir / safe_name

        # Check if file already exists
        if dest_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"Image '{safe_name}' already exists"
            )

        # Check available disk space (need at least the virtual size for metadata)
        stat = shutil.disk_usage(images_dir)
        min_space_needed = 1024 * 1024 * 100  # 100MB minimum for sparse file
        if stat.free < min_space_needed:
            raise HTTPException(
                status_code=507,
                detail=f"Insufficient disk space. Need at least {format_size(min_space_needed)}"
            )

        # Create the disk image using qemu-img
        logger.info(f"Creating disk image: {safe_name} ({request.size_gb}GB)")

        result = subprocess.run(
            ['qemu-img', 'create', '-f', 'qcow2', str(dest_path), f'{request.size_gb}G'],
            capture_output=True, text=True, timeout=60
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create disk image: {result.stderr}"
            )

        logger.info(f"Disk image created: {dest_path}")

        # Get info about created image
        img_info = get_disk_image_info(dest_path)

        return {
            "success": True,
            "message": f"Disk image '{safe_name}' created successfully",
            "data": img_info.model_dump()
        }

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Image creation timed out")
    except Exception as e:
        logger.error(f"Error creating image: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=Dict[str, Any])
async def upload_image(file: UploadFile = File(...)):
    """
    Upload a disk image file.

    Accepts multipart file upload. Large files are streamed to disk.
    """
    try:
        # Validate file extension
        valid_extensions = ['.qcow2', '.qcow', '.img', '.raw']
        if not any(file.filename.lower().endswith(ext) for ext in valid_extensions):
            raise HTTPException(
                status_code=400,
                detail=f"File must have one of these extensions: {', '.join(valid_extensions)}"
            )

        images_dir = get_images_directory()
        dest_path = images_dir / file.filename

        # Check if file already exists
        if dest_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"Image '{file.filename}' already exists"
            )

        # Check available disk space
        stat = shutil.disk_usage(images_dir)
        if file.size and file.size > stat.free:
            raise HTTPException(
                status_code=507,
                detail=f"Insufficient disk space. Need {format_size(file.size)}, have {format_size(stat.free)}"
            )

        # Stream file to disk
        logger.info(f"Uploading disk image: {file.filename}")
        total_written = 0

        with open(dest_path, 'wb') as f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                f.write(chunk)
                total_written += len(chunk)

        logger.info(f"Disk image uploaded: {file.filename} ({format_size(total_written)})")

        # Get info about uploaded image
        img_info = get_disk_image_info(dest_path)

        return {
            "success": True,
            "message": f"Disk image '{file.filename}' uploaded successfully",
            "data": img_info.model_dump()
        }

    except HTTPException:
        raise
    except Exception as e:
        # Clean up partial file on error
        if 'dest_path' in locals() and dest_path.exists():
            try:
                dest_path.unlink()
            except:
                pass
        logger.error(f"Error uploading image: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/", response_model=Dict[str, Any])
async def delete_image(path: str):
    """
    Delete a disk image.

    Args:
        path: Full path to the disk image to delete
    """
    try:
        img_path = Path(os.path.expanduser(path))

        if not img_path.exists():
            raise HTTPException(status_code=404, detail=f"Image not found: {path}")

        if not img_path.is_file():
            raise HTTPException(status_code=400, detail=f"Not a file: {path}")

        # Security check - only allow deletion from managed directories
        images_dir = get_images_directory()
        alt_paths = paths.images_search_paths
        allowed_dirs = [images_dir] + [p if isinstance(p, Path) else Path(os.path.expanduser(p)) for p in alt_paths]

        if not any(img_path.parent == d or img_path.parent.is_relative_to(d) for d in allowed_dirs):
            raise HTTPException(
                status_code=403,
                detail="Cannot delete images outside managed directories"
            )

        # Get size before deletion
        size = img_path.stat().st_size

        # Delete the file
        img_path.unlink()

        logger.info(f"Disk image deleted: {path} ({format_size(size)})")

        return {
            "success": True,
            "message": f"Disk image deleted successfully",
            "deleted_path": path,
            "deleted_size": size,
            "deleted_size_human": format_size(size)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting image: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/storage/info", response_model=Dict[str, Any])
async def get_storage_info():
    """
    Get storage information for images directory.
    """
    try:
        images_dir = get_images_directory()
        stat = shutil.disk_usage(images_dir)

        return {
            "success": True,
            "data": {
                "path": str(images_dir),
                "total_bytes": stat.total,
                "total_human": format_size(stat.total),
                "used_bytes": stat.used,
                "used_human": format_size(stat.used),
                "free_bytes": stat.free,
                "free_human": format_size(stat.free),
                "usage_percent": round((stat.used / stat.total) * 100, 1)
            }
        }
    except Exception as e:
        logger.error(f"Error getting storage info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
