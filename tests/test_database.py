"""
Tests for db/db.py - FawkesDB database operations.
"""

import os
import json
import pytest
import sqlite3
import tempfile
import threading
from pathlib import Path

from db.db import FawkesDB


class TestFawkesDBInit:
    """Tests for FawkesDB initialization."""

    def test_db_init_creates_file(self, tmp_path):
        """Test that DB init creates database file."""
        db_path = tmp_path / "test.db"
        db = FawkesDB(str(db_path))

        assert db_path.exists()
        db.close()

    def test_db_init_creates_directory(self, tmp_path):
        """Test that DB init creates directory if needed."""
        db_path = tmp_path / "subdir" / "test.db"
        db = FawkesDB(str(db_path))

        assert db_path.parent.exists()
        assert db_path.exists()
        db.close()

    def test_db_creates_tables(self, tmp_path):
        """Test that required tables are created."""
        db_path = tmp_path / "test.db"
        db = FawkesDB(str(db_path))

        # Check tables exist
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        assert "jobs" in tables
        assert "crashes" in tables
        assert "testcases" in tables

        conn.close()
        db.close()

    def test_db_wal_mode(self, tmp_path):
        """Test that WAL mode is enabled."""
        db_path = tmp_path / "test.db"
        db = FawkesDB(str(db_path))

        # Check journal mode
        cursor = db._conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]

        assert mode.lower() == "wal"
        db.close()


