"""System API endpoints"""

import logging
from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from api.database import db_manager
from api.websocket import websocket_manager
from api.executor import get_executor

router = APIRouter()
logger = logging.getLogger("fawkes.web.api.system")


@router.get("/stats")
async def get_system_stats() -> Dict[str, Any]:
    """
    Get current system statistics.

    Returns metrics like CPU usage, RAM usage, running VMs, job counts, crash counts.
    """
    try:
        stats = await websocket_manager.get_system_stats()
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        logger.error(f"Error getting system stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint.

    Returns service status and version information.
    """
    return {
        "status": "ok",
        "service": "fawkes-web-ui",
        "version": "1.0.0",
        "mode": db_manager.mode
    }


@router.get("/config")
async def get_system_config() -> Dict[str, Any]:
    """
    Get current system configuration.

    Returns the current Fawkes configuration.
    """
    try:
        return {
            "success": True,
            "data": db_manager.config
        }
    except Exception as e:
        logger.error(f"Error getting config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Controller service management

@router.post("/controller/start")
async def start_controller() -> Dict[str, Any]:
    """
    Start the Fawkes controller service for distributed fuzzing.

    The controller manages workers and distributes fuzzing jobs.
    """
    try:
        executor = get_executor()
        result = executor.start_controller(db_manager.config)

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))

        return result
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail="Job executor not available")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting controller: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/controller/stop")
async def stop_controller() -> Dict[str, Any]:
    """
    Stop the Fawkes controller service.
    """
    try:
        executor = get_executor()
        result = executor.stop_controller()

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))

        return result
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail="Job executor not available")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping controller: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/controller/status")
async def controller_status() -> Dict[str, Any]:
    """
    Get the status of the controller service.
    """
    try:
        executor = get_executor()
        is_running = executor.is_controller_running()

        return {
            "success": True,
            "data": {
                "running": is_running,
                "mode": db_manager.mode,
                "host": db_manager.config.get("controller_host", "0.0.0.0"),
                "port": db_manager.config.get("controller_port", 5000)
            }
        }
    except RuntimeError as e:
        return {
            "success": True,
            "data": {
                "running": False,
                "mode": db_manager.mode,
                "error": "Executor not initialized"
            }
        }
    except Exception as e:
        logger.error(f"Error getting controller status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executor/status")
async def executor_status() -> Dict[str, Any]:
    """
    Get the status of the job executor.

    Returns info about running jobs and the controller.
    """
    try:
        executor = get_executor()
        running_jobs = executor.get_running_jobs()

        return {
            "success": True,
            "data": {
                "running_jobs_count": len(running_jobs),
                "running_jobs": list(running_jobs.values()),
                "controller_running": executor.is_controller_running()
            }
        }
    except RuntimeError as e:
        return {
            "success": True,
            "data": {
                "running_jobs_count": 0,
                "running_jobs": [],
                "controller_running": False,
                "error": "Executor not initialized"
            }
        }
    except Exception as e:
        logger.error(f"Error getting executor status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
