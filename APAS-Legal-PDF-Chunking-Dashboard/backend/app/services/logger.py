"""SQLite activity log for tracking uploads and pushes."""
import sqlite3
import os
from datetime import datetime, timezone
from typing import Optional


DB_PATH = os.path.join(os.environ.get("DATA_DIR", "/data"), "activity.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            upload_time TEXT NOT NULL,
            page_count INTEGER DEFAULT 0,
            chunk_count INTEGER DEFAULT 0,
            pushed_to_neo4j INTEGER DEFAULT 0,
            push_time TEXT,
            processing_duration_s REAL DEFAULT 0,
            status TEXT DEFAULT 'pending',
            enrichment_enabled INTEGER DEFAULT 0,
            error_message TEXT
        )
    """)
    conn.commit()
    return conn


def create_log_entry(
    job_id: str,
    filename: str,
    enrichment_enabled: bool = False,
) -> int:
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO activity_log
           (job_id, filename, upload_time, status, enrichment_enabled)
           VALUES (?, ?, ?, 'processing', ?)""",
        (job_id, filename, now, int(enrichment_enabled)),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def update_log_entry(
    job_id: str,
    page_count: Optional[int] = None,
    chunk_count: Optional[int] = None,
    processing_duration_s: Optional[float] = None,
    status: Optional[str] = None,
    error_message: Optional[str] = None,
):
    conn = _get_conn()
    updates = []
    params = []
    if page_count is not None:
        updates.append("page_count = ?")
        params.append(page_count)
    if chunk_count is not None:
        updates.append("chunk_count = ?")
        params.append(chunk_count)
    if processing_duration_s is not None:
        updates.append("processing_duration_s = ?")
        params.append(processing_duration_s)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if error_message is not None:
        updates.append("error_message = ?")
        params.append(error_message)
    if updates:
        params.append(job_id)
        conn.execute(
            f"UPDATE activity_log SET {', '.join(updates)} WHERE job_id = ?",
            params,
        )
        conn.commit()
    conn.close()


def mark_pushed(job_id: str):
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE activity_log SET pushed_to_neo4j = 1, push_time = ? WHERE job_id = ?",
        (now, job_id),
    )
    conn.commit()
    conn.close()


def get_all_logs() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM activity_log ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_log_by_job(job_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM activity_log WHERE job_id = ?", (job_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None
