"""
tracker/db.py — SQLite-backed job tracker
Tracks which jobs have been seen, applied, skipped, etc.
"""

import sqlite3
import logging
from datetime import datetime

log = logging.getLogger(__name__)


class JobTracker:
    def __init__(self, db_path: str = "data/jobs.db"):
        import os
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          TEXT PRIMARY KEY,
                source      TEXT,
                title       TEXT,
                company     TEXT,
                url         TEXT,
                email       TEXT,
                status      TEXT DEFAULT 'new',
                applied_at  TEXT
            )
        """)
        self.conn.commit()

    def already_applied(self, job_id: str) -> bool:
        cur = self.conn.execute(
            "SELECT status FROM jobs WHERE id = ?", (job_id,)
        )
        row = cur.fetchone()
        if not row:
            return False
        return row[0] in ("applied", "skipped")

    def mark(self, job_id: str, status: str, job: dict = None):
        if job:
            self.conn.execute("""
                INSERT OR REPLACE INTO jobs (id, source, title, company, url, email, status, applied_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id,
                job.get("source"),
                job.get("title"),
                job.get("company"),
                job.get("url"),
                job.get("contact_email"),
                status,
                datetime.now().isoformat(),
            ))
        else:
            self.conn.execute(
                "UPDATE jobs SET status = ?, applied_at = ? WHERE id = ?",
                (status, datetime.now().isoformat(), job_id),
            )
        self.conn.commit()

    def print_summary(self):
        cur = self.conn.execute(
            "SELECT status, COUNT(*) FROM jobs GROUP BY status"
        )
        rows = cur.fetchall()
        if rows:
            log.info("── Job tracker summary ──")
            for status, count in rows:
                log.info(f"  {status:<12} {count}")

    def all_jobs(self) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM jobs ORDER BY applied_at DESC")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