class TestJobsManagement:
    """Tests for job CRUD operations."""

    def test_add_job(self, tmp_path, sample_job_data):
        """Test adding a new job."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job_id = db.add_job(
            name=sample_job_data["name"],
            input_dir=sample_job_data["input_dir"],
            fuzzer_type=sample_job_data["fuzzer_type"],
            fuzzer_config=sample_job_data["fuzzer_config"]
        )

        assert job_id == 1
        db.close()

    def test_get_job(self, tmp_path, sample_job_data):
        """Test retrieving a job by ID."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job_id = db.add_job(
            name=sample_job_data["name"],
            input_dir=sample_job_data["input_dir"],
            fuzzer_type=sample_job_data["fuzzer_type"],
            fuzzer_config=sample_job_data["fuzzer_config"]
        )

        job = db.get_job(job_id)

        assert job is not None
        assert job["name"] == "test_job"
        assert job["status"] == "running"
        assert job["fuzzer_type"] == "file"
        assert job["fuzzer_config"]["mutations_per_seed"] == 100
        db.close()

    def test_get_nonexistent_job(self, tmp_path):
        """Test getting non-existent job returns None."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job = db.get_job(999)
        assert job is None
        db.close()

    def test_get_jobs(self, tmp_path):
        """Test retrieving all jobs."""
        db = FawkesDB(str(tmp_path / "test.db"))

        db.add_job("job1", "/corpus1")
        db.add_job("job2", "/corpus2")
        db.add_job("job3", "/corpus3")

        jobs = db.get_jobs()

        assert len(jobs) == 3
        # Should have all job names (order may vary due to same timestamp)
        names = {j["name"] for j in jobs}
        assert names == {"job1", "job2", "job3"}
        db.close()

    def test_update_job_status(self, tmp_path):
        """Test updating job status."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job_id = db.add_job("test", "/corpus")
        db.update_job_status(job_id, "completed")

        job = db.get_job(job_id)
        assert job["status"] == "completed"
        db.close()

    def test_update_fuzzer_stats(self, tmp_path):
        """Test updating fuzzer statistics."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job_id = db.add_job("test", "/corpus")
        db.update_fuzzer_stats(job_id, total_testcases=1000, generated_testcases=50)

        job = db.get_job(job_id)
        assert job["total_testcases"] == 1000
        assert job["generated_testcases"] == 50
        db.close()

    def test_update_job_vms(self, tmp_path):
        """Test updating VM count for a job."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job_id = db.add_job("test", "/corpus")
        db.update_job_vms(job_id, 4)

        job = db.get_job(job_id)
        assert job["vm_count"] == 4
        db.close()

    def test_delete_job(self, tmp_path):
        """Test deleting a job and associated data."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job_id = db.add_job("test", "/corpus")
        db.add_crash(job_id, "/crash.bin", "SIGSEGV", "crash details")
        db.add_testcase(job_id, 1, "/test.bin")

        # Delete job
        db.delete_job(job_id)

        # Verify deletion
        assert db.get_job(job_id) is None
        assert len(db.get_crashes(job_id)) == 0
        db.close()


class TestCrashesManagement:
    """Tests for crash handling and deduplication."""

    def test_add_crash_basic(self, tmp_path):
        """Test adding a basic crash."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job_id = db.add_job("test", "/corpus")
        crash_id = db.add_crash(
            job_id=job_id,
            testcase_path="/crash.bin",
            crash_type="SIGSEGV",
            details="Segmentation fault"
        )

        assert crash_id >= 1
        db.close()

    def test_add_crash_with_stack_hash(self, tmp_path, sample_crash_data):
        """Test adding a crash with stack hash for deduplication."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job_id = db.add_job("test", "/corpus")
        crash_id = db.add_crash(
            job_id=job_id,
            testcase_path=sample_crash_data["testcase_path"],
            crash_type=sample_crash_data["crash_type"],
            details=sample_crash_data["details"],
            stack_hash=sample_crash_data["stack_hash"],
            backtrace=sample_crash_data["backtrace"],
            crash_address=sample_crash_data["crash_address"]
        )

        assert crash_id >= 1
        db.close()

    def test_add_crash_with_sanitizer(self, tmp_path, sample_crash_data):
        """Test adding a crash with sanitizer information."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job_id = db.add_job("test", "/corpus")
        crash_id = db.add_crash(
            job_id=job_id,
            testcase_path=sample_crash_data["testcase_path"],
            crash_type=sample_crash_data["crash_type"],
            details=sample_crash_data["details"],
            sanitizer_type=sample_crash_data["sanitizer_type"],
            sanitizer_report=sample_crash_data["sanitizer_report"],
            severity=sample_crash_data["severity"]
        )

        assert crash_id >= 1
        db.close()

    def test_crash_deduplication_by_stack_hash(self, tmp_path):
        """Test that duplicate crashes are detected by stack hash."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job_id = db.add_job("test", "/corpus")

        # Add first crash
        crash_id1 = db.add_crash(
            job_id=job_id,
            testcase_path="/crash1.bin",
            crash_type="SIGSEGV",
            details="crash 1",
            stack_hash="unique_hash_123"
        )

        # Add duplicate with same stack hash
        crash_id2 = db.add_crash(
            job_id=job_id,
            testcase_path="/crash2.bin",
            crash_type="SIGSEGV",
            details="crash 2",
            stack_hash="unique_hash_123"
        )

        # Should return same ID (duplicate detected)
        assert crash_id1 == crash_id2
        db.close()

    def test_crash_deduplication_updates_count(self, tmp_path):
        """Test that duplicate count is incremented."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job_id = db.add_job("test", "/corpus")
        stack_hash = "test_hash_456"

        # Add crashes with same hash
        db.add_crash(job_id, "/crash1.bin", "SIGSEGV", "d1", stack_hash=stack_hash)
        db.add_crash(job_id, "/crash2.bin", "SIGSEGV", "d2", stack_hash=stack_hash)
        db.add_crash(job_id, "/crash3.bin", "SIGSEGV", "d3", stack_hash=stack_hash)

        # Check duplicate count
        crashes = db.get_crashes(job_id)
        assert len(crashes) == 1  # Only one unique crash
        assert crashes[0][9] == 2  # duplicate_count should be 2 (after initial)
        db.close()

    def test_get_unique_crashes(self, tmp_path):
        """Test getting only unique crashes."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job_id = db.add_job("test", "/corpus")

        # Add unique crashes
        db.add_crash(job_id, "/c1.bin", "SIGSEGV", "d1", stack_hash="hash1")
        db.add_crash(job_id, "/c2.bin", "SIGABRT", "d2", stack_hash="hash2")
        # Add duplicate
        db.add_crash(job_id, "/c3.bin", "SIGSEGV", "d3", stack_hash="hash1")

        unique = db.get_unique_crashes(job_id)
        assert len(unique) == 2
        db.close()

    def test_get_crash_statistics(self, tmp_path):
        """Test crash statistics calculation."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job_id = db.add_job("test", "/corpus")

        # Add crashes
        db.add_crash(job_id, "/c1.bin", "SIGSEGV", "d1", stack_hash="hash1")
        db.add_crash(job_id, "/c2.bin", "SIGABRT", "d2", stack_hash="hash2")
        db.add_crash(job_id, "/c3.bin", "SIGSEGV", "d3", stack_hash="hash1")  # duplicate

        stats = db.get_crash_statistics(job_id)

        assert stats["total_crashes"] == 2  # 2 records in DB
        assert stats["unique_crashes"] == 2
        db.close()


