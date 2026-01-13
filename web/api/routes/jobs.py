"""Jobs API endpoints"""

import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Query
from fastapi.responses import FileResponse

from api.database import db_manager
from api.models.job import Job, JobCreate, JobUpdate
from api.executor import get_executor

router = APIRouter()
logger = logging.getLogger("fawkes.web.api.jobs")

# Base directory for job input files
JOBS_INPUT_DIR = Path.home() / ".fawkes" / "job_inputs"


def get_session_dir(session_id: str) -> Path:
    """Get the directory for a pending session's files."""
    return JOBS_INPUT_DIR / f"session_{session_id}"


def get_job_dir(job_id: int) -> Path:
    """Get the directory for a job's input files."""
    return JOBS_INPUT_DIR / f"job_{job_id}"


@router.get("/", response_model=Dict[str, Any])
async def list_jobs():
    """
    List all fuzzing jobs.

    Returns a list of all jobs with their current status.
    """
    try:
        jobs = db_manager.get_jobs()

        # Enhance with live status from executor
        try:
            executor = get_executor()
            running_jobs = executor.get_running_jobs()

            for job in jobs:
                job_id = job.get("job_id")
                if job_id in running_jobs:
                    job["live_status"] = running_jobs[job_id]
                    job["is_running"] = True
                else:
                    job["is_running"] = False
        except RuntimeError:
            # Executor not initialized yet
            pass

        return {
            "success": True,
            "count": len(jobs),
            "data": jobs
        }
    except Exception as e:
        logger.error(f"Error listing jobs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}", response_model=Dict[str, Any])
