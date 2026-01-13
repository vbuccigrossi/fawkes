"""
Paths API endpoints.

Provides access to the centralized Fawkes paths configuration.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, HTTPException

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from paths import paths, FawkesPaths

router = APIRouter()
logger = logging.getLogger("fawkes.web.api.paths")


@router.get("/", response_model=Dict[str, Any])
async def get_all_paths():
    """
    Get all configured paths.

    Returns the complete paths configuration including all directories
    and search paths used by Fawkes.
    """
    try:
        return {
            "success": True,
            "data": paths.get_all_paths()
        }
    except Exception as e:
        logger.error(f"Error getting paths: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/directories", response_model=Dict[str, Any])
async def get_directories():
    """
    Get all standard directories.

    Returns only the directory paths (not files or search paths).
    """
    try:
        dirs = {
            "base_dir": str(paths.base_dir),
            "iso_dir": str(paths.iso_dir),
            "images_dir": str(paths.images_dir),
            "snapshots_dir": str(paths.snapshots_dir),
            "firmware_dir": str(paths.firmware_dir),
            "corpus_dir": str(paths.corpus_dir),
            "crashes_dir": str(paths.crashes_dir),
            "jobs_dir": str(paths.jobs_dir),
            "logs_dir": str(paths.logs_dir),
            "screenshots_dir": str(paths.screenshots_dir),
            "shared_dir": str(paths.shared_dir),
            "tmp_dir": str(paths.tmp_dir),
        }
        return {
            "success": True,
            "data": dirs
        }
    except Exception as e:
        logger.error(f"Error getting directories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search", response_model=Dict[str, Any])
async def get_search_paths():
    """
    Get search paths for ISOs and images.

    Returns the additional search paths used when looking for files.
    """
    try:
        return {
            "success": True,
            "data": {
                "iso_search_paths": [str(p) for p in paths.iso_search_paths],
                "images_search_paths": [str(p) for p in paths.images_search_paths],
            }
        }
    except Exception as e:
        logger.error(f"Error getting search paths: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ensure", response_model=Dict[str, Any])
async def ensure_directories():
    """
    Ensure all standard directories exist.

    Creates any missing directories in the standard structure.
    """
    try:
        paths.ensure_all_directories()
        return {
            "success": True,
            "message": "All directories created/verified",
            "data": paths.get_all_paths()
        }
    except Exception as e:
        logger.error(f"Error ensuring directories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{path_key}", response_model=Dict[str, Any])
async def set_path(path_key: str, path_value: str):
    """
    Set a custom path override.

    Args:
        path_key: The path key to set (e.g., "iso_dir", "images_dir")
        path_value: The new path value
    """
    try:
        # Validate the path key
        valid_keys = [
            "iso_dir", "images_dir", "snapshots_dir", "firmware_dir",
            "corpus_dir", "crashes_dir", "jobs_dir", "logs_dir",
            "screenshots_dir", "shared_dir", "tmp_dir",
            "config_file", "database_file", "registry_file"
        ]

        if path_key not in valid_keys:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid path key: {path_key}. Valid keys: {', '.join(valid_keys)}"
            )

        # Validate the path
        expanded_path = Path(path_value).expanduser().resolve()

        # For directories, try to create them
        if path_key.endswith("_dir"):
            expanded_path.mkdir(parents=True, exist_ok=True)

        # Set the path
        paths.set_path(path_key, str(expanded_path))

        logger.info(f"Path '{path_key}' set to '{expanded_path}'")

        return {
            "success": True,
            "message": f"Path '{path_key}' updated",
            "data": {
                "key": path_key,
                "value": str(expanded_path)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting path {path_key}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{path_key}", response_model=Dict[str, Any])
async def reset_path(path_key: str):
    """
    Reset a path to its default value.

    Args:
        path_key: The path key to reset
    """
    try:
        paths.reset_path(path_key)
        logger.info(f"Path '{path_key}' reset to default")

        return {
            "success": True,
            "message": f"Path '{path_key}' reset to default"
        }
    except Exception as e:
        logger.error(f"Error resetting path {path_key}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset", response_model=Dict[str, Any])
async def reset_all_paths():
    """
    Reset all paths to their default values.
    """
    try:
        paths.reset_all_paths()
        logger.info("All paths reset to defaults")

        return {
            "success": True,
            "message": "All paths reset to defaults",
            "data": paths.get_all_paths()
        }
    except Exception as e:
        logger.error(f"Error resetting all paths: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
