"""
Differential Fuzzing Database

Stores divergences, execution results, and campaign data.
"""

import sqlite3
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from .engine import Divergence, ExecutionResult, DivergenceType, DivergenceSeverity


logger = logging.getLogger("fawkes.differential.db")


class DifferentialDB:
    """Database for differential fuzzing results"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.create_tables()

    def create_tables(self):
        """Create differential fuzzing tables"""
        cursor = self.conn.cursor()

        # Campaigns table
        cursor.execute('''CREATE TABLE IF NOT EXISTS campaigns (
            campaign_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            targets TEXT NOT NULL,
            start_time INTEGER,
            end_time INTEGER,
            testcases_executed INTEGER DEFAULT 0,
            divergences_found INTEGER DEFAULT 0,
            crashes_found INTEGER DEFAULT 0
        )''')

        # Execution results table
        cursor.execute('''CREATE TABLE IF NOT EXISTS executions (
            execution_id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER,
            target_id TEXT NOT NULL,
            target_version TEXT NOT NULL,
            testcase_path TEXT NOT NULL,
            crashed BOOLEAN,
            exit_code INTEGER,
            timeout BOOLEAN,
            execution_time REAL,
            output_hash TEXT,
            signal TEXT,
            timestamp INTEGER,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
        )''')

        # Divergences table
        cursor.execute('''CREATE TABLE IF NOT EXISTS divergences (
            divergence_id TEXT PRIMARY KEY,
            campaign_id INTEGER,
            testcase_path TEXT NOT NULL,
            divergence_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            target_a_id TEXT NOT NULL,
            target_b_id TEXT NOT NULL,
            description TEXT,
            confidence REAL,
            details TEXT,
            timestamp INTEGER,
            triaged BOOLEAN DEFAULT 0,
            notes TEXT,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
        )''')

        # Indices
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_divergences_campaign
                         ON divergences(campaign_id)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_divergences_severity
                         ON divergences(severity)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_divergences_type
                         ON divergences(divergence_type)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_executions_campaign
                         ON executions(campaign_id)''')

        self.conn.commit()
        logger.debug("Differential database tables created/verified")

    def add_campaign(self, name: str, targets: List[str],
                    description: Optional[str] = None) -> int:
        """Add a new campaign"""
        cursor = self.conn.cursor()
        start_time = int(datetime.now().timestamp())

        cursor.execute('''INSERT INTO campaigns (name, description, targets, start_time)
                         VALUES (?, ?, ?, ?)''', (
            name,
            description,
            json.dumps(targets),
            start_time
        ))

        campaign_id = cursor.lastrowid
        self.conn.commit()
        logger.info(f"Created campaign {campaign_id}: {name}")
        return campaign_id

    def update_campaign_stats(self, campaign_id: int, stats: Dict[str, int]):
        """Update campaign statistics"""
        cursor = self.conn.cursor()
        cursor.execute('''UPDATE campaigns SET
                         testcases_executed = ?,
                         divergences_found = ?,
                         crashes_found = ?
                         WHERE campaign_id = ?''', (
            stats.get("testcases_executed", 0),
            stats.get("divergences_found", 0),
            stats.get("crashes_found", 0),
            campaign_id
        ))
        self.conn.commit()

    def end_campaign(self, campaign_id: int):
        """Mark campaign as ended"""
        cursor = self.conn.cursor()
        end_time = int(datetime.now().timestamp())
        cursor.execute("UPDATE campaigns SET end_time = ? WHERE campaign_id = ?",
                      (end_time, campaign_id))
        self.conn.commit()

    def add_execution(self, campaign_id: int, result: ExecutionResult) -> int:
        """Add execution result"""
        cursor = self.conn.cursor()
        cursor.execute('''INSERT INTO executions (
            campaign_id, target_id, target_version, testcase_path,
            crashed, exit_code, timeout, execution_time, output_hash, signal, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
            campaign_id,
            result.target_id,
            result.target_version,
            result.testcase_path,
            result.crashed,
            result.exit_code,
            result.timeout,
            result.execution_time,
            result.output_hash,
            result.signal,
            int(datetime.now().timestamp())
        ))

        execution_id = cursor.lastrowid
        self.conn.commit()
        return execution_id

    def add_divergence(self, campaign_id: int, divergence: Divergence):
        """Add divergence"""
        cursor = self.conn.cursor()

        cursor.execute('''INSERT OR IGNORE INTO divergences (
            divergence_id, campaign_id, testcase_path, divergence_type, severity,
            target_a_id, target_b_id, description, confidence, details, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
            divergence.divergence_id,
            campaign_id,
            divergence.testcase_path,
            divergence.divergence_type.value,
            divergence.severity.value,
            divergence.target_a.target_id,
            divergence.target_b.target_id,
            divergence.description,
            divergence.confidence,
            json.dumps(divergence.details),
            divergence.timestamp
        ))

        self.conn.commit()

    def get_divergences(self, campaign_id: Optional[int] = None,
                       severity: Optional[str] = None,
                       div_type: Optional[str] = None) -> List[Dict]:
        """Get divergences with optional filters"""
        cursor = self.conn.cursor()

        query = "SELECT * FROM divergences WHERE 1=1"
        params = []

        if campaign_id is not None:
            query += " AND campaign_id = ?"
            params.append(campaign_id)

        if severity is not None:
            query += " AND severity = ?"
            params.append(severity)

        if div_type is not None:
            query += " AND divergence_type = ?"
            params.append(div_type)

        query += " ORDER BY timestamp DESC"

        cursor.execute(query, params)

        divergences = []
        for row in cursor.fetchall():
            divergences.append({
                "divergence_id": row[0],
                "campaign_id": row[1],
                "testcase_path": row[2],
                "divergence_type": row[3],
                "severity": row[4],
                "target_a_id": row[5],
                "target_b_id": row[6],
                "description": row[7],
                "confidence": row[8],
                "details": json.loads(row[9]) if row[9] else {},
                "timestamp": row[10],
                "triaged": bool(row[11]),
                "notes": row[12]
            })

        return divergences

    def get_campaign_summary(self, campaign_id: int) -> Optional[Dict]:
        """Get campaign summary"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,))
        row = cursor.fetchone()

        if not row:
            return None

        return {
            "campaign_id": row[0],
            "name": row[1],
            "description": row[2],
            "targets": json.loads(row[3]),
            "start_time": row[4],
            "end_time": row[5],
            "testcases_executed": row[6],
            "divergences_found": row[7],
            "crashes_found": row[8]
        }

    def triage_divergence(self, divergence_id: str, notes: str):
        """Mark divergence as triaged"""
        cursor = self.conn.cursor()
        cursor.execute('''UPDATE divergences SET triaged = 1, notes = ?
                         WHERE divergence_id = ?''', (notes, divergence_id))
        self.conn.commit()

    def get_stats(self, campaign_id: Optional[int] = None) -> Dict[str, Any]:
        """Get statistics"""
        cursor = self.conn.cursor()

        stats = {}

        # Total campaigns
        cursor.execute("SELECT COUNT(*) FROM campaigns")
        stats["total_campaigns"] = cursor.fetchone()[0]

        # Filter by campaign if specified
        where_clause = f"WHERE campaign_id = {campaign_id}" if campaign_id else ""

        # Divergences by type
        cursor.execute(f'''SELECT divergence_type, COUNT(*) FROM divergences
                          {where_clause}
                          GROUP BY divergence_type''')
        stats["divergences_by_type"] = {row[0]: row[1] for row in cursor.fetchall()}

        # Divergences by severity
        cursor.execute(f'''SELECT severity, COUNT(*) FROM divergences
                          {where_clause}
                          GROUP BY severity''')
        stats["divergences_by_severity"] = {row[0]: row[1] for row in cursor.fetchall()}

        # Total divergences
        cursor.execute(f"SELECT COUNT(*) FROM divergences {where_clause}")
        stats["total_divergences"] = cursor.fetchone()[0]

        # Triaged divergences
        cursor.execute(f'''SELECT COUNT(*) FROM divergences
                          {where_clause}
                          {'AND' if where_clause else 'WHERE'} triaged = 1''')
        stats["triaged_divergences"] = cursor.fetchone()[0]

        return stats

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
