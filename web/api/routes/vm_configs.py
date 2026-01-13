"""
VM Configuration Management API endpoints.

Handles saving, loading, listing, and managing VM configuration JSON files.
These configs store all VM settings and can be loaded when starting a VM for fuzzing.
"""

import json
import logging
import os
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from paths import paths

router = APIRouter()
logger = logging.getLogger("fawkes.web.api.vm_configs")


class VMConfigCreate(BaseModel):
    """Request to create/save a VM configuration."""
    name: str = Field(..., description="Human-readable name for this VM config")
    description: Optional[str] = Field(None, description="Optional description")

    # Basic Configuration
    disk_image: str = Field(..., description="Path to the QCOW2 disk image")
    iso_path: Optional[str] = Field(None, description="Path to the ISO file")
    snapshot_name: Optional[str] = Field(None, description="Snapshot to use for fuzzing")
    arch: str = Field(default="x86_64", description="CPU architecture")

    # CPU Configuration
    memory: str = Field(default="2G", description="RAM allocation")
    cpu_cores: int = Field(default=2, description="Number of CPU cores")
    cpu_model: Optional[str] = Field(None, description="CPU model")
    cpu_features: Optional[str] = Field(None, description="CPU features")

    # Acceleration
    enable_kvm: bool = Field(default=True, description="Enable KVM")
    enable_hax: bool = Field(default=False, description="Enable HAXM")

    # Boot Configuration
    boot_order: str = Field(default="c", description="Boot order")
    boot_menu: bool = Field(default=False, description="Enable boot menu")
    uefi: bool = Field(default=False, description="Use UEFI")
    secure_boot: bool = Field(default=False, description="Enable Secure Boot")

    # Display/Graphics
    display: str = Field(default="vnc", description="Display type")
    vga: str = Field(default="std", description="VGA type")

    # Storage Configuration
    disk_interface: str = Field(default="virtio", description="Disk interface")
    disk_cache: str = Field(default="writeback", description="Disk cache mode")
    disk_aio: str = Field(default="threads", description="Disk AIO mode")

    # Network Configuration
    network_type: str = Field(default="user", description="Network type")
    network_model: str = Field(default="virtio-net-pci", description="NIC model")
    mac_address: Optional[str] = Field(None, description="MAC address")
    host_forward_ports: Optional[List[Dict[str, int]]] = Field(None, description="Port forwards")

    # USB Configuration
    usb_enabled: bool = Field(default=True, description="Enable USB")
    usb_tablet: bool = Field(default=True, description="USB tablet")

    # Audio
    audio_enabled: bool = Field(default=False, description="Enable audio")
    audio_device: str = Field(default="intel-hda", description="Audio device")

    # Serial/Parallel Ports
    serial_enabled: bool = Field(default=False, description="Enable serial port")
    serial_device: str = Field(default="pty", description="Serial device type")

    # TPM
    tpm_enabled: bool = Field(default=False, description="Enable TPM 2.0")
    tpm_version: str = Field(default="2.0", description="TPM version")

    # Machine Type
    machine_type: Optional[str] = Field(None, description="Machine type")

    # Advanced Options
    rtc_base: str = Field(default="utc", description="RTC base")
    no_shutdown: bool = Field(default=False, description="Don't exit on shutdown")
    no_reboot: bool = Field(default=False, description="Exit instead of rebooting")
    snapshot_mode: bool = Field(default=False, description="Run in snapshot mode")

    # Shared Folders
    shared_folders: Optional[List[Dict[str, str]]] = Field(None, description="Shared folders")

    # Extra QEMU Arguments
    extra_args: Optional[List[str]] = Field(None, description="Extra QEMU args")

    # Fuzzing-specific settings
    target_binary: Optional[str] = Field(None, description="Path to target binary in VM")
    target_args: Optional[str] = Field(None, description="Arguments for target binary")
    fuzzer_type: str = Field(default="file", description="Fuzzer type to use")
    timeout: int = Field(default=60, description="Execution timeout in seconds")

    # Tags for organization
    tags: Optional[List[str]] = Field(None, description="Tags for organization")


