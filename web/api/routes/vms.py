"""VM API endpoints - including screenshot functionality"""

import logging
import base64
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.database import db_manager

router = APIRouter()
logger = logging.getLogger("fawkes.web.api.vms")

# Global reference to QEMU manager (set by executor when initialized)
_qemu_manager = None


def set_qemu_manager(qemu_mgr):
    """Set the QEMU manager reference for screenshot functionality."""
    global _qemu_manager
    _qemu_manager = qemu_mgr
    logger.info("QEMU manager registered for VM screenshots")


def get_qemu_manager():
    """Get the QEMU manager instance."""
    global _qemu_manager
    return _qemu_manager


@router.get("/")
async def list_vms() -> Dict[str, Any]:
    """
    List all VMs in the registry.

    Returns VM info including status, ports, and screenshot availability.
    """
    try:
        qemu_mgr = get_qemu_manager()
        if not qemu_mgr or not qemu_mgr.registry:
            return {
                "success": True,
                "count": 0,
                "data": [],
                "message": "No VMs registered (QEMU manager not initialized)"
            }

        vms = []
        for vm_id, vm_info in qemu_mgr.registry.vms.items():
            if not isinstance(vm_info, dict):
                continue

            vms.append({
                "vm_id": vm_id,
                "pid": vm_info.get("pid"),
                "status": vm_info.get("status"),
                "arch": vm_info.get("arch"),
                "disk_path": vm_info.get("disk_path"),
                "snapshot_name": vm_info.get("snapshot_name"),
                "screenshots_enabled": vm_info.get("screenshots_enabled", False),
                "vnc_port": vm_info.get("vnc_port"),
                "monitor_port": vm_info.get("monitor_port"),
                "debug_port": vm_info.get("debug_port"),
                "agent_port": vm_info.get("agent_port"),
            })

        return {
            "success": True,
            "count": len(vms),
            "data": vms
        }
    except Exception as e:
        logger.error(f"Error listing VMs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{vm_id}")
async def get_vm(vm_id: int) -> Dict[str, Any]:
    """
    Get details for a specific VM.
    """
    try:
        qemu_mgr = get_qemu_manager()
        if not qemu_mgr or not qemu_mgr.registry:
            raise HTTPException(status_code=503, detail="QEMU manager not initialized")

        vm_info = qemu_mgr.registry.get_vm(vm_id)
        if not vm_info:
            raise HTTPException(status_code=404, detail=f"VM {vm_id} not found")

        return {
            "success": True,
            "data": {
                "vm_id": vm_id,
                "pid": vm_info.get("pid"),
                "status": vm_info.get("status"),
                "arch": vm_info.get("arch"),
                "disk_path": vm_info.get("disk_path"),
                "original_disk": vm_info.get("original_disk"),
                "snapshot_name": vm_info.get("snapshot_name"),
                "screenshots_enabled": vm_info.get("screenshots_enabled", False),
                "vnc_port": vm_info.get("vnc_port"),
                "monitor_port": vm_info.get("monitor_port"),
                "debug_port": vm_info.get("debug_port"),
                "agent_port": vm_info.get("agent_port"),
                "share_dir": vm_info.get("share_dir"),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting VM {vm_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{vm_id}/screenshot")
async def get_vm_screenshot(vm_id: int) -> Response:
    """
    Get a screenshot from a running VM.

    Returns the screenshot as a PNG image.
    """
    try:
        qemu_mgr = get_qemu_manager()
        if not qemu_mgr:
            raise HTTPException(status_code=503, detail="QEMU manager not initialized")

        # Check if VM exists and is running
        vm_info = qemu_mgr.registry.get_vm(vm_id)
        if not vm_info:
            raise HTTPException(status_code=404, detail=f"VM {vm_id} not found")

        if vm_info.get("status") != "Running":
            raise HTTPException(status_code=400, detail=f"VM {vm_id} is not running")

        if not vm_info.get("monitor_port"):
            raise HTTPException(
                status_code=400,
                detail=f"VM {vm_id} does not have monitor port enabled (screenshots require enable_vm_screenshots=true)"
            )

        # Capture screenshot
        screenshot_bytes = qemu_mgr.capture_screenshot(vm_id)
        if not screenshot_bytes:
            raise HTTPException(status_code=500, detail="Failed to capture screenshot")

        return Response(
            content=screenshot_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error capturing screenshot for VM {vm_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screenshots/all")
async def get_all_screenshots() -> Dict[str, Any]:
    """
    Get screenshots from all running VMs with screenshots enabled.

    Returns base64-encoded PNG images for each VM.
    """
    try:
        qemu_mgr = get_qemu_manager()
        if not qemu_mgr:
            return {
                "success": True,
                "count": 0,
                "data": {},
                "message": "QEMU manager not initialized"
            }

        screenshots = qemu_mgr.get_all_vm_screenshots()

        # Convert to base64 for JSON response
        result = {}
        for vm_id, png_bytes in screenshots.items():
            result[str(vm_id)] = {
                "vm_id": vm_id,
                "image_base64": base64.b64encode(png_bytes).decode('utf-8'),
                "format": "png"
            }

        return {
            "success": True,
            "count": len(result),
            "data": result
        }
    except Exception as e:
        logger.error(f"Error getting all screenshots: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screenshots/status")
async def get_screenshot_status() -> Dict[str, Any]:
    """
    Get the status of screenshot functionality.

    Returns whether screenshots are enabled and which VMs support them.
    """
    try:
        qemu_mgr = get_qemu_manager()
        config = db_manager.config

        screenshots_enabled = config.get("enable_vm_screenshots", False)
        screenshot_interval = config.get("screenshot_interval", 5)

        vms_with_screenshots = []
        if qemu_mgr and qemu_mgr.registry:
            for vm_id, vm_info in qemu_mgr.registry.vms.items():
                if not isinstance(vm_info, dict):
                    continue
                if vm_info.get("status") == "Running" and vm_info.get("screenshots_enabled"):
                    vms_with_screenshots.append({
                        "vm_id": vm_id,
                        "vnc_port": vm_info.get("vnc_port"),
                        "monitor_port": vm_info.get("monitor_port")
                    })

        return {
            "success": True,
            "data": {
                "enabled": screenshots_enabled,
                "interval": screenshot_interval,
                "vms_with_screenshots": vms_with_screenshots,
                "qemu_manager_initialized": qemu_mgr is not None
            }
        }
    except Exception as e:
        logger.error(f"Error getting screenshot status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
