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

    # Crashes Management
    def add_crash(self, job_id: int, testcase_path: str, crash_type: str, details: str, crash_file: str = None) -> int:
        timestamp = int(time.time())
        cur = self._conn.cursor()
        signature = hashlib.sha256(f"{crash_type}:{details}".encode()).hexdigest()
        cur.execute("SELECT crash_id, duplicate_count FROM crashes WHERE signature = ?", (signature,))
        existing = cur.fetchone()
        if existing:
            crash_id, dup_count = existing
            cur.execute("UPDATE crashes SET duplicate_count = ? WHERE crash_id = ?", (dup_count + 1, crash_id))
            self._conn.commit()
            logger.info(f"Duplicate crash detected for signature={signature}, crash_id={crash_id}, new count={dup_count + 1}")
            return crash_id
        cur.execute("""
        INSERT INTO crashes(job_id, testcase_path, crash_type, details, signature, crash_file, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (job_id, testcase_path, crash_type, details, signature, crash_file, timestamp))
        self._conn.commit()
        crash_id = cur.lastrowid
        logger.info(f"New crash recorded: job_id={job_id}, crash_id={crash_id}, signature={signature}")
        return crash_id

    def get_crashes(self, job_id: int) -> list:
        """Get all crashes for a specific job."""
        cur = self._conn.cursor()
        cur.execute("""
            SELECT crash_id, job_id, testcase_path, crash_type, details,
                   signature, exploitability, crash_file, timestamp, duplicate_count
            FROM crashes WHERE job_id = ?
        """, (job_id,))
        return cur.fetchall()

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
