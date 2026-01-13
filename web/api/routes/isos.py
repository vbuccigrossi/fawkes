"""
ISO Management API endpoints.

Handles listing, uploading, and deleting ISO files for VM installation.
"""

import logging
import os
import shutil
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from paths import paths

from api.database import db_manager
from api.models.vm_setup import ISOFile, ISOUploadResponse

router = APIRouter()
logger = logging.getLogger("fawkes.web.api.isos")


def get_iso_directory() -> Path:
    """Get the ISO storage directory from centralized paths."""
    return paths.iso_dir


def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def get_iso_info(path: Path) -> ISOFile:
    """Get information about an ISO file."""
    stat = path.stat()
    return ISOFile(
        filename=path.name,
        path=str(path),
        size_bytes=stat.st_size,
        size_human=format_size(stat.st_size),
        created_at=datetime.fromtimestamp(stat.st_ctime),
        modified_at=datetime.fromtimestamp(stat.st_mtime)
    )


@router.get("/", response_model=Dict[str, Any])
async def list_isos():
    """
    List all available ISO files.

    Returns a list of ISO files in the configured ISO directory.
    """
    try:
        iso_dir = get_iso_directory()
        isos: List[ISOFile] = []

        # Find all ISO files
        for iso_path in iso_dir.glob("*.iso"):
            if iso_path.is_file():
                try:
                    isos.append(get_iso_info(iso_path))
                except Exception as e:
                    logger.warning(f"Error reading ISO {iso_path}: {e}")

        # Also check for ISOs in alternate locations from centralized paths
        alt_paths = paths.iso_search_paths
        for alt_path in alt_paths:
            alt_dir = alt_path if isinstance(alt_path, Path) else Path(os.path.expanduser(alt_path))
            if alt_dir.exists() and alt_dir.is_dir():
                for iso_path in alt_dir.glob("*.iso"):
                    if iso_path.is_file():
                        try:
                            iso_info = get_iso_info(iso_path)
                            # Avoid duplicates
                            if not any(i.path == iso_info.path for i in isos):
                                isos.append(iso_info)
                        except Exception as e:
                            logger.warning(f"Error reading ISO {iso_path}: {e}")

        # Sort by modification time (newest first)
        isos.sort(key=lambda x: x.modified_at, reverse=True)

        return {
            "success": True,
            "count": len(isos),
            "iso_directory": str(iso_dir),
            "data": [iso.model_dump() for iso in isos]
        }
    except Exception as e:
        logger.error(f"Error listing ISOs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{filename}", response_model=Dict[str, Any])
async def get_iso(filename: str):
    """
    Get details for a specific ISO file.

    Args:
        filename: Name of the ISO file
    """
    try:
        iso_dir = get_iso_directory()
        iso_path = iso_dir / filename

        if not iso_path.exists():
            # Check alternate paths from centralized config
            alt_paths = paths.iso_search_paths
            for alt_path in alt_paths:
                alt_dir = alt_path if isinstance(alt_path, Path) else Path(os.path.expanduser(alt_path))
                alt_iso = alt_dir / filename
                if alt_iso.exists():
                    iso_path = alt_iso
                    break
            else:
                raise HTTPException(status_code=404, detail=f"ISO '{filename}' not found")

        if not iso_path.is_file():
            raise HTTPException(status_code=404, detail=f"'{filename}' is not a file")

        iso_info = get_iso_info(iso_path)

        return {
            "success": True,
            "data": iso_info.model_dump()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ISO {filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=Dict[str, Any])
async def upload_iso(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """
    Upload a new ISO file.

    Accepts multipart file upload. Large files are streamed to disk.
    """
    try:
        # Validate file extension
        if not file.filename.lower().endswith('.iso'):
            raise HTTPException(
                status_code=400,
                detail="File must have .iso extension"
            )

        iso_dir = get_iso_directory()
        dest_path = iso_dir / file.filename

        # Check if file already exists
        if dest_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"ISO '{file.filename}' already exists. Delete it first or use a different name."
            )

        # Check available disk space
        stat = shutil.disk_usage(iso_dir)
        if file.size and file.size > stat.free:
            raise HTTPException(
                status_code=507,
                detail=f"Insufficient disk space. Need {format_size(file.size)}, have {format_size(stat.free)}"
            )

        # Stream file to disk
        logger.info(f"Uploading ISO: {file.filename}")
        total_written = 0

        with open(dest_path, 'wb') as f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                f.write(chunk)
                total_written += len(chunk)

        logger.info(f"ISO uploaded successfully: {file.filename} ({format_size(total_written)})")

        iso_info = get_iso_info(dest_path)

        return {
            "success": True,
            "message": f"ISO '{file.filename}' uploaded successfully",
            "data": iso_info.model_dump()
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
        logger.error(f"Error uploading ISO: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{filename}", response_model=Dict[str, Any])
async def delete_iso(filename: str):
    """
    Delete an ISO file.

    Args:
        filename: Name of the ISO file to delete
    """
    try:
        iso_dir = get_iso_directory()
        iso_path = iso_dir / filename

        if not iso_path.exists():
            raise HTTPException(status_code=404, detail=f"ISO '{filename}' not found")

        if not iso_path.is_file():
            raise HTTPException(status_code=400, detail=f"'{filename}' is not a file")

        # Get size before deletion for logging
        size = iso_path.stat().st_size

        # Delete the file
        iso_path.unlink()

        logger.info(f"ISO deleted: {filename} ({format_size(size)})")

        return {
            "success": True,
            "message": f"ISO '{filename}' deleted successfully",
            "deleted_size": size,
            "deleted_size_human": format_size(size)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting ISO {filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/storage/info", response_model=Dict[str, Any])
async def get_storage_info():
    """
    Get storage information for ISO directory.

    Returns disk space usage and availability.
    """
    try:
        iso_dir = get_iso_directory()
        stat = shutil.disk_usage(iso_dir)

        return {
            "success": True,
            "data": {
                "path": str(iso_dir),
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
