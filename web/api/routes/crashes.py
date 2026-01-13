"""Crashes API endpoints"""

import logging
import os
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from api.database import db_manager
from api.models.crash import Crash, CrashFilter

router = APIRouter()
logger = logging.getLogger("fawkes.web.api.crashes")


@router.get("/", response_model=Dict[str, Any])
async def list_crashes(
    severity: Optional[List[str]] = Query(None),
    sanitizer: Optional[List[str]] = Query(None),
    unique_only: bool = Query(False),
    job_id: Optional[int] = Query(None)
):
    """
    List crashes with optional filtering.

    Args:
        severity: Filter by severity levels (HIGH, MEDIUM, LOW, CRITICAL)
        sanitizer: Filter by sanitizer type (ASan, UBSan, MSan)
        unique_only: Show only unique crashes (not duplicates)
        job_id: Filter by job ID

    Returns:
        List of crashes matching the filters
    """
    try:
        # Build filters
        filters = {}
        if severity:
            filters["severity"] = severity
        if sanitizer:
            filters["sanitizer"] = sanitizer
        if unique_only:
            filters["unique_only"] = True

        crashes = db_manager.get_crashes(job_id=job_id, filters=filters if filters else None)

        return {
            "success": True,
            "count": len(crashes),
            "data": crashes
        }
    except Exception as e:
        logger.error(f"Error listing crashes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{crash_id}", response_model=Dict[str, Any])
async def get_crash(crash_id: int):
    """
    Get details for a specific crash.

    Args:
        crash_id: Crash ID to retrieve

    Returns:
        Detailed crash information including stack trace, sanitizer report, etc.
    """
    try:
        crash = db_manager.get_crash(crash_id)
        if not crash:
            raise HTTPException(status_code=404, detail=f"Crash {crash_id} not found")

        return {
            "success": True,
            "data": crash
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting crash {crash_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{crash_id}/testcase")
async def download_testcase(crash_id: int):
    """
    Download the testcase file that triggered a crash.

    Args:
        crash_id: Crash ID

    Returns:
        Testcase file as download
    """
    try:
        crash = db_manager.get_crash(crash_id)
        if not crash:
            raise HTTPException(status_code=404, detail=f"Crash {crash_id} not found")

        testcase_path = crash.get("testcase_path") or crash.get("crash_file")
        if not testcase_path:
            raise HTTPException(status_code=404, detail="Testcase file not found for this crash")

        testcase_path = os.path.expanduser(testcase_path)
        if not os.path.exists(testcase_path):
            raise HTTPException(status_code=404, detail=f"Testcase file does not exist: {testcase_path}")

        return FileResponse(
            path=testcase_path,
            filename=os.path.basename(testcase_path),
            media_type="application/octet-stream"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading testcase for crash {crash_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{crash_id}/reproduce", response_model=Dict[str, Any])
async def reproduce_crash(crash_id: int):
    """
    Trigger replay/reproduction of a crash.

    Args:
        crash_id: Crash ID to reproduce

    Returns:
        Reproduction job information
    """
    try:
        crash = db_manager.get_crash(crash_id)
        if not crash:
            raise HTTPException(status_code=404, detail=f"Crash {crash_id} not found")

        # TODO: Integrate with replay.py to actually reproduce
        # For now, return a placeholder response

        logger.info(f"Reproduction requested for crash {crash_id}")

        return {
            "success": True,
            "message": f"Crash {crash_id} reproduction queued",
            "data": {
                "crash_id": crash_id,
                "status": "queued"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reproducing crash {crash_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{crash_id}/triage", response_model=Dict[str, Any])
async def update_crash_triage(crash_id: int, triage_data: Dict[str, Any]):
    """
    Update crash triage information (mark as fixed, add notes, etc.).

    Args:
        crash_id: Crash ID to update
        triage_data: Triage information

    Returns:
        Updated crash
    """
    try:
        crash = db_manager.get_crash(crash_id)
        if not crash:
            raise HTTPException(status_code=404, detail=f"Crash {crash_id} not found")

        # TODO: Add triage fields to database schema
        # For now, log the triage action

        logger.info(f"Triage updated for crash {crash_id}: {triage_data}")

        return {
            "success": True,
            "message": f"Crash {crash_id} triage updated",
            "data": crash
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating triage for crash {crash_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/summary", response_model=Dict[str, Any])
async def get_crash_summary():
    """
    Get crash summary statistics.

    Returns:
        Total crashes, unique crashes, crash counts by severity/sanitizer
    """
    try:
        crashes = db_manager.get_crashes()

        summary = {
            "total": len(crashes),
            "unique": len([c for c in crashes if c.get("is_unique")]),
            "by_severity": {},
            "by_sanitizer": {},
            "by_type": {}
        }

        # Count by severity
        for crash in crashes:
            severity = crash.get("severity", "UNKNOWN")
            summary["by_severity"][severity] = summary["by_severity"].get(severity, 0) + 1

        # Count by sanitizer
        for crash in crashes:
            sanitizer = crash.get("sanitizer_type", "None")
            summary["by_sanitizer"][sanitizer] = summary["by_sanitizer"].get(sanitizer, 0) + 1

        # Count by type
        for crash in crashes:
            crash_type = crash.get("crash_type", "Unknown")
            summary["by_type"][crash_type] = summary["by_type"].get(crash_type, 0) + 1

        return {
            "success": True,
            "data": summary
        }
    except Exception as e:
        logger.error(f"Error getting crash summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