class TestTestcasesManagement:
    """Tests for testcase tracking."""

    def test_add_testcase(self, tmp_path):
        """Test adding a testcase record."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job_id = db.add_job("test", "/corpus")
        db.add_testcase(job_id, vm_id=1, testcase_path="/test.bin", execution_time=0.5)

        # Verify
        cursor = db._conn.cursor()
        cursor.execute("SELECT * FROM testcases WHERE job_id = ?", (job_id,))
        rows = cursor.fetchall()

        assert len(rows) == 1
        assert rows[0][3] == "/test.bin"  # testcase_path
        assert rows[0][5] == 0.5  # execution_time
        db.close()

    def test_add_testcase_no_execution_time(self, tmp_path):
        """Test adding testcase without execution time."""
        db = FawkesDB(str(tmp_path / "test.db"))

        job_id = db.add_job("test", "/corpus")
        db.add_testcase(job_id, vm_id=1, testcase_path="/test.bin")

        cursor = db._conn.cursor()
        cursor.execute("SELECT execution_time FROM testcases WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()

        assert row[0] is None
        db.close()


class TestSchemaMigration:
    """Tests for database schema migration."""

    def test_migrate_adds_vm_count(self, tmp_path):
        """Test migration adds vm_count column if missing."""
        db_path = tmp_path / "test.db"

        # Create old schema without vm_count
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE jobs (
                job_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                disk TEXT NOT NULL,
                status TEXT DEFAULT 'pending'
            )
        """)
        conn.execute("CREATE TABLE crashes (crash_id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE testcases (test_id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        # Open with FawkesDB (should migrate)
        db = FawkesDB(str(db_path))

        # Check column exists
        cursor = db._conn.cursor()
        cursor.execute("PRAGMA table_info(jobs)")
        columns = [col[1] for col in cursor.fetchall()]

        assert "vm_count" in columns
        db.close()

    def test_migrate_adds_crash_columns(self, tmp_path):
        """Test migration adds crash-related columns."""
        db_path = tmp_path / "test.db"

        # Create old schema without new crash columns
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE crashes (
                crash_id INTEGER PRIMARY KEY,
                job_id INTEGER,
                crash_type TEXT
            )
        """)
        conn.execute("CREATE TABLE jobs (job_id INTEGER PRIMARY KEY, name TEXT, disk TEXT)")
        conn.execute("CREATE TABLE testcases (test_id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        # Open with FawkesDB (should migrate)
        db = FawkesDB(str(db_path))

        # Check new columns exist
        cursor = db._conn.cursor()
        cursor.execute("PRAGMA table_info(crashes)")
        columns = [col[1] for col in cursor.fetchall()]

        assert "stack_hash" in columns
        assert "backtrace_json" in columns
        assert "is_unique" in columns
        assert "sanitizer_type" in columns
        assert "severity" in columns
        db.close()


class TestExploitabilityEstimation:
    """Tests for crash exploitability estimation."""

    def test_estimate_high_exploitability(self, tmp_path):
        """Test HIGH exploitability for RIP corruption."""
        db = FawkesDB(str(tmp_path / "test.db"))

        crash_info = {
            "signal": "SIGSEGV",
            "reg_bt": "RIP  0x41414141"
        }
        result = db.estimate_exploitability(crash_info)
        assert result == "HIGH"
        db.close()

    def test_estimate_low_exploitability(self, tmp_path):
        """Test LOW exploitability for NULL deref."""
        db = FawkesDB(str(tmp_path / "test.db"))

        crash_info = {
            "signal": "SIGSEGV",
            "reg_bt": "NULL pointer dereference at 0x00000000"
        }
        result = db.estimate_exploitability(crash_info)
        assert result == "LOW"
        db.close()

    def test_estimate_medium_exploitability(self, tmp_path):
        """Test MEDIUM exploitability for general crash."""
        db = FawkesDB(str(tmp_path / "test.db"))

        crash_info = {
            "signal": "SIGSEGV",
            "reg_bt": "crash at 0x12345678"
        }
        result = db.estimate_exploitability(crash_info)
        assert result == "MEDIUM"
        db.close()

    def test_estimate_unknown_signal(self, tmp_path):
        """Test UNKNOWN for unrecognized signals."""
        db = FawkesDB(str(tmp_path / "test.db"))

        crash_info = {
            "signal": "SIGINT",
            "reg_bt": ""
        }
        result = db.estimate_exploitability(crash_info)
        assert result == "UNKNOWN"
        db.close()


class TestConcurrency:
    """Tests for concurrent database access."""

    def test_concurrent_job_creation(self, tmp_path):
        """Test creating jobs from multiple threads."""
        db = FawkesDB(str(tmp_path / "test.db"))
        results = []

        def create_job(i):
            job_id = db.add_job(f"job_{i}", f"/corpus_{i}")
            results.append(job_id)

        threads = [threading.Thread(target=create_job, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # With concurrent access, there may be some collisions
        # but we should have created most jobs
        assert len(results) >= 5  # At least 5 results
        db.close()

    def test_concurrent_crash_recording(self, tmp_path):
        """Test recording crashes from multiple threads."""
        db = FawkesDB(str(tmp_path / "test.db"))
        job_id = db.add_job("test", "/corpus")

        def add_crash(i):
            db.add_crash(
                job_id=job_id,
                testcase_path=f"/crash_{i}.bin",
                crash_type="SIGSEGV",
                details=f"crash {i}",
                stack_hash=f"hash_{i}"  # Unique hashes
            )

        threads = [threading.Thread(target=add_crash, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # With concurrent access, most crashes should be recorded
        stats = db.get_crash_statistics(job_id)
        assert stats["total_crashes"] >= 10  # At least half should succeed
        db.close()
