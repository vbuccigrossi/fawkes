import sqlite3
import json
from datetime import datetime

class ControllerDB:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS jobs
                          (job_id INTEGER PRIMARY KEY, config TEXT, status TEXT,
                           start_time TEXT, end_time TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS workers
                          (worker_id INTEGER PRIMARY KEY, ip_address TEXT UNIQUE,
                           status TEXT, last_seen TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS job_assignments
                          (assignment_id INTEGER PRIMARY KEY, job_id INTEGER,
                           worker_id INTEGER, status TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS crashes
                          (crash_id INTEGER PRIMARY KEY,
                           job_id INTEGER,
                           worker_id INTEGER,
                           testcase_path TEXT,
                           crash_type TEXT,
                           details TEXT,
                           signature TEXT,
                           exploitability TEXT,
                           crash_file TEXT,
                           timestamp TEXT,
                           duplicate_count INTEGER,
                           FOREIGN KEY (job_id) REFERENCES jobs(job_id),
                           FOREIGN KEY (worker_id) REFERENCES workers(worker_id))''')
        self.conn.commit()

    def add_job(self, config):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO jobs (config, status, start_time) VALUES (?, ?, ?)",
                       (json.dumps(config), "pending", datetime.utcnow().isoformat()))
        self.conn.commit()
        return cursor.lastrowid

    def add_worker(self, ip_address):
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO workers (ip_address, status, last_seen) VALUES (?, ?, ?)",
                       (ip_address, "offline", datetime.utcnow().isoformat()))
        self.conn.commit()

    def update_worker_status(self, worker_id, status):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE workers SET status = ?, last_seen = ? WHERE worker_id = ?",
                       (status, datetime.utcnow().isoformat(), worker_id))
        self.conn.commit()

    def assign_job_to_worker(self, job_id, worker_id):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO job_assignments (job_id, worker_id, status) VALUES (?, ?, ?)",
                       (job_id, worker_id, "active"))
        cursor.execute("UPDATE jobs SET status = 'running' WHERE job_id = ?", (job_id,))
        self.conn.commit()

    def add_crash(self, job_id, worker_id, crash):
        cursor = self.conn.cursor()
        cursor.execute('''INSERT INTO crashes (
                            job_id, worker_id, testcase_path, crash_type, details,
                            signature, exploitability, crash_file, timestamp, duplicate_count
                          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                       (job_id,
                        worker_id,
                        crash.get("testcase_path"),
                        crash.get("crash_type"),
                        crash.get("details"),
                        crash.get("signature"),
                        crash.get("exploitability"),
                        crash.get("crash_file"),
                        crash.get("timestamp", datetime.utcnow().isoformat()),
                        crash.get("duplicate_count", 0)))
        self.conn.commit()

    def get_workers(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT worker_id, ip_address, status FROM workers")
        return [{"worker_id": row[0], "ip_address": row[1], "status": row[2]} for row in cursor.fetchall()]

    def get_available_workers(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT worker_id, ip_address FROM workers WHERE status = 'online'")
        return [{"worker_id": row[0], "ip_address": row[1]} for row in cursor.fetchall()]

    def get_pending_jobs(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT job_id, config FROM jobs WHERE status = 'pending'")
        return [{"job_id": row[0], "config": json.loads(row[1])} for row in cursor.fetchall()]

    def get_crashes(self, job_id=None):
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
