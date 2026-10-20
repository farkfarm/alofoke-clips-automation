from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

from .errors import PipelineError
from .observability import utc_now


def sha256_file(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


class ArtifactStore(Protocol):
    def write_json(self, path: Path, value: Any) -> None: ...


class LocalArtifacts:
    def write_json(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL,
                    request_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, error TEXT, report_path TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0, request_key TEXT UNIQUE
                );
                CREATE TABLE IF NOT EXISTS clips (
                    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
                    source_hash TEXT NOT NULL, start REAL NOT NULL, end REAL NOT NULL,
                    text TEXT NOT NULL, video_hash TEXT NOT NULL,
                    metadata_path TEXT NOT NULL, mode TEXT NOT NULL,
                    UNIQUE(source_hash, start, end, mode)
                );
                CREATE INDEX IF NOT EXISTS clips_mode ON clips(mode);
                CREATE TABLE IF NOT EXISTS processing_lock (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), owner TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS worker_control (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), paused INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO worker_control VALUES (1, 0);
                CREATE TABLE IF NOT EXISTS cloud_reservations (
                    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
                    month TEXT NOT NULL, amount_usd REAL NOT NULL, created_at TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, request: dict[str, Any], request_key: str | None = None) -> str:
        job_id = uuid.uuid4().hex
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if request_key:
                existing = db.execute(
                    "SELECT id FROM jobs WHERE request_key=?", (request_key,)
                ).fetchone()
                if existing:
                    original = db.execute(
                        "SELECT request_json FROM jobs WHERE id=?", (existing[0],)
                    ).fetchone()[0]
                    if json.loads(original) != request:
                        raise PipelineError("job-key already belongs to a different request")
                    return existing[0]
            db.execute(
                "INSERT INTO jobs (id,status,request_json,created_at,updated_at,request_key) "
                "VALUES (?, 'queued', ?, ?, ?, ?)",
                (job_id, json.dumps(request), now, now, request_key),
            )
        return job_id

    def claim(self, job_id: str | None = None) -> dict[str, Any] | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if (
                db.execute("SELECT paused FROM worker_control").fetchone()[0]
                or db.execute("SELECT 1 FROM processing_lock").fetchone()
            ):
                return None
            row = db.execute(
                "SELECT * FROM jobs WHERE status='queued'"
                + (" AND id=?" if job_id else "")
                + " ORDER BY created_at LIMIT 1",
                (job_id,) if job_id else (),
            ).fetchone()
            if not row:
                return None
            db.execute("INSERT INTO processing_lock VALUES (1, ?)", (row["id"],))
            db.execute(
                "UPDATE jobs SET status='running', attempts=attempts+1, updated_at=? WHERE id=?",
                (utc_now(), row["id"]),
            )
            return dict(row)

    def finish(self, job_id: str, status: str, report: Path, error: str | None = None) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE jobs SET status=?, updated_at=?, error=?, report_path=? WHERE id=?",
                (status, utc_now(), error, str(report), job_id),
            )
            db.execute("DELETE FROM processing_lock WHERE owner=?", (job_id,))

    def list_jobs(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id,status,attempts,request_key,created_at,updated_at,error,report_path "
                    "FROM jobs ORDER BY created_at"
                )
            ]

    def set_paused(self, paused: bool) -> None:
        with self.connect() as db:
            db.execute("UPDATE worker_control SET paused=?", (int(paused),))

    def is_paused(self) -> bool:
        with self.connect() as db:
            return bool(db.execute("SELECT paused FROM worker_control").fetchone()[0])

    def reserve_cloud(
        self, job_id: str, amount: float, monthly_limit: float, job_limit: float
    ) -> str:
        import math

        if not math.isfinite(amount) or amount <= 0:
            raise PipelineError("cloud reservation must be positive and finite")
        now = utc_now()
        month = now[:7]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            monthly = db.execute(
                "SELECT COALESCE(SUM(amount_usd),0) FROM cloud_reservations WHERE month=?", (month,)
            ).fetchone()[0]
            per_job = db.execute(
                "SELECT COALESCE(SUM(amount_usd),0) FROM cloud_reservations WHERE job_id=?",
                (job_id,),
            ).fetchone()[0]
            if monthly + amount > monthly_limit + 1e-9 or per_job + amount > job_limit + 1e-9:
                raise PipelineError("cloud-processing budget limit would be exceeded")
            identity = uuid.uuid4().hex
            db.execute(
                "INSERT INTO cloud_reservations VALUES (?,?,?,?,?)",
                (identity, job_id, month, amount, now),
            )
        return identity

    def recover(self, job_id: str, allow_paid_gpu: bool = False) -> None:
        # Explicit operator action after confirming the previous process has stopped.
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT status,request_json FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if row is None or row[0] not in {"running", "failed"}:
                raise ValueError("only running or failed jobs can be recovered")
            db.execute("DELETE FROM processing_lock WHERE owner=?", (job_id,))
            request = json.loads(row["request_json"])
            request["allow_paid_gpu"] = allow_paid_gpu
            db.execute(
                "UPDATE jobs SET status='queued', updated_at=?, error=NULL,request_json=? "
                "WHERE id=?",
                (utc_now(), json.dumps(request), job_id),
            )

    def existing_clips(self, mode: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM clips WHERE mode=?", (mode,))
            return [
                dict(row)
                for row in rows
                if Path(row["metadata_path"]).is_file()
                and (Path(row["metadata_path"]).parent / "video.mp4").is_file()
            ]

    def save_clip(self, **fields: Any) -> None:
        with self.connect() as db:
            # Replace permits explicit regeneration after an artifact was removed.
            db.execute(
                "INSERT OR REPLACE INTO clips "
                "(id,job_id,source_hash,start,end,text,video_hash,metadata_path,mode) "
                "VALUES (:id,:job_id,:source_hash,:start,:end,:text,:video_hash,"
                ":metadata_path,:mode)",
                fields,
            )