class VMConfigUpdate(BaseModel):
    """Request to update a VM configuration."""
    name: Optional[str] = None
    description: Optional[str] = None
    disk_image: Optional[str] = None
    iso_path: Optional[str] = None
    snapshot_name: Optional[str] = None
    arch: Optional[str] = None
    memory: Optional[str] = None
    cpu_cores: Optional[int] = None
    cpu_model: Optional[str] = None
    enable_kvm: Optional[bool] = None
    uefi: Optional[bool] = None
    tpm_enabled: Optional[bool] = None
    network_type: Optional[str] = None
    target_binary: Optional[str] = None
    target_args: Optional[str] = None
    fuzzer_type: Optional[str] = None
    timeout: Optional[int] = None
    tags: Optional[List[str]] = None


def get_configs_directory() -> Path:
    """Get the VM configs storage directory."""
    return paths.vm_configs_dir


def sanitize_filename(name: str) -> str:
    """Sanitize a name for use as a filename."""
    # Replace spaces and special characters with underscores
    safe_name = re.sub(r'[^\w\-.]', '_', name)
    # Remove leading/trailing underscores
    safe_name = safe_name.strip('_')
    # Limit length
    if len(safe_name) > 64:
        safe_name = safe_name[:64]
    return safe_name or "unnamed"


def generate_config_id() -> str:
    """Generate a unique config ID."""
    return str(uuid4())[:8]


def load_config_file(config_path: Path) -> Dict[str, Any]:
    """Load a VM config from a JSON file."""
    with open(config_path, 'r') as f:
        return json.load(f)


def save_config_file(config_path: Path, config: Dict[str, Any]) -> None:
    """Save a VM config to a JSON file."""
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2, default=str)


