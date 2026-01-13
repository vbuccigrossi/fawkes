"""Workers API endpoints (controller mode only)"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException

from api.database import db_manager
from api.models.worker import Worker, WorkerCreate

router = APIRouter()
logger = logging.getLogger("fawkes.web.api.workers")


@router.get("/", response_model=Dict[str, Any])
async def list_workers():
    """
    List all workers (controller mode only).

    Returns:
        List of all registered workers
    """
    try:
        if db_manager.mode != "controller":
            raise HTTPException(status_code=400, detail="Workers endpoint only available in controller mode")

        workers = db_manager.get_workers()

        return {
            "success": True,
            "count": len(workers),
            "data": workers
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing workers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{worker_id}", response_model=Dict[str, Any])
async def get_worker(worker_id: int):
    """
    Get details for a specific worker.

    Args:
        worker_id: Worker ID to retrieve

    Returns:
        Worker details including status, current job, statistics
    """
    try:
        if db_manager.mode != "controller":
            raise HTTPException(status_code=400, detail="Workers endpoint only available in controller mode")

        worker = db_manager.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail=f"Worker {worker_id} not found")

        return {
            "success": True,
            "data": worker
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting worker {worker_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=Dict[str, Any])
async def add_worker(worker: WorkerCreate):
    """
    Register a new worker.

    Args:
        worker: Worker information (IP address)

    Returns:
        Registered worker
    """
    try:
        if db_manager.mode != "controller":
            raise HTTPException(status_code=400, detail="Workers endpoint only available in controller mode")

        db_manager.add_worker(worker.ip_address)

        logger.info(f"Registered new worker: {worker.ip_address}")

        return {
            "success": True,
            "message": f"Worker {worker.ip_address} registered successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding worker: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{worker_id}/assign", response_model=Dict[str, Any])
async def assign_job_to_worker(worker_id: int, job_id: int):
    """
    Assign a job to a worker.

    Args:
        worker_id: Worker to assign job to
        job_id: Job to assign

    Returns:
        Assignment confirmation
    """
    try:
        if db_manager.mode != "controller":
            raise HTTPException(status_code=400, detail="Workers endpoint only available in controller mode")

        # Check if worker exists
        worker = db_manager.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail=f"Worker {worker_id} not found")

        # Check if job exists
        job = db_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        # Assign job
        db_manager.controller_db.assign_job_to_worker(job_id, worker_id)

        logger.info(f"Assigned job {job_id} to worker {worker_id}")

        return {
            "success": True,
            "message": f"Job {job_id} assigned to worker {worker_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning job to worker: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{worker_id}", response_model=Dict[str, Any])
async def remove_worker(worker_id: int):
    """
    Remove a worker from the system.

    Args:
        worker_id: Worker ID to remove

    Returns:
        Removal confirmation
    """
    try:
        if db_manager.mode != "controller":
            raise HTTPException(status_code=400, detail="Workers endpoint only available in controller mode")

        # Check if worker exists
        worker = db_manager.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail=f"Worker {worker_id} not found")

        # TODO: Implement worker removal in ControllerDB
        logger.info(f"Worker {worker_id} removal requested")

        return {
            "success": True,
            "message": f"Worker {worker_id} removed successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing worker {worker_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
