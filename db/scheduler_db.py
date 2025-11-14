"""
Enhanced Scheduler Database

Provides advanced job scheduling, worker management, and resource tracking
for distributed fuzzing operations.
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger("fawkes.scheduler")


class SchedulerDB:
    """Enhanced database for distributed job scheduling"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.create_tables()
        self.migrate_schema()

    def create_tables(self):
        """Create all scheduler tables"""
        cursor = self.conn.cursor()

        # Enhanced jobs table
        cursor.execute('''CREATE TABLE IF NOT EXISTS jobs (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            config TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            priority INTEGER DEFAULT 50,
            deadline INTEGER,
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            dependencies TEXT,
            resource_requirements TEXT,
            assigned_worker_id INTEGER,
            created_time INTEGER,
            start_time INTEGER,
            end_time INTEGER,
            error_message TEXT,
            FOREIGN KEY (assigned_worker_id) REFERENCES workers(worker_id)
        )''')

        # Workers table with capabilities
        cursor.execute('''CREATE TABLE IF NOT EXISTS workers (
            worker_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT UNIQUE NOT NULL,
            hostname TEXT,
            status TEXT DEFAULT 'offline',
            capabilities TEXT,
            current_load TEXT,
            tags TEXT,
            heartbeat_interval INTEGER DEFAULT 30,
            last_heartbeat INTEGER,
            registered_time INTEGER,
            UNIQUE(ip_address)
        )''')

        # Job queue
        cursor.execute('''CREATE TABLE IF NOT EXISTS job_queue (
            queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER UNIQUE NOT NULL,
            priority INTEGER DEFAULT 50,
            queued_time INTEGER NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        )''')

        # Job assignments
        cursor.execute('''CREATE TABLE IF NOT EXISTS job_assignments (
            assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            worker_id INTEGER NOT NULL,
            assigned_time INTEGER NOT NULL,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (job_id) REFERENCES jobs(job_id),
            FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
        )''')

        # Job execution history
        cursor.execute('''CREATE TABLE IF NOT EXISTS job_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            worker_id INTEGER,
            start_time INTEGER,
            end_time INTEGER,
            status TEXT,
            error_message TEXT,
            stats TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id),
            FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
        )''')

        # Crashes table
        cursor.execute('''CREATE TABLE IF NOT EXISTS crashes (
            crash_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            worker_id INTEGER,
            testcase_path TEXT,
            crash_type TEXT,
            details TEXT,
            signature TEXT,
            exploitability TEXT,
            crash_file TEXT,
            timestamp INTEGER,
            duplicate_count INTEGER DEFAULT 0,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id),
            FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
        )''')

        # Create indices for performance
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_jobs_status
                         ON jobs(status)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_jobs_priority
                         ON jobs(priority DESC, created_time ASC)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_workers_status
                         ON workers(status)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_queue_priority
                         ON job_queue(priority DESC, queued_time ASC)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_crashes_job
                         ON crashes(job_id)''')

        self.conn.commit()
        logger.debug("Scheduler tables created/verified")

    def migrate_schema(self):
        """Migrate existing schema to add new columns if needed"""
        cursor = self.conn.cursor()

        # Check jobs table columns
        cursor.execute("PRAGMA table_info(jobs)")
        job_columns = {col[1] for col in cursor.fetchall()}

        migrations = []
        if "priority" not in job_columns:
            migrations.append("ALTER TABLE jobs ADD COLUMN priority INTEGER DEFAULT 50")
        if "deadline" not in job_columns:
            migrations.append("ALTER TABLE jobs ADD COLUMN deadline INTEGER")
        if "retry_count" not in job_columns:
            migrations.append("ALTER TABLE jobs ADD COLUMN retry_count INTEGER DEFAULT 0")
        if "max_retries" not in job_columns:
            migrations.append("ALTER TABLE jobs ADD COLUMN max_retries INTEGER DEFAULT 3")
        if "dependencies" not in job_columns:
            migrations.append("ALTER TABLE jobs ADD COLUMN dependencies TEXT")
        if "resource_requirements" not in job_columns:
            migrations.append("ALTER TABLE jobs ADD COLUMN resource_requirements TEXT")
        if "assigned_worker_id" not in job_columns:
            migrations.append("ALTER TABLE jobs ADD COLUMN assigned_worker_id INTEGER")
        if "created_time" not in job_columns:
            migrations.append("ALTER TABLE jobs ADD COLUMN created_time INTEGER")
        if "error_message" not in job_columns:
            migrations.append("ALTER TABLE jobs ADD COLUMN error_message TEXT")

        # Check workers table columns
        cursor.execute("PRAGMA table_info(workers)")
        worker_columns = {col[1] for col in cursor.fetchall()}

        if "hostname" not in worker_columns:
            migrations.append("ALTER TABLE workers ADD COLUMN hostname TEXT")
        if "capabilities" not in worker_columns:
            migrations.append("ALTER TABLE workers ADD COLUMN capabilities TEXT")
        if "current_load" not in worker_columns:
            migrations.append("ALTER TABLE workers ADD COLUMN current_load TEXT")
        if "tags" not in worker_columns:
            migrations.append("ALTER TABLE workers ADD COLUMN tags TEXT")
        if "heartbeat_interval" not in worker_columns:
            migrations.append("ALTER TABLE workers ADD COLUMN heartbeat_interval INTEGER DEFAULT 30")
        if "last_heartbeat" not in worker_columns:
            migrations.append("ALTER TABLE workers ADD COLUMN last_heartbeat INTEGER")
        if "registered_time" not in worker_columns:
            migrations.append("ALTER TABLE workers ADD COLUMN registered_time INTEGER")

        if migrations:
            logger.info(f"Running {len(migrations)} schema migrations")
            for migration in migrations:
                cursor.execute(migration)
            self.conn.commit()

    # ============================================================================
    # JOB MANAGEMENT
    # ============================================================================

    def add_job(self, name: str, config: Dict[str, Any],
                priority: int = 50, deadline: Optional[int] = None,
                dependencies: Optional[List[int]] = None,
                resource_requirements: Optional[Dict[str, Any]] = None) -> int:
        """
        Add a new job to the scheduler

        Args:
            name: Job name/description
            config: Job configuration dict
            priority: Priority (0-100, higher = more urgent)
            deadline: Unix timestamp deadline
            dependencies: List of job_ids that must complete first
            resource_requirements: Dict with cpu, ram, vms requirements

        Returns:
            job_id
        """
        cursor = self.conn.cursor()
        created_time = int(datetime.now().timestamp())

        cursor.execute('''INSERT INTO jobs (
            name, config, status, priority, deadline, dependencies,
            resource_requirements, created_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (
            name,
            json.dumps(config),
            'pending',
            priority,
            deadline,
            json.dumps(dependencies) if dependencies else None,
            json.dumps(resource_requirements) if resource_requirements else None,
            created_time
        ))

        job_id = cursor.lastrowid

        # Add to queue if no dependencies or all dependencies satisfied
        if not dependencies or self._dependencies_satisfied(dependencies):
            cursor.execute('''INSERT INTO job_queue (job_id, priority, queued_time)
                             VALUES (?, ?, ?)''', (job_id, priority, created_time))

        self.conn.commit()
        logger.info(f"Added job {job_id}: {name} (priority={priority})")
        return job_id

    def _dependencies_satisfied(self, dependencies: List[int]) -> bool:
        """Check if all dependency jobs are completed"""
        cursor = self.conn.cursor()
        cursor.execute(f'''SELECT COUNT(*) FROM jobs
                          WHERE job_id IN ({','.join('?' * len(dependencies))})
                          AND status = 'completed' ''', dependencies)
        completed_count = cursor.fetchone()[0]
        return completed_count == len(dependencies)

    def update_job_status(self, job_id: int, status: str, error_message: Optional[str] = None):
        """Update job status"""
        cursor = self.conn.cursor()

        updates = {"status": status}
        if status == "running" and not self._get_job_start_time(job_id):
            updates["start_time"] = int(datetime.now().timestamp())
        elif status in ("completed", "failed", "cancelled"):
            updates["end_time"] = int(datetime.now().timestamp())
            if error_message:
                updates["error_message"] = error_message

            # Remove from queue if present
            cursor.execute("DELETE FROM job_queue WHERE job_id = ?", (job_id,))

            # Add to history
            job_data = self.get_job(job_id)
            if job_data:
                cursor.execute('''INSERT INTO job_history (
                    job_id, worker_id, start_time, end_time, status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?)''', (
                    job_id,
                    job_data.get("assigned_worker_id"),
                    job_data.get("start_time"),
                    updates.get("end_time"),
                    status,
                    error_message
                ))

        # Update status FIRST
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [job_id]
        cursor.execute(f"UPDATE jobs SET {set_clause} WHERE job_id = ?", values)
        self.conn.commit()

        # THEN check for dependent jobs (after status is committed)
        if status in ("completed", "failed", "cancelled"):
            self._check_dependent_jobs(job_id)

        logger.debug(f"Job {job_id} status updated to {status}")

    def _get_job_start_time(self, job_id: int) -> Optional[int]:
        """Get job start time"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT start_time FROM jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def _check_dependent_jobs(self, completed_job_id: int):
        """Check if any jobs were waiting for this job to complete"""
        cursor = self.conn.cursor()
        cursor.execute('''SELECT job_id, dependencies FROM jobs
                         WHERE status = 'pending' AND dependencies IS NOT NULL''')

        for row in cursor.fetchall():
            job_id, deps_json = row
            dependencies = json.loads(deps_json)
            if completed_job_id in dependencies and self._dependencies_satisfied(dependencies):
                # Add to queue now that dependencies are satisfied
                job_data = self.get_job(job_id)
                if job_data:
                    cursor.execute('''INSERT OR IGNORE INTO job_queue (job_id, priority, queued_time)
                                     VALUES (?, ?, ?)''', (
                        job_id,
                        job_data.get("priority", 50),
                        int(datetime.now().timestamp())
                    ))
                    logger.info(f"Job {job_id} now queued (dependencies satisfied)")

        self.conn.commit()

    def assign_job_to_worker(self, job_id: int, worker_id: int):
        """Assign a job to a worker"""
        cursor = self.conn.cursor()
        assigned_time = int(datetime.now().timestamp())

        cursor.execute('''INSERT INTO job_assignments (job_id, worker_id, assigned_time, status)
                         VALUES (?, ?, ?, 'active')''', (job_id, worker_id, assigned_time))
        cursor.execute('''UPDATE jobs SET assigned_worker_id = ?, status = 'assigned'
                         WHERE job_id = ?''', (worker_id, job_id))
        cursor.execute("DELETE FROM job_queue WHERE job_id = ?", (job_id,))

        self.conn.commit()
        logger.info(f"Job {job_id} assigned to worker {worker_id}")

    def increment_job_retry(self, job_id: int) -> bool:
        """
        Increment job retry count and re-queue if under max retries

        Returns:
            True if re-queued, False if max retries exceeded
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT retry_count, max_retries, priority FROM jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        if not row:
            return False

        retry_count, max_retries, priority = row
        new_retry_count = retry_count + 1

        if new_retry_count >= max_retries:
            self.update_job_status(job_id, "failed", f"Max retries ({max_retries}) exceeded")
            return False

        cursor.execute("UPDATE jobs SET retry_count = ?, status = 'pending' WHERE job_id = ?",
                      (new_retry_count, job_id))
        cursor.execute('''INSERT INTO job_queue (job_id, priority, queued_time)
                         VALUES (?, ?, ?)''', (job_id, priority, int(datetime.now().timestamp())))
        self.conn.commit()
        logger.info(f"Job {job_id} re-queued (retry {new_retry_count}/{max_retries})")
        return True

    def get_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Get job details"""
        cursor = self.conn.cursor()
        cursor.execute('''SELECT job_id, name, config, status, priority, deadline, retry_count,
                         max_retries, dependencies, resource_requirements, assigned_worker_id,
                         created_time, start_time, end_time, error_message
                         FROM jobs WHERE job_id = ?''', (job_id,))
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "job_id": row[0],
            "name": row[1],
            "config": json.loads(row[2]),
            "status": row[3],
            "priority": row[4],
            "deadline": row[5],
            "retry_count": row[6],
            "max_retries": row[7],
            "dependencies": json.loads(row[8]) if row[8] else None,
            "resource_requirements": json.loads(row[9]) if row[9] else None,
            "assigned_worker_id": row[10],
            "created_time": row[11],
            "start_time": row[12],
            "end_time": row[13],
            "error_message": row[14]
        }

    def get_next_job_from_queue(self) -> Optional[Dict[str, Any]]:
        """Get highest priority job from queue (FIFO within priority)"""
        cursor = self.conn.cursor()
        cursor.execute('''SELECT j.job_id, j.name, j.config, j.priority, j.resource_requirements
                         FROM job_queue q
                         JOIN jobs j ON q.job_id = j.job_id
                         ORDER BY q.priority DESC, q.queued_time ASC
                         LIMIT 1''')
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "job_id": row[0],
            "name": row[1],
            "config": json.loads(row[2]),
            "priority": row[3],
            "resource_requirements": json.loads(row[4]) if row[4] else None
        }

    # ============================================================================
    # WORKER MANAGEMENT
    # ============================================================================

    def register_worker(self, ip_address: str, hostname: Optional[str] = None,
                       capabilities: Optional[Dict[str, Any]] = None,
                       tags: Optional[List[str]] = None) -> int:
        """
        Register a new worker or update existing

        Args:
            ip_address: Worker IP address
            hostname: Worker hostname
            capabilities: Dict with cpu_cores, ram_gb, max_vms
            tags: List of tags for worker classification

        Returns:
            worker_id
        """
        cursor = self.conn.cursor()
        registered_time = int(datetime.now().timestamp())

        # Check if worker exists
        cursor.execute("SELECT worker_id FROM workers WHERE ip_address = ?", (ip_address,))
        existing = cursor.fetchone()

        if existing:
            worker_id = existing[0]
            cursor.execute('''UPDATE workers SET hostname = ?, capabilities = ?, tags = ?,
                             status = 'online', last_heartbeat = ?, registered_time = ?
                             WHERE worker_id = ?''', (
                hostname,
                json.dumps(capabilities) if capabilities else None,
                json.dumps(tags) if tags else None,
                registered_time,
                registered_time,
                worker_id
            ))
            logger.info(f"Updated worker {worker_id} ({ip_address})")
        else:
            cursor.execute('''INSERT INTO workers (
                ip_address, hostname, status, capabilities, tags, last_heartbeat, registered_time
            ) VALUES (?, ?, 'online', ?, ?, ?, ?)''', (
                ip_address,
                hostname,
                json.dumps(capabilities) if capabilities else None,
                json.dumps(tags) if tags else None,
                registered_time,
                registered_time
            ))
            worker_id = cursor.lastrowid
            logger.info(f"Registered new worker {worker_id} ({ip_address})")

        self.conn.commit()
        return worker_id

    def update_worker_heartbeat(self, worker_id: int, current_load: Optional[Dict[str, Any]] = None):
        """Update worker heartbeat and current load"""
        cursor = self.conn.cursor()
        last_heartbeat = int(datetime.now().timestamp())

        cursor.execute('''UPDATE workers SET last_heartbeat = ?, current_load = ?, status = 'online'
                         WHERE worker_id = ?''', (
            last_heartbeat,
            json.dumps(current_load) if current_load else None,
            worker_id
        ))
        self.conn.commit()
        logger.debug(f"Worker {worker_id} heartbeat updated")

    def get_worker(self, worker_id: int) -> Optional[Dict[str, Any]]:
        """Get worker details"""
        cursor = self.conn.cursor()
        cursor.execute('''SELECT worker_id, ip_address, hostname, status, capabilities,
                         current_load, tags, heartbeat_interval, last_heartbeat, registered_time
                         FROM workers WHERE worker_id = ?''', (worker_id,))
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "worker_id": row[0],
            "ip_address": row[1],
            "hostname": row[2],
            "status": row[3],
            "capabilities": json.loads(row[4]) if row[4] else None,
            "current_load": json.loads(row[5]) if row[5] else None,
            "tags": json.loads(row[6]) if row[6] else None,
            "heartbeat_interval": row[7],
            "last_heartbeat": row[8],
            "registered_time": row[9]
        }

    def get_available_workers(self, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Get all available (online) workers, optionally filtered by tags

        Args:
            tags: Optional list of tags - workers must have at least one matching tag

        Returns:
            List of worker dicts
        """
        cursor = self.conn.cursor()
        cursor.execute('''SELECT worker_id, ip_address, hostname, capabilities, current_load, tags
                         FROM workers WHERE status = 'online' ''')

        workers = []
        for row in cursor.fetchall():
            worker = {
                "worker_id": row[0],
                "ip_address": row[1],
                "hostname": row[2],
                "capabilities": json.loads(row[3]) if row[3] else None,
                "current_load": json.loads(row[4]) if row[4] else None,
                "tags": json.loads(row[5]) if row[5] else None
            }

            # Filter by tags if specified
            if tags:
                worker_tags = worker.get("tags", [])
                if not any(tag in worker_tags for tag in tags):
                    continue

            workers.append(worker)

        return workers

    def mark_stale_workers_offline(self, timeout_seconds: int = 90):
        """Mark workers as offline if heartbeat is stale"""
        cursor = self.conn.cursor()
        cutoff_time = int(datetime.now().timestamp()) - timeout_seconds

        cursor.execute('''UPDATE workers SET status = 'offline'
                         WHERE status = 'online' AND last_heartbeat < ?''', (cutoff_time,))

        affected = cursor.rowcount
        self.conn.commit()
        if affected > 0:
            logger.warning(f"Marked {affected} workers as offline (heartbeat timeout)")
        return affected

    # ============================================================================
    # CRASH MANAGEMENT
    # ============================================================================

    def add_crash(self, job_id: int, worker_id: int, crash_data: Dict[str, Any]) -> int:
        """Add crash record"""
        cursor = self.conn.cursor()
        cursor.execute('''INSERT INTO crashes (
            job_id, worker_id, testcase_path, crash_type, details,
            signature, exploitability, crash_file, timestamp, duplicate_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
            job_id,
            worker_id,
            crash_data.get("testcase_path"),
            crash_data.get("crash_type"),
            crash_data.get("details"),
            crash_data.get("signature"),
            crash_data.get("exploitability"),
            crash_data.get("crash_file"),
            crash_data.get("timestamp", int(datetime.now().timestamp())),
            crash_data.get("duplicate_count", 0)
        ))
        crash_id = cursor.lastrowid
        self.conn.commit()
        logger.info(f"Recorded crash {crash_id} for job {job_id}")
        return crash_id

    def get_crashes(self, job_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all crashes, optionally filtered by job_id"""
        cursor = self.conn.cursor()
        if job_id:
            cursor.execute('''SELECT crash_id, job_id, worker_id, testcase_path, crash_type,
                             details, signature, exploitability, crash_file, timestamp, duplicate_count
                             FROM crashes WHERE job_id = ?''', (job_id,))
        else:
            cursor.execute('''SELECT crash_id, job_id, worker_id, testcase_path, crash_type,
                             details, signature, exploitability, crash_file, timestamp, duplicate_count
                             FROM crashes''')

        return [{
            "crash_id": row[0],
            "job_id": row[1],
            "worker_id": row[2],
            "testcase_path": row[3],
            "crash_type": row[4],
            "details": row[5],
            "signature": row[6],
            "exploitability": row[7],
            "crash_file": row[8],
            "timestamp": row[9],
            "duplicate_count": row[10]
        } for row in cursor.fetchall()]

    # ============================================================================
    # STATISTICS & MONITORING
    # ============================================================================

    def get_job_stats(self) -> Dict[str, int]:
        """Get job statistics by status"""
        cursor = self.conn.cursor()
        cursor.execute('''SELECT status, COUNT(*) FROM jobs GROUP BY status''')
        return {row[0]: row[1] for row in cursor.fetchall()}

    def get_worker_stats(self) -> Dict[str, int]:
        """Get worker statistics by status"""
        cursor = self.conn.cursor()
        cursor.execute('''SELECT status, COUNT(*) FROM workers GROUP BY status''')
        return {row[0]: row[1] for row in cursor.fetchall()}

    def get_queue_length(self) -> int:
        """Get number of jobs in queue"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM job_queue")
        return cursor.fetchone()[0]

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.debug("Scheduler database connection closed")
