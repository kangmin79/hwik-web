"""SQLite 체크포인트.

Stage 별로 (key → status) 기록. 재실행 시 done 건너뛰기.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class Checkpoint:
    """Thread-safe SQLite checkpoint store."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS stage_progress (
                stage         TEXT NOT NULL,
                key           TEXT NOT NULL,
                status        TEXT NOT NULL,
                row_count     INTEGER,
                completed_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                error         TEXT,
                PRIMARY KEY (stage, key)
            )
        """)

    def is_done(self, stage: str, key: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "SELECT status FROM stage_progress WHERE stage=? AND key=?",
                (stage, key),
            )
            row = cur.fetchone()
        return bool(row and row[0] == "done")

    def mark_done(self, stage: str, key: str, row_count: int = 0) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO stage_progress(stage, key, status, row_count, error)
                   VALUES(?,?,?,?,NULL)
                   ON CONFLICT(stage, key) DO UPDATE SET
                     status='done', row_count=excluded.row_count,
                     completed_at=CURRENT_TIMESTAMP, error=NULL""",
                (stage, key, "done", row_count),
            )

    def mark_error(self, stage: str, key: str, error: str) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO stage_progress(stage, key, status, error)
                   VALUES(?,?,?,?)
                   ON CONFLICT(stage, key) DO UPDATE SET
                     status='error', error=excluded.error,
                     completed_at=CURRENT_TIMESTAMP""",
                (stage, key, "error", error[:1000]),
            )

    def stage_summary(self, stage: str) -> dict:
        with self._lock:
            cur = self._conn.execute(
                """SELECT status, COUNT(*), COALESCE(SUM(row_count),0)
                   FROM stage_progress WHERE stage=? GROUP BY status""",
                (stage,),
            )
            rows = cur.fetchall()
        out = {"done": 0, "error": 0, "rows": 0}
        for status, n, rc in rows:
            out[status] = n
            if status == "done":
                out["rows"] = rc
        return out
