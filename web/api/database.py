"""
Database Access Layer for Fawkes Web UI

Provides unified interface to FawkesDB (local mode) and ControllerDB (controller mode).
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add parent directory to import Fawkes modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db.db import FawkesDB
from db.controller_db import ControllerDB
from config import FawkesConfig

logger = logging.getLogger("fawkes.web.database")


class DatabaseManager:
    """
    Unified database manager that handles both local and controller modes.
    """

    def __init__(self):
        self.local_db: Optional[FawkesDB] = None
        self.controller_db: Optional[ControllerDB] = None
        self.mode: str = "local"  # "local" or "controller"
        self.config: Dict[str, Any] = {}

    def initialize(self, mode: str = None, config_path: str = "~/.fawkes/config.json"):
        """Initialize database connections based on mode."""
        try:
            # Load configuration
            config_path = os.path.expanduser(config_path)
            if os.path.exists(config_path):
                import json
                with open(config_path, 'r') as f:
                    self.config = json.load(f)
            else:
                logger.warning(f"Config not found at {config_path}, using defaults")
                self.config = {}

            # Determine mode
            if mode:
                self.mode = mode
            else:
                self.mode = self.config.get("fuzzing_mode", "local")

            logger.info(f"Initializing database manager in {self.mode} mode")

            # Initialize appropriate database
            if self.mode in ("local", "worker"):
                # Worker mode uses local database (will sync with controller)
                db_path = os.path.expanduser(self.config.get("db_path", "~/.fawkes/fawkes.db"))
                self.local_db = FawkesDB(db_path)
                logger.info(f"Connected to local database: {db_path}")
            elif self.mode == "controller":
                db_path = os.path.expanduser(self.config.get("controller_db_path", "~/.fawkes/controller.db"))
                self.controller_db = ControllerDB(db_path)
                logger.info(f"Connected to controller database: {db_path}")
            else:
                logger.warning(f"Unknown mode '{self.mode}', defaulting to local")
                self.mode = "local"
                db_path = os.path.expanduser(self.config.get("db_path", "~/.fawkes/fawkes.db"))
                self.local_db = FawkesDB(db_path)
                logger.info(f"Connected to local database: {db_path}")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}", exc_info=True)
            raise

    def close(self):
        """Close database connections."""
        if self.local_db:
            self.local_db.close()
        if self.controller_db:
            self.controller_db._conn.close() if hasattr(self.controller_db, '_conn') else None

    # Job operations
    def get_jobs(self) -> List[Dict[str, Any]]:
        """Get all jobs."""
        if self.mode in ("local", "worker"):
            # Query jobs table directly
            cursor = self.local_db._conn.cursor()
            cursor.execute("""
                SELECT job_id, name, disk, snapshot, status, fuzzer_type, fuzzer_config,
                       total_testcases, generated_testcases, create_time, vm_count
                FROM jobs
            """)
            import json
            return [{
                "job_id": row[0],
                "name": row[1],
                "disk": row[2],
                "snapshot": row[3],
                "status": row[4],
                "fuzzer_type": row[5],
                "fuzzer_config": json.loads(row[6]) if row[6] else None,
                "total_testcases": row[7] or 0,
                "generated_testcases": row[8] or 0,
                "create_time": row[9],
                "vm_count": row[10] or 0
            } for row in cursor.fetchall()]
        else:
            cursor = self.controller_db.conn.cursor()
            cursor.execute("""
                SELECT job_id, config, status, start_time, end_time
                FROM jobs
            """)
            import json
            return [{
                "job_id": row[0],
                "config": json.loads(row[1]) if row[1] else {},
                "status": row[2],
                "start_time": row[3],
                "end_time": row[4]
            } for row in cursor.fetchall()]

    def get_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Get job by ID."""
        if self.mode in ("local", "worker"):
            cursor = self.local_db._conn.cursor()
            cursor.execute("""
                SELECT job_id, name, disk, snapshot, status, fuzzer_type, fuzzer_config,
                       total_testcases, generated_testcases, create_time, vm_count
                FROM jobs WHERE job_id = ?
            """, (job_id,))
            row = cursor.fetchone()
            if not row:
                return None
            import json
            return {
                "job_id": row[0],
                "name": row[1],
                "disk": row[2],
                "snapshot": row[3],
                "status": row[4],
                "fuzzer_type": row[5],
                "fuzzer_config": json.loads(row[6]) if row[6] else None,
                "total_testcases": row[7] or 0,
                "generated_testcases": row[8] or 0,
                "create_time": row[9],
                "vm_count": row[10] or 0
            }
        else:
            cursor = self.controller_db.conn.cursor()
            cursor.execute("""
                SELECT job_id, config, status, start_time, end_time
                FROM jobs WHERE job_id = ?
            """, (job_id,))
            row = cursor.fetchone()
            if not row:
                return None
            import json
            return {
                "job_id": row[0],
                "config": json.loads(row[1]) if row[1] else {},
                "status": row[2],
                "start_time": row[3],
                "end_time": row[4]
            }

    def add_job(self, job_config: Dict[str, Any]) -> int:
        """Add a new job."""
        if self.mode in ("local", "worker"):
            return self.local_db.add_job(
                name=job_config.get("name", "Unnamed Job"),
                input_dir=job_config.get("input_dir", "/tmp"),
                fuzzer_type=job_config.get("fuzzer_type"),
                fuzzer_config=job_config.get("fuzzer_config")
            )
        else:
            return self.controller_db.add_job(job_config)

    def update_job_status(self, job_id: int, status: str):
        """Update job status."""
        if self.mode in ("local", "worker"):
            self.local_db.update_job_status(job_id, status)
        else:
            cursor = self.controller_db.conn.cursor()
            cursor.execute("UPDATE jobs SET status = ? WHERE job_id = ?", (status, job_id))
            self.controller_db.conn.commit()

    def delete_job(self, job_id: int):
        """Delete a job."""
        if self.mode in ("local", "worker"):
            self.local_db.delete_job(job_id)
        else:
            cursor = self.controller_db.conn.cursor()
            cursor.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            self.controller_db.conn.commit()

    # Crash operations
    def get_crashes(self, job_id: Optional[int] = None, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Get crashes with optional filtering."""
        if self.mode in ("local", "worker"):
            # Query crashes table directly
            cursor = self.local_db._conn.cursor()
            if job_id:
                cursor.execute("""
                    SELECT crash_id, job_id, testcase_path, crash_type, details, signature,
                           exploitability, crash_file, timestamp, duplicate_count, stack_hash,
                           sanitizer_type, sanitizer_report, severity, is_unique
                    FROM crashes WHERE job_id = ?
                """, (job_id,))
            else:
                cursor.execute("""
                    SELECT crash_id, job_id, testcase_path, crash_type, details, signature,
                           exploitability, crash_file, timestamp, duplicate_count, stack_hash,
                           sanitizer_type, sanitizer_report, severity, is_unique
                    FROM crashes
                """)
            crashes = [{
                "crash_id": row[0],
                "job_id": row[1],
                "testcase_path": row[2],
                "crash_type": row[3],
                "details": row[4],
                "signature": row[5],
                "exploitability": row[6],
                "crash_file": row[7],
                "timestamp": row[8],
                "duplicate_count": row[9] or 0,
                "stack_hash": row[10],
                "sanitizer_type": row[11],
                "sanitizer_report": row[12],
                "severity": row[13],
                "is_unique": bool(row[14]) if row[14] is not None else True
            } for row in cursor.fetchall()]

            # Apply filters
            if filters:
                if filters.get("severity"):
                    crashes = [c for c in crashes if c.get("severity") in filters["severity"]]
                if filters.get("sanitizer"):
                    crashes = [c for c in crashes if c.get("sanitizer_type") in filters["sanitizer"]]
                if filters.get("unique_only"):
                    crashes = [c for c in crashes if c.get("is_unique")]

            return crashes
        else:
            return self.controller_db.get_crashes(job_id)

    def get_crash(self, crash_id: int) -> Optional[Dict[str, Any]]:
        """Get crash by ID."""
        if self.mode in ("local", "worker"):
            cursor = self.local_db._conn.cursor()
            cursor.execute("""
                SELECT crash_id, job_id, testcase_path, crash_type, details, signature,
                       exploitability, crash_file, timestamp, duplicate_count, stack_hash,
                       sanitizer_type, sanitizer_report, severity, is_unique
                FROM crashes WHERE crash_id = ?
            """, (crash_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "crash_id": row[0],
                "job_id": row[1],
                "testcase_path": row[2],
                "crash_type": row[3],
                "details": row[4],
                "signature": row[5],
                "exploitability": row[6],
                "crash_file": row[7],
                "timestamp": row[8],
                "duplicate_count": row[9] or 0,
                "stack_hash": row[10],
                "sanitizer_type": row[11],
                "sanitizer_report": row[12],
                "severity": row[13],
                "is_unique": bool(row[14]) if row[14] is not None else True
            }
        else:
            crashes = self.controller_db.get_crashes()
            for crash in crashes:
                if crash["crash_id"] == crash_id:
                    return crash
            return None

    def add_crash(self, job_id: int, crash_data: Dict[str, Any]) -> int:
        """Add a new crash."""
        if self.mode in ("local", "worker"):
            return self.local_db.add_crash(
                job_id=job_id,
                testcase_path=crash_data.get("testcase_path"),
                crash_type=crash_data.get("crash_type"),
                details=crash_data.get("details"),
                signature=crash_data.get("signature"),
                exploitability=crash_data.get("exploitability"),
                crash_file=crash_data.get("crash_file")
            )
        else:
            self.controller_db.add_crash(job_id, worker_id=None, crash=crash_data)
            return crash_data.get("crash_id", 0)

    # Worker operations (controller mode only)
    def get_workers(self) -> List[Dict[str, Any]]:
        """Get all workers (controller mode only)."""
        if self.mode == "controller":
            return self.controller_db.get_workers()
        return []

    def get_worker(self, worker_id: int) -> Optional[Dict[str, Any]]:
        """Get worker by ID (controller mode only)."""
        if self.mode == "controller":
            workers = self.controller_db.get_workers()
            for worker in workers:
                if worker["worker_id"] == worker_id:
                    return worker
        return None

    def add_worker(self, ip_address: str):
        """Add a new worker (controller mode only)."""
        if self.mode == "controller":
            self.controller_db.add_worker(ip_address)

    def update_worker_status(self, worker_id: int, status: str):
        """Update worker status (controller mode only)."""
        if self.mode == "controller":
            self.controller_db.update_worker_status(worker_id, status)

    # Statistics
    def get_stats(self) -> Dict[str, Any]:
        """Get overall statistics."""
        stats = {
            "total_jobs": 0,
            "running_jobs": 0,
            "total_crashes": 0,
            "unique_crashes": 0,
            "total_testcases": 0,
            "workers_online": 0,
            "workers_total": 0
        }

        try:
            jobs = self.get_jobs()
            stats["total_jobs"] = len(jobs)
            stats["running_jobs"] = len([j for j in jobs if j.get("status") == "running"])

            crashes = self.get_crashes()
            stats["total_crashes"] = len(crashes)
            if self.mode in ("local", "worker"):
                stats["unique_crashes"] = len([c for c in crashes if c.get("is_unique")])
            else:
                stats["unique_crashes"] = stats["total_crashes"]  # TODO: Implement dedup for controller mode

            if self.mode in ("local", "worker"):
                # Get testcase count
                cursor = self.local_db._conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM testcases")
                stats["total_testcases"] = cursor.fetchone()[0]

            if self.mode == "controller":
                workers = self.get_workers()
                stats["workers_total"] = len(workers)
                stats["workers_online"] = len([w for w in workers if w.get("status") == "online"])

        except Exception as e:
            logger.error(f"Error getting stats: {e}", exc_info=True)

        return stats


# Global database manager instance
db_manager = DatabaseManager()
