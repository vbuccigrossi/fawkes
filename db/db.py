import os
import sqlite3
import time
import logging
import zipfile
import hashlib
from datetime import datetime
from typing import Optional
import json

logger = logging.getLogger("fawkes")

class FawkesDB:
    def __init__(self, db_path: str = "~/.fawkes/fawkes.db"):
        self.db_path = os.path.expanduser(db_path)
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        self._conn = None
        self.connect()
        self.create_tables()
        self.migrate_schema()  # Add migration step

    def connect(self):
        logger.debug(f"Connecting to SQLite DB at {self.db_path}")
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")

    def create_tables(self):
        cur = self._conn.cursor()
        # Consolidated jobs table with all fields
        cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            disk TEXT NOT NULL,
            snapshot TEXT,
            create_time INTEGER DEFAULT (strftime('%s', 'now')),
            status TEXT DEFAULT 'pending',
            fuzzer_type TEXT,
            fuzzer_config TEXT,
            total_testcases INTEGER,
            generated_testcases INTEGER,
            worker_id TEXT,
            controller_id TEXT,
            vm_count INTEGER DEFAULT 0
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS crashes (
            crash_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            testcase_path TEXT,
            crash_type TEXT,
            details TEXT,
            signature TEXT,
            exploitability TEXT,
            crash_file TEXT,
            timestamp INTEGER DEFAULT (strftime('%s', 'now')),
            duplicate_count INTEGER DEFAULT 0,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS testcases (
            test_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            vm_id INTEGER,
            testcase_path TEXT,
            start_time INTEGER DEFAULT (strftime('%s', 'now')),
            execution_time REAL,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        )
        """)
        self._conn.commit()
        logger.debug("Tables ensured/created: jobs, crashes, testcases.")

    def migrate_schema(self):
        """Add missing columns to existing tables."""
        cur = self._conn.cursor()

        # Check if vm_count exists in jobs
        cur.execute("PRAGMA table_info(jobs)")
        columns = [col[1] for col in cur.fetchall()]
        if "vm_count" not in columns:
            logger.info("Migrating jobs table to add vm_count column")
            cur.execute("ALTER TABLE jobs ADD COLUMN vm_count INTEGER DEFAULT 0")
            self._conn.commit()

        # Check if stack_hash exists in crashes
        cur.execute("PRAGMA table_info(crashes)")
        crash_columns = [col[1] for col in cur.fetchall()]

        if "stack_hash" not in crash_columns:
            logger.info("Migrating crashes table to add stack_hash column")
            cur.execute("ALTER TABLE crashes ADD COLUMN stack_hash TEXT")
            self._conn.commit()

        if "backtrace_json" not in crash_columns:
            logger.info("Migrating crashes table to add backtrace_json column")
            cur.execute("ALTER TABLE crashes ADD COLUMN backtrace_json TEXT")
            self._conn.commit()

        if "crash_address" not in crash_columns:
            logger.info("Migrating crashes table to add crash_address column")
            cur.execute("ALTER TABLE crashes ADD COLUMN crash_address TEXT")
            self._conn.commit()

        if "is_unique" not in crash_columns:
            logger.info("Migrating crashes table to add is_unique column")
            cur.execute("ALTER TABLE crashes ADD COLUMN is_unique INTEGER DEFAULT 1")
            self._conn.commit()

        # Sanitizer support columns
        if "sanitizer_type" not in crash_columns:
            logger.info("Migrating crashes table to add sanitizer_type column")
            cur.execute("ALTER TABLE crashes ADD COLUMN sanitizer_type TEXT")
            self._conn.commit()

        if "sanitizer_report" not in crash_columns:
            logger.info("Migrating crashes table to add sanitizer_report column")
            cur.execute("ALTER TABLE crashes ADD COLUMN sanitizer_report TEXT")
            self._conn.commit()

        if "severity" not in crash_columns:
            logger.info("Migrating crashes table to add severity column")
            cur.execute("ALTER TABLE crashes ADD COLUMN severity TEXT")
            self._conn.commit()

        # Add more migrations here if needed later

    def close(self):
        if self._conn:
            logger.debug("Closing SQLite DB connection.")
            self._conn.close()
            self._conn = None

    # Jobs Management
    def add_job(self, name: str, input_dir: str, fuzzer_type: str = None, fuzzer_config: dict = None) -> int:
        fuzzer_config_str = json.dumps(fuzzer_config) if fuzzer_config else None
        cur = self._conn.cursor()
        cur.execute("""
            INSERT INTO jobs(name, disk, create_time, status, fuzzer_type, fuzzer_config)
            VALUES (?, ?, ?, 'running', ?, ?)
        """, (name, input_dir, int(time.time()), fuzzer_type, fuzzer_config_str))
        self._conn.commit()
        job_id = cur.lastrowid
        logger.info(f"Job '{name}' added with job_id={job_id}")
        return job_id

    def update_job_status(self, job_id: int, new_status: str):
        cur = self._conn.cursor()
        cur.execute("UPDATE jobs SET status=? WHERE job_id=?", (new_status, job_id))
        self._conn.commit()
        logger.debug(f"Job {job_id} status updated to {new_status}")

    def update_fuzzer_stats(self, job_id: int, total_testcases: Optional[int] = None, generated_testcases: Optional[int] = None):
        cur = self._conn.cursor()
        if total_testcases is not None:
            cur.execute("UPDATE jobs SET total_testcases=? WHERE job_id=?", (total_testcases, job_id))
        if generated_testcases is not None:
            cur.execute("UPDATE jobs SET generated_testcases=? WHERE job_id=?", (generated_testcases, job_id))
        self._conn.commit()
        logger.debug(f"Updated fuzzer stats for job_id={job_id}: total={total_testcases}, generated={generated_testcases}")

    def update_job_vms(self, job_id: int, vm_count: int):
        cur = self._conn.cursor()
        cur.execute("UPDATE jobs SET vm_count=? WHERE job_id=?", (vm_count, job_id))
        self._conn.commit()
        logger.debug(f"Job {job_id} updated with vm_count={vm_count}")

    def get_job(self, job_id: int) -> dict:
        """Get a specific job by ID."""
        cur = self._conn.cursor()
        cur.execute("""
            SELECT job_id, name, disk, snapshot, status, fuzzer_type, fuzzer_config,
                   total_testcases, generated_testcases, create_time, vm_count
            FROM jobs WHERE job_id = ?
        """, (job_id,))
        row = cur.fetchone()
        if row:
            return {
                'job_id': row[0],
                'name': row[1],
                'disk': row[2],
                'snapshot': row[3],
                'status': row[4],
                'fuzzer_type': row[5],
                'fuzzer_config': json.loads(row[6]) if row[6] else None,
                'total_testcases': row[7] or 0,
                'generated_testcases': row[8] or 0,
                'create_time': row[9],
                'vm_count': row[10] or 0
            }
        return None

    def get_jobs(self) -> list:
        """Get all jobs."""
        cur = self._conn.cursor()
        cur.execute("""
            SELECT job_id, name, disk, snapshot, status, fuzzer_type, fuzzer_config,
                   total_testcases, generated_testcases, create_time, vm_count
            FROM jobs ORDER BY create_time DESC
        """)
        jobs = []
        for row in cur.fetchall():
            jobs.append({
                'job_id': row[0],
                'name': row[1],
                'disk': row[2],
                'snapshot': row[3],
                'status': row[4],
                'fuzzer_type': row[5],
                'fuzzer_config': json.loads(row[6]) if row[6] else None,
                'total_testcases': row[7] or 0,
                'generated_testcases': row[8] or 0,
                'create_time': row[9],
                'vm_count': row[10] or 0
            })
        return jobs

    def delete_job(self, job_id: int):
        """Delete a job and all associated data (crashes, testcases)."""
        cur = self._conn.cursor()
        # Delete associated testcases
        cur.execute("DELETE FROM testcases WHERE job_id = ?", (job_id,))
        # Delete associated crashes
        cur.execute("DELETE FROM crashes WHERE job_id = ?", (job_id,))
        # Delete the job
        cur.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        self._conn.commit()
        logger.info(f"Job {job_id} and all associated data deleted")

    # Crashes Management
    def add_crash(self, job_id: int, testcase_path: str, crash_type: str, details: str, crash_file: str = None,
                  stack_hash: str = None, backtrace: list = None, crash_address: str = None,
                  sanitizer_type: str = None, sanitizer_report: dict = None, severity: str = None) -> int:
        """
        Add crash to database with enhanced deduplication and sanitizer support.

        Args:
            job_id: Job ID
            testcase_path: Path to crashing testcase
            crash_type: Type of crash
            details: Crash details
            crash_file: Path to crash archive
            stack_hash: Stack trace hash for deduplication (preferred)
            backtrace: Full backtrace as list of dicts
            crash_address: Memory address where crash occurred
            sanitizer_type: Sanitizer that detected the crash (ASAN, UBSAN, etc.)
            sanitizer_report: Full sanitizer report as dict
            severity: Crash severity (critical, high, medium, low)

        Returns:
            crash_id
        """
        timestamp = int(time.time())
        cur = self._conn.cursor()

        # Use stack_hash for deduplication if available, otherwise fall back to old method
        if stack_hash:
            # Modern deduplication by stack hash
            dedup_key = stack_hash
        else:
            # Legacy deduplication by crash type + details
            dedup_key = hashlib.sha256(f"{crash_type}:{details}".encode()).hexdigest()

        signature = dedup_key

        # Check for duplicate using stack_hash if available
        if stack_hash:
            cur.execute("SELECT crash_id, duplicate_count FROM crashes WHERE stack_hash = ?", (stack_hash,))
        else:
            cur.execute("SELECT crash_id, duplicate_count FROM crashes WHERE signature = ?", (signature,))

        existing = cur.fetchone()
        if existing:
            # Duplicate crash - increment duplicate count but keep original as unique
            crash_id, dup_count = existing
            cur.execute("UPDATE crashes SET duplicate_count = ? WHERE crash_id = ?",
                       (dup_count + 1, crash_id))
            self._conn.commit()
            logger.info(f"Duplicate crash detected for signature={dedup_key[:16]}..., crash_id={crash_id}, new count={dup_count + 1}")
            return crash_id

        # New unique crash
        backtrace_json = json.dumps(backtrace) if backtrace else None
        sanitizer_report_json = json.dumps(sanitizer_report) if sanitizer_report else None

        cur.execute("""
        INSERT INTO crashes(job_id, testcase_path, crash_type, details, signature, crash_file, timestamp,
                           stack_hash, backtrace_json, crash_address, is_unique,
                           sanitizer_type, sanitizer_report, severity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """, (job_id, testcase_path, crash_type, details, signature, crash_file, timestamp,
              stack_hash, backtrace_json, crash_address,
              sanitizer_type, sanitizer_report_json, severity))
        self._conn.commit()
        crash_id = cur.lastrowid
        logger.info(f"New unique crash recorded: job_id={job_id}, crash_id={crash_id}, signature={dedup_key[:16]}...")
        return crash_id

    def get_crashes(self, job_id: int) -> list:
        """Get all crashes for a specific job."""
        cur = self._conn.cursor()
        cur.execute("""
            SELECT crash_id, job_id, testcase_path, crash_type, details,
                   signature, exploitability, crash_file, timestamp, duplicate_count,
                   stack_hash, crash_address, is_unique
            FROM crashes WHERE job_id = ?
        """, (job_id,))
        return cur.fetchall()

    def get_unique_crashes(self, job_id: int = None) -> list:
        """
        Get only unique crashes (not duplicates).

        Args:
            job_id: Optional job ID to filter by

        Returns:
            List of unique crash records
        """
        cur = self._conn.cursor()
        if job_id:
            cur.execute("""
                SELECT crash_id, job_id, testcase_path, crash_type, details,
                       signature, exploitability, crash_file, timestamp, duplicate_count,
                       stack_hash, crash_address, is_unique
                FROM crashes
                WHERE job_id = ? AND is_unique = 1
                ORDER BY timestamp DESC
            """, (job_id,))
        else:
            cur.execute("""
                SELECT crash_id, job_id, testcase_path, crash_type, details,
                       signature, exploitability, crash_file, timestamp, duplicate_count,
                       stack_hash, crash_address, is_unique
                FROM crashes
                WHERE is_unique = 1
                ORDER BY timestamp DESC
            """)
        return cur.fetchall()

    def get_crash_statistics(self, job_id: int = None) -> dict:
        """
        Get crash statistics including deduplication metrics.

        Args:
            job_id: Optional job ID to filter by

        Returns:
            Dict with crash statistics
        """
        cur = self._conn.cursor()

        if job_id:
            cur.execute("SELECT COUNT(*) FROM crashes WHERE job_id = ?", (job_id,))
            total_crashes = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM crashes WHERE job_id = ? AND is_unique = 1", (job_id,))
            unique_crashes = cur.fetchone()[0]
        else:
            cur.execute("SELECT COUNT(*) FROM crashes")
            total_crashes = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM crashes WHERE is_unique = 1")
            unique_crashes = cur.fetchone()[0]

        duplicate_crashes = total_crashes - unique_crashes
        dedup_ratio = (duplicate_crashes / max(1, total_crashes)) * 100

        return {
            'total_crashes': total_crashes,
            'unique_crashes': unique_crashes,
            'duplicate_crashes': duplicate_crashes,
            'dedup_ratio': dedup_ratio
        }

    # Testcases Management
    def add_testcase(self, job_id: int, vm_id: int, testcase_path: str, execution_time: Optional[float] = None):
        cur = self._conn.cursor()
        cur.execute("""
        INSERT INTO testcases(job_id, vm_id, testcase_path, execution_time)
        VALUES (?, ?, ?, ?)
        """, (job_id, vm_id, testcase_path, execution_time))
        self._conn.commit()
        logger.debug(f"Testcase added for job_id={job_id}, vm_id={vm_id}")

    # Legacy Methods
    def record_crash(self, job_id: int, test_file: str, signature: str, exploitability: str, notes: str = "") -> int:
        return self.add_crash(job_id, test_file, "unknown", notes, crash_file=None)

    def estimate_exploitability(self, crash_info: dict) -> str:
        signal = crash_info.get("signal", "UNKNOWN")
        reg_bt = crash_info.get("reg_bt", "")
        if "SIGSEGV" in signal or "SIGILL" in signal:
            if "RIP  0x41414141" in reg_bt or "EIP  0x41414141" in reg_bt:
                return "HIGH"
            elif "0x00000000" in reg_bt or "NULL" in reg_bt:
                return "LOW"
            return "MEDIUM"
        return "UNKNOWN"

    def package_crash_data(self, job_name: str, test_file: str, crash_id: int, crash_info: dict, artifact_files: list) -> str:
        base_dir = os.path.expanduser("~/.fawkes/crashes")
        os.makedirs(base_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"crash_{job_name}_{timestamp}_{crash_id}.zip"
        zip_path = os.path.join(base_dir, zip_name)
        logger.info(f"Creating crash archive: {zip_path}")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if os.path.isfile(test_file):
                zf.write(test_file, os.path.basename(test_file))
            for f in artifact_files:
                if os.path.isfile(f):
                    zf.write(f, os.path.basename(f))
            info_txt = self._generate_crash_info_text(crash_info)
            zf.writestr("crash_info.txt", info_txt)
        cur = self._conn.cursor()
        cur.execute("UPDATE crashes SET zip_path=? WHERE crash_id=?", (zip_path, crash_id))
        self._conn.commit()
        logger.info(f"Crash archive created at: {zip_path}")
        return zip_path

    def _generate_crash_info_text(self, crash_info: dict) -> str:
        lines = [
            f"Signal: {crash_info.get('signal', 'unknown')}",
            f"Desc: {crash_info.get('desc', '')}",
            "",
            "=== Registers & Backtrace ===",
            crash_info.get("reg_bt", ""),
            ""
        ]
        extra_mem = crash_info.get("extra_mem", "")
        if extra_mem:
            lines.extend(["=== Extra Memory Dump ===", extra_mem, ""])
        return "\n".join(lines)
