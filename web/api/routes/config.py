"""Configuration API endpoints"""

import logging
import json
import os
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api.database import db_manager

router = APIRouter()
logger = logging.getLogger("fawkes.web.api.config")


@router.get("/", response_model=Dict[str, Any])
async def get_config():
    """
    Get current Fawkes configuration.

    Returns:
        Current configuration dictionary
    """
    try:
        return {
            "success": True,
            "data": db_manager.config
        }
    except Exception as e:
        logger.error(f"Error getting config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/", response_model=Dict[str, Any])
async def update_config(config_update: Dict[str, Any]):
    """
    Update Fawkes configuration.

    Args:
        config_update: Configuration fields to update

    Returns:
        Updated configuration
    """
    try:
        # Check if mode is changing
        old_mode = db_manager.config.get("fuzzing_mode", "local")
        new_mode = config_update.get("fuzzing_mode", old_mode)
        mode_changed = old_mode != new_mode

        # Merge with existing config
        db_manager.config.update(config_update)

        # Save to file
        config_path = os.path.expanduser("~/.fawkes/config.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        with open(config_path, 'w') as f:
            json.dump(db_manager.config, f, indent=2)

        logger.info(f"Configuration updated: {list(config_update.keys())}")

        # Reinitialize database if mode changed
        if mode_changed:
            logger.info(f"Fuzzing mode changed from {old_mode} to {new_mode}, reinitializing database...")
            db_manager.close()
            db_manager.initialize(mode=new_mode)

        return {
            "success": True,
            "message": "Configuration updated successfully",
            "data": db_manager.config
        }
    except Exception as e:
        logger.error(f"Error updating config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export")
async def export_config():
    """
    Export configuration as JSON file download.

    Returns:
        Configuration file as download
    """
    try:
        config_path = os.path.expanduser("~/.fawkes/config.json")

        if not os.path.exists(config_path):
            raise HTTPException(status_code=404, detail="Configuration file not found")

        return FileResponse(
            path=config_path,
            filename="fawkes_config.json",
            media_type="application/json"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import", response_model=Dict[str, Any])
async def import_config(config_data: Dict[str, Any]):
    """
    Import configuration from JSON.

    Args:
        config_data: Configuration to import

    Returns:
        Success confirmation
    """
    try:
        # Validate config (basic check)
        if not isinstance(config_data, dict):
            raise HTTPException(status_code=400, detail="Invalid configuration format")

        # Save to file
        config_path = os.path.expanduser("~/.fawkes/config.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)

        # Update in-memory config
        db_manager.config = config_data

        logger.info("Configuration imported successfully")

        return {
            "success": True,
            "message": "Configuration imported successfully",
            "data": config_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset", response_model=Dict[str, Any])
async def reset_config():
    """
    Reset configuration to defaults.

    Returns:
        Default configuration
    """
    try:
        # TODO: Load default config from tui.py
        default_config = {
            "fuzzing_mode": "local",
            "max_vms": 5,
            "log_level": "INFO",
            "enable_time_compression": False,
            "enable_persistent": False,
            "enable_corpus_sync": False
        }

        # Save to file
        config_path = os.path.expanduser("~/.fawkes/config.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=2)

        # Update in-memory config
        db_manager.config = default_config

        logger.info("Configuration reset to defaults")

        return {
            "success": True,
            "message": "Configuration reset to defaults",
            "data": default_config
        }
    except Exception as e:
        logger.error(f"Error resetting config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