def get_config_info(config_path: Path) -> Dict[str, Any]:
    """Get summary info about a config file."""
    try:
        config = load_config_file(config_path)
        stat = config_path.stat()

        return {
            "id": config.get("id", config_path.stem),
            "filename": config_path.name,
            "path": str(config_path),
            "name": config.get("name", config_path.stem),
            "description": config.get("description"),
            "disk_image": config.get("disk_image"),
            "snapshot_name": config.get("snapshot_name"),
            "arch": config.get("arch", "x86_64"),
            "memory": config.get("memory", "2G"),
            "cpu_cores": config.get("cpu_cores", 2),
            "target_binary": config.get("target_binary"),
            "fuzzer_type": config.get("fuzzer_type", "file"),
            "tags": config.get("tags", []),
            "created_at": config.get("created_at"),
            "updated_at": config.get("updated_at"),
            "file_modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }
    except Exception as e:
        logger.warning(f"Error reading config {config_path}: {e}")
        return None


@router.get("/", response_model=Dict[str, Any])
async def list_vm_configs(tag: Optional[str] = None):
    """
    List all saved VM configurations.

    Args:
        tag: Optional tag to filter by
    """
    try:
        configs_dir = get_configs_directory()
        configs = []

        for config_path in configs_dir.glob("*.json"):
            if config_path.is_file():
                config_info = get_config_info(config_path)
                if config_info:
                    # Filter by tag if specified
                    if tag:
                        config_tags = config_info.get("tags", [])
                        if tag not in config_tags:
                            continue
                    configs.append(config_info)

        # Sort by updated_at (newest first)
        configs.sort(
            key=lambda x: x.get("updated_at") or x.get("file_modified_at") or "",
            reverse=True
        )

        return {
            "success": True,
            "count": len(configs),
            "configs_directory": str(configs_dir),
            "data": configs
        }
    except Exception as e:
        logger.error(f"Error listing VM configs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tags", response_model=Dict[str, Any])
async def list_tags():
    """
    List all unique tags used across VM configurations.
    """
    try:
        configs_dir = get_configs_directory()
        all_tags = set()

        for config_path in configs_dir.glob("*.json"):
            if config_path.is_file():
                try:
                    config = load_config_file(config_path)
                    tags = config.get("tags", [])
                    all_tags.update(tags)
                except:
                    pass

        return {
            "success": True,
            "count": len(all_tags),
            "data": sorted(list(all_tags))
        }
    except Exception as e:
        logger.error(f"Error listing tags: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=Dict[str, Any])
async def create_vm_config(request: VMConfigCreate):
    """
    Create and save a new VM configuration.

    The configuration is saved as a JSON file that can be loaded
    when starting a VM for fuzzing.
    """
    try:
        configs_dir = get_configs_directory()

        # Generate unique ID
        config_id = generate_config_id()

        # Create filename from name
        safe_name = sanitize_filename(request.name)
        filename = f"{safe_name}_{config_id}.json"
        config_path = configs_dir / filename

        # Build config dict
        now = datetime.now().isoformat()
        config = {
            "id": config_id,
            "version": "1.0",
            "created_at": now,
            "updated_at": now,
            **request.model_dump()
        }

        # Save config
        save_config_file(config_path, config)

        logger.info(f"VM config created: {filename}")

        return {
            "success": True,
            "message": f"VM configuration '{request.name}' saved successfully",
            "data": {
                "id": config_id,
                "filename": filename,
                "path": str(config_path),
                "name": request.name
            }
        }
    except Exception as e:
        logger.error(f"Error creating VM config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{config_id}", response_model=Dict[str, Any])
async def get_vm_config(config_id: str):
    """
    Get a specific VM configuration by ID.

    Args:
        config_id: The config ID or filename (without .json)
    """
    try:
        configs_dir = get_configs_directory()

        # Try to find by ID in filename
        matching_files = list(configs_dir.glob(f"*_{config_id}.json"))
        if not matching_files:
            # Try exact filename match
            exact_path = configs_dir / f"{config_id}.json"
            if exact_path.exists():
                matching_files = [exact_path]

        if not matching_files:
            # Try searching by ID inside configs
            for config_path in configs_dir.glob("*.json"):
                try:
                    config = load_config_file(config_path)
                    if config.get("id") == config_id:
                        matching_files = [config_path]
                        break
                except:
                    pass

        if not matching_files:
            raise HTTPException(status_code=404, detail=f"VM config '{config_id}' not found")

        config_path = matching_files[0]
        config = load_config_file(config_path)

        return {
            "success": True,
            "data": {
                "filename": config_path.name,
                "path": str(config_path),
                **config
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting VM config {config_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{config_id}", response_model=Dict[str, Any])
async def update_vm_config(config_id: str, request: VMConfigUpdate):
    """
    Update an existing VM configuration.

    Args:
        config_id: The config ID to update
        request: Fields to update
    """
    try:
        configs_dir = get_configs_directory()

        # Find the config file
        matching_files = list(configs_dir.glob(f"*_{config_id}.json"))
        if not matching_files:
            for config_path in configs_dir.glob("*.json"):
                try:
                    config = load_config_file(config_path)
                    if config.get("id") == config_id:
                        matching_files = [config_path]
                        break
                except:
                    pass

        if not matching_files:
            raise HTTPException(status_code=404, detail=f"VM config '{config_id}' not found")

        config_path = matching_files[0]
        config = load_config_file(config_path)

        # Update fields
        update_data = request.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                config[key] = value

        config["updated_at"] = datetime.now().isoformat()

        # Save updated config
        save_config_file(config_path, config)

        logger.info(f"VM config updated: {config_path.name}")

        return {
            "success": True,
            "message": "VM configuration updated successfully",
            "data": {
                "id": config_id,
                "filename": config_path.name,
                "updated_fields": list(update_data.keys())
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating VM config {config_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{config_id}", response_model=Dict[str, Any])
async def delete_vm_config(config_id: str):
    """
    Delete a VM configuration.

    Args:
        config_id: The config ID to delete
    """
    try:
        configs_dir = get_configs_directory()

        # Find the config file
        matching_files = list(configs_dir.glob(f"*_{config_id}.json"))
        if not matching_files:
            for config_path in configs_dir.glob("*.json"):
                try:
                    config = load_config_file(config_path)
                    if config.get("id") == config_id:
                        matching_files = [config_path]
                        break
                except:
                    pass

        if not matching_files:
            raise HTTPException(status_code=404, detail=f"VM config '{config_id}' not found")

        config_path = matching_files[0]
        config_path.unlink()

        logger.info(f"VM config deleted: {config_path.name}")

        return {
            "success": True,
            "message": "VM configuration deleted successfully",
            "data": {
                "id": config_id,
                "deleted_file": config_path.name
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting VM config {config_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{config_id}/duplicate", response_model=Dict[str, Any])
async def duplicate_vm_config(config_id: str, new_name: Optional[str] = None):
    """
    Duplicate an existing VM configuration.

    Args:
        config_id: The config ID to duplicate
        new_name: Optional new name for the duplicate
    """
    try:
        configs_dir = get_configs_directory()

        # Find the config file
        matching_files = list(configs_dir.glob(f"*_{config_id}.json"))
        if not matching_files:
            for config_path in configs_dir.glob("*.json"):
                try:
                    config = load_config_file(config_path)
                    if config.get("id") == config_id:
                        matching_files = [config_path]
                        break
                except:
                    pass

        if not matching_files:
            raise HTTPException(status_code=404, detail=f"VM config '{config_id}' not found")

        # Load original config
        config = load_config_file(matching_files[0])

        # Create new config
        new_config_id = generate_config_id()
        now = datetime.now().isoformat()

        config["id"] = new_config_id
        config["name"] = new_name or f"{config.get('name', 'Config')} (Copy)"
        config["created_at"] = now
        config["updated_at"] = now

        # Save new config
        safe_name = sanitize_filename(config["name"])
        filename = f"{safe_name}_{new_config_id}.json"
        config_path = configs_dir / filename

        save_config_file(config_path, config)

        logger.info(f"VM config duplicated: {filename}")

        return {
            "success": True,
            "message": "VM configuration duplicated successfully",
            "data": {
                "id": new_config_id,
                "filename": filename,
                "path": str(config_path),
                "name": config["name"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error duplicating VM config {config_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{config_id}/export", response_model=Dict[str, Any])
async def export_vm_config(config_id: str):
    """
    Export a VM configuration as a standalone JSON file.

    Returns the full configuration that can be imported on another system.
    """
    try:
        configs_dir = get_configs_directory()

        # Find the config file
        matching_files = list(configs_dir.glob(f"*_{config_id}.json"))
        if not matching_files:
            for config_path in configs_dir.glob("*.json"):
                try:
                    config = load_config_file(config_path)
                    if config.get("id") == config_id:
                        matching_files = [config_path]
                        break
                except:
                    pass

        if not matching_files:
            raise HTTPException(status_code=404, detail=f"VM config '{config_id}' not found")

        config = load_config_file(matching_files[0])

        # Add export metadata
        config["exported_at"] = datetime.now().isoformat()
        config["export_version"] = "1.0"

        return {
            "success": True,
            "message": "Configuration exported successfully",
            "data": config
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting VM config {config_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import", response_model=Dict[str, Any])
async def import_vm_config(config_data: Dict[str, Any]):
    """
    Import a VM configuration from JSON.

    Args:
        config_data: The configuration data to import
    """
    try:
        configs_dir = get_configs_directory()

        # Validate required fields
        if "name" not in config_data:
            raise HTTPException(status_code=400, detail="Configuration must have a 'name' field")
        if "disk_image" not in config_data:
            raise HTTPException(status_code=400, detail="Configuration must have a 'disk_image' field")

        # Generate new ID for imported config
        config_id = generate_config_id()
        now = datetime.now().isoformat()

        config_data["id"] = config_id
        config_data["created_at"] = now
        config_data["updated_at"] = now
        config_data["imported_at"] = now

        # Remove export metadata if present
        config_data.pop("exported_at", None)
        config_data.pop("export_version", None)

        # Save config
        safe_name = sanitize_filename(config_data["name"])
        filename = f"{safe_name}_{config_id}.json"
        config_path = configs_dir / filename

        save_config_file(config_path, config_data)

        logger.info(f"VM config imported: {filename}")

        return {
            "success": True,
            "message": f"VM configuration '{config_data['name']}' imported successfully",
            "data": {
                "id": config_id,
                "filename": filename,
                "path": str(config_path),
                "name": config_data["name"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing VM config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