async def get_job(job_id: int):
    """
    Get details for a specific job.

    Args:
        job_id: Job ID to retrieve

    Returns:
        Job details including configuration and statistics
    """
    try:
        job = db_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        # Get crash count for this job
        crashes = db_manager.get_crashes(job_id=job_id)
        job["crash_count"] = len(crashes)
        job["unique_crash_count"] = len([c for c in crashes if c.get("is_unique")])

        # Get live status from executor
        try:
            executor = get_executor()
            live_status = executor.get_job_status(job_id)
            job["live_status"] = live_status
            job["is_running"] = live_status.get("status") == "running"
        except RuntimeError:
            job["is_running"] = False

        return {
            "success": True,
            "data": job
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_job(job: JobCreate, session_id: Optional[str] = Query(None)):
    """
    Create a new fuzzing job.

    Args:
        job: Job configuration
        session_id: Optional session ID to move uploaded files from

    Returns:
        Created job with assigned job_id
    """
    try:
        # Convert Pydantic model to dict
        job_config = job.model_dump()

        # Add job to database
        job_id = db_manager.add_job(job_config)

        # If session_id provided, move files from session dir to job dir
        if session_id:
            session_dir = get_session_dir(session_id)
            if session_dir.exists():
                job_dir = get_job_dir(job_id)
                job_dir.mkdir(parents=True, exist_ok=True)

                # Move all files from session to job directory
                for file_path in session_dir.iterdir():
                    if file_path.is_file():
                        shutil.move(str(file_path), str(job_dir / file_path.name))

                # Remove the empty session directory
                try:
                    session_dir.rmdir()
                except OSError:
                    pass  # Directory not empty or already removed

                logger.info(f"Moved session {session_id} files to job {job_id}")

                # Update input_dir in job config if using uploaded files
                fuzzer_config = job_config.get("fuzzer_config", {})
                if fuzzer_config.get("input_dir", "").startswith("~/.fawkes/job_inputs/session_"):
                    # Update the input_dir to point to the job directory
                    fuzzer_config["input_dir"] = str(job_dir)
                    db_manager.update_job_config(job_id, {"fuzzer_config": fuzzer_config})

        # Get created job
        created_job = db_manager.get_job(job_id)

        logger.info(f"Created job {job_id}: {job_config.get('name')}")

        return {
            "success": True,
            "message": f"Job {job_id} created successfully",
            "data": created_job,
            "input_dir": str(get_job_dir(job_id)) if session_id else None
        }
    except Exception as e:
        logger.error(f"Error creating job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{job_id}", response_model=Dict[str, Any])
async def update_job(job_id: int, update: JobUpdate):
    """
    Update a job's configuration or status.

    Args:
        job_id: Job ID to update
        update: Fields to update

    Returns:
        Updated job
    """
    try:
        # Check if job exists
        job = db_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        # Update status if provided
        if update.status:
            db_manager.update_job_status(job_id, update.status)

        # Get updated job
        updated_job = db_manager.get_job(job_id)

        logger.info(f"Updated job {job_id}")

        return {
            "success": True,
            "message": f"Job {job_id} updated successfully",
            "data": updated_job
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{job_id}", response_model=Dict[str, Any])
async def delete_job(job_id: int):
    """
    Delete a job and all associated data.

    Args:
        job_id: Job ID to delete

    Returns:
        Success confirmation
    """
    try:
        # Check if job exists
        job = db_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        # Stop job if running
        try:
            executor = get_executor()
            if job_id in executor.running_jobs:
                executor.stop_job(job_id)
        except RuntimeError:
            pass

        # Delete job
        db_manager.delete_job(job_id)

        logger.info(f"Deleted job {job_id}")

        return {
            "success": True,
            "message": f"Job {job_id} deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/start", response_model=Dict[str, Any])
async def start_job(job_id: int):
    """
    Start a fuzzing job.

    This actually launches the fuzzing process with VMs.

    Args:
        job_id: Job ID to start

    Returns:
        Start status including process ID
    """
    try:
        # Check if job exists
        job = db_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        # Get executor and start job
        executor = get_executor()
        result = executor.start_job(job_id)

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to start job"))

        logger.info(f"Started job {job_id} (PID: {result.get('pid')})")

        # Get updated job
        updated_job = db_manager.get_job(job_id)

        return {
            "success": True,
            "message": result.get("message", f"Job {job_id} started"),
            "pid": result.get("pid"),
            "data": updated_job
        }
    except HTTPException:
        raise
    except RuntimeError as e:
        logger.error(f"Executor not available: {e}")
        raise HTTPException(status_code=503, detail="Job executor not available")
    except Exception as e:
        logger.error(f"Error starting job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/pause", response_model=Dict[str, Any])
async def pause_job(job_id: int):
    """
    Pause a running job.

    Args:
        job_id: Job ID to pause

    Returns:
        Updated job status
    """
    try:
        # Get executor and pause job
        executor = get_executor()
        result = executor.pause_job(job_id)

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to pause job"))

        logger.info(f"Paused job {job_id}")

        # Get updated job
        job = db_manager.get_job(job_id)

        return {
            "success": True,
            "message": result.get("message", f"Job {job_id} paused"),
            "data": job
        }
    except HTTPException:
        raise
    except RuntimeError as e:
        logger.error(f"Executor not available: {e}")
        raise HTTPException(status_code=503, detail="Job executor not available")
    except Exception as e:
        logger.error(f"Error pausing job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/stop", response_model=Dict[str, Any])
async def stop_job(job_id: int):
    """
    Stop a running job.

    Args:
        job_id: Job ID to stop

    Returns:
        Updated job status
    """
    try:
        # Get executor and stop job
        executor = get_executor()
        result = executor.stop_job(job_id)

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to stop job"))

        logger.info(f"Stopped job {job_id}")

        # Get updated job
        job = db_manager.get_job(job_id)

        return {
            "success": True,
            "message": result.get("message", f"Job {job_id} stopped"),
            "data": job
        }
    except HTTPException:
        raise
    except RuntimeError as e:
        logger.error(f"Executor not available: {e}")
        raise HTTPException(status_code=503, detail="Job executor not available")
    except Exception as e:
        logger.error(f"Error stopping job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/status", response_model=Dict[str, Any])
async def get_job_live_status(job_id: int):
    """
    Get the live execution status of a job.

    Args:
        job_id: Job ID to check

    Returns:
        Live status including PID, running time, etc.
    """
    try:
        executor = get_executor()
        status = executor.get_job_status(job_id)

        return {
            "success": True,
            "data": status
        }
    except RuntimeError as e:
        logger.error(f"Executor not available: {e}")
        raise HTTPException(status_code=503, detail="Job executor not available")
    except Exception as e:
        logger.error(f"Error getting job status {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/running/list", response_model=Dict[str, Any])
async def list_running_jobs():
    """
    List all currently running jobs.

    Returns:
        List of running jobs with process info
    """
    try:
        executor = get_executor()
        running = executor.get_running_jobs()

        return {
            "success": True,
            "count": len(running),
            "data": list(running.values())
        }
    except RuntimeError as e:
        logger.error(f"Executor not available: {e}")
        raise HTTPException(status_code=503, detail="Job executor not available")
    except Exception as e:
        logger.error(f"Error listing running jobs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Job Input Files (Seed Corpus) Endpoints
# ============================================================================


def _get_target_dir(session_id: Optional[str], job_id: Optional[int]) -> Path:
    """Get the target directory for file operations."""
    if job_id is not None:
        return get_job_dir(job_id)
    elif session_id:
        return get_session_dir(session_id)
    else:
        # Legacy: use root directory
        return JOBS_INPUT_DIR


@router.post("/inputs/session", response_model=Dict[str, Any])
async def create_session():
    """
    Create a new upload session for job creation.

    Returns a unique session ID that can be used to upload files
    before the job is created.

    Returns:
        Session ID for file uploads
    """
    try:
        session_id = str(uuid.uuid4())[:8]
        session_dir = get_session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Created upload session: {session_id}")

        return {
            "success": True,
            "session_id": session_id,
            "directory": str(session_dir)
        }
    except Exception as e:
        logger.error(f"Error creating session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/inputs/session/{session_id}", response_model=Dict[str, Any])
async def delete_session(session_id: str):
    """
    Delete an upload session and all its files.

    Used when user cancels job creation.

    Args:
        session_id: Session ID to delete

    Returns:
        Deletion status
    """
    try:
        session_dir = get_session_dir(session_id)

        if session_dir.exists():
            shutil.rmtree(str(session_dir))
            logger.info(f"Deleted session {session_id}")
            return {
                "success": True,
                "message": f"Session {session_id} deleted"
            }
        else:
            return {
                "success": True,
                "message": f"Session {session_id} not found (already deleted)"
            }
    except Exception as e:
        logger.error(f"Error deleting session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inputs/upload", response_model=Dict[str, Any])
async def upload_input_file(
    file: UploadFile = File(...),
    session_id: Optional[str] = Query(None),
    job_id: Optional[int] = Query(None)
):
    """
    Upload a seed file for fuzzing.

    Files are stored in session or job-specific directories.

    Args:
        file: The file to upload
        session_id: Optional session ID (for pending job creation)
        job_id: Optional job ID (for existing jobs)

    Returns:
        Upload status with file path
    """
    try:
        # Determine target directory
        target_dir = _get_target_dir(session_id, job_id)
        target_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize filename
        safe_filename = Path(file.filename).name
        if not safe_filename or safe_filename.startswith('.'):
            raise HTTPException(status_code=400, detail="Invalid filename")

        # Save file
        file_path = target_dir / safe_filename

        # Handle duplicate filenames by adding suffix
        if file_path.exists():
            base = file_path.stem
            suffix = file_path.suffix
            counter = 1
            while file_path.exists():
                file_path = target_dir / f"{base}_{counter}{suffix}"
                counter += 1

        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        logger.info(f"Uploaded input file: {file_path}")

        return {
            "success": True,
            "message": f"File uploaded successfully",
            "data": {
                "filename": file_path.name,
                "path": str(file_path),
                "size": len(content),
                "original_filename": file.filename,
                "session_id": session_id,
                "job_id": job_id
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading input file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inputs/upload-multiple", response_model=Dict[str, Any])
async def upload_multiple_input_files(
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Query(None),
    job_id: Optional[int] = Query(None)
):
    """
    Upload multiple seed files for fuzzing.

    Args:
        files: List of files to upload
        session_id: Optional session ID (for pending job creation)
        job_id: Optional job ID (for existing jobs)

    Returns:
        Upload status with file paths
    """
    try:
        # Determine target directory
        target_dir = _get_target_dir(session_id, job_id)
        target_dir.mkdir(parents=True, exist_ok=True)

        uploaded = []
        errors = []

        for file in files:
            try:
                # Sanitize filename
                safe_filename = Path(file.filename).name
                if not safe_filename or safe_filename.startswith('.'):
                    errors.append({"filename": file.filename, "error": "Invalid filename"})
                    continue

                # Save file
                file_path = target_dir / safe_filename

                # Handle duplicate filenames
                if file_path.exists():
                    base = file_path.stem
                    suffix = file_path.suffix
                    counter = 1
                    while file_path.exists():
                        file_path = target_dir / f"{base}_{counter}{suffix}"
                        counter += 1

                with open(file_path, "wb") as f:
                    content = await file.read()
                    f.write(content)

                uploaded.append({
                    "filename": file_path.name,
                    "path": str(file_path),
                    "size": len(content),
                    "original_filename": file.filename
                })

            except Exception as e:
                errors.append({"filename": file.filename, "error": str(e)})

        logger.info(f"Uploaded {len(uploaded)} input files, {len(errors)} errors")

        return {
            "success": len(errors) == 0,
            "message": f"Uploaded {len(uploaded)} files" + (f", {len(errors)} failed" if errors else ""),
            "data": {
                "uploaded": uploaded,
                "errors": errors,
                "session_id": session_id,
                "job_id": job_id
            }
        }
    except Exception as e:
        logger.error(f"Error uploading input files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inputs/", response_model=Dict[str, Any])
async def list_input_files(
    session_id: Optional[str] = Query(None),
    job_id: Optional[int] = Query(None)
):
    """
    List all uploaded input files.

    Args:
        session_id: Optional session ID (for pending job creation)
        job_id: Optional job ID (for existing jobs)

    Returns:
        List of input files with metadata
    """
    try:
        target_dir = _get_target_dir(session_id, job_id)
        files = []

        if target_dir.exists():
            for file_path in target_dir.iterdir():
                if file_path.is_file():
                    stat = file_path.stat()
                    files.append({
                        "filename": file_path.name,
                        "path": str(file_path),
                        "size": stat.st_size,
                        "modified": stat.st_mtime
                    })

        # Sort by modification time (newest first)
        files.sort(key=lambda x: x["modified"], reverse=True)

        return {
            "success": True,
            "count": len(files),
            "directory": str(target_dir),
            "session_id": session_id,
            "job_id": job_id,
            "data": files
        }
    except Exception as e:
        logger.error(f"Error listing input files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inputs/{filename}")
async def download_input_file(
    filename: str,
    session_id: Optional[str] = Query(None),
    job_id: Optional[int] = Query(None)
):
    """
    Download an input file.

    Args:
        filename: Name of the file to download
        session_id: Optional session ID (for pending job creation)
        job_id: Optional job ID (for existing jobs)

    Returns:
        The file content
    """
    try:
        target_dir = _get_target_dir(session_id, job_id)

        # Sanitize filename
        safe_filename = Path(filename).name
        file_path = target_dir / safe_filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {filename}")

        return FileResponse(
            path=str(file_path),
            filename=safe_filename,
            media_type="application/octet-stream"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading input file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/inputs/{filename}", response_model=Dict[str, Any])
async def delete_input_file(
    filename: str,
    session_id: Optional[str] = Query(None),
    job_id: Optional[int] = Query(None)
):
    """
    Delete an input file.

    Args:
        filename: Name of the file to delete
        session_id: Optional session ID (for pending job creation)
        job_id: Optional job ID (for existing jobs)

    Returns:
        Deletion status
    """
    try:
        target_dir = _get_target_dir(session_id, job_id)

        # Sanitize filename
        safe_filename = Path(filename).name
        file_path = target_dir / safe_filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {filename}")

        file_path.unlink()
        logger.info(f"Deleted input file: {file_path}")

        return {
            "success": True,
            "message": f"File {filename} deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting input file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/inputs/clear", response_model=Dict[str, Any])
async def clear_all_input_files(
    session_id: Optional[str] = Query(None),
    job_id: Optional[int] = Query(None)
):
    """
    Delete all input files in a session or job directory.

    Args:
        session_id: Optional session ID (for pending job creation)
        job_id: Optional job ID (for existing jobs)

    Returns:
        Deletion status with count of files removed
    """
    try:
        target_dir = _get_target_dir(session_id, job_id)
        count = 0

        if target_dir.exists():
            for file_path in target_dir.iterdir():
                if file_path.is_file():
                    file_path.unlink()
                    count += 1

        logger.info(f"Cleared {count} input files from {target_dir}")

        return {
            "success": True,
            "message": f"Deleted {count} files",
            "count": count
        }
    except Exception as e:
        logger.error(f"Error clearing input files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
