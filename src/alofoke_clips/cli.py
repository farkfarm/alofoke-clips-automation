from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from pydantic import ValidationError

from .config import load_settings, require_gpu_permission
from .diagnostics import diagnose
from .errors import PipelineError
from .pipeline import run_claimed
from .storage import Database, LocalArtifacts


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Authorized local recordings → reviewable Spanish clips"
    )
    parser.add_argument(
        "--config", type=Path, help="TOML configuration (paths relative to this file)"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("process", "enqueue", "benchmark"):
        command = commands.add_parser(name)
        command.add_argument("source", type=Path)
        command.add_argument(
            "--authorized-local",
            action="store_true",
            required=True,
            help="Confirm that you have permission to process the recording",
        )
        command.add_argument("--mode", choices=("mock", "local", "gpu"))
        command.add_argument("--mock-transcript", type=Path)
        command.add_argument("--mock-analysis", type=Path)
        command.add_argument("--job-key", help="Optional idempotency key for submission")
        command.add_argument(
            "--allow-paid-gpu",
            action="store_true",
            help="Explicit approval for this GPU job; also needs config permission and budget",
        )
    commands.add_parser("doctor", help="Read-only diagnostics; installs and downloads nothing")
    worker = commands.add_parser("worker", help="Serial local worker; queue persists while offline")
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--poll-seconds", type=float, default=2)
    queue = commands.add_parser("queue")
    actions = queue.add_subparsers(dest="action", required=True)
    for name in ("pause", "resume", "list"):
        actions.add_parser(name)
    retry = actions.add_parser("retry")
    retry.add_argument("job_id")
    retry.add_argument("--confirm-worker-stopped", action="store_true", required=True)
    retry.add_argument("--allow-paid-gpu", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
        if args.command == "doctor":
            result = diagnose(settings)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ffmpeg"]["ready"] else 1
        db = Database(settings.data_dir / "queue.sqlite3")
        if args.command == "queue":
            if args.action in {"pause", "resume"}:
                db.set_paused(args.action == "pause")
                print(
                    json.dumps(
                        {
                            "paused": db.is_paused(),
                            "note": "Active stages finish and release models before pausing",
                        }
                    )
                )
            elif args.action == "retry":
                db.recover(args.job_id, args.allow_paid_gpu)
                print(json.dumps({"job_id": args.job_id, "status": "queued"}))
            else:
                print(json.dumps({"paused": db.is_paused(), "jobs": db.list_jobs()}, indent=2))
            return 0
        if args.command == "worker":
            if not 0.1 <= args.poll_seconds <= 60:
                raise PipelineError("poll-seconds must be between 0.1 and 60")
            while True:
                job = db.claim()
                if job:
                    report = run_claimed(db, job)
                    print(json.dumps(report, ensure_ascii=False), flush=True)
                    if args.once:
                        return 1 if report["status"] == "failed" else 0
                elif args.once:
                    print(json.dumps({"status": "idle", "paused": db.is_paused()}))
                    return 0
                else:
                    time.sleep(args.poll_seconds)
        if args.mode:
            settings.mode = args.mode
        require_gpu_permission(settings, args.allow_paid_gpu)
        if settings.mode == "mock" and (not args.mock_transcript or not args.mock_analysis):
            raise PipelineError("MOCK requires --mock-transcript and --mock-analysis")
        request = {
            "settings": settings.model_dump(mode="json"),
            "source": str(args.source.resolve()),
            "authorized_local": args.authorized_local,
            "allow_paid_gpu": args.allow_paid_gpu,
            "benchmark": args.command == "benchmark",
            "mock_transcript": str(args.mock_transcript.resolve())
            if args.mock_transcript
            else None,
            "mock_analysis": str(args.mock_analysis.resolve()) if args.mock_analysis else None,
        }
        job_id = db.enqueue(request, args.job_key)
        if args.command == "enqueue":
            print(json.dumps({"job_id": job_id, "queue": str(db.path)}))
            return 0
        job = db.claim(job_id)
        if not job:
            print(
                json.dumps(
                    {
                        "job_id": job_id,
                        "status": "already tracked or worker busy/paused",
                        "next_step": "queue list",
                    }
                )
            )
            return 0
        if args.command == "benchmark":
            # Hardware collection is separate from the measured pipeline total.
            hardware = diagnose(settings)
            LocalArtifacts().write_json(
                settings.data_dir / "jobs" / job_id / "hardware.json", hardware
            )
        report = run_claimed(db, job)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["status"] == "failed" else 0
    except KeyboardInterrupt:
        print("Worker stopped; queued jobs remain in SQLite.", file=sys.stderr)
        return 130
    except (PipelineError, OSError, ValueError, ValidationError) as error:
        message = str(error) if isinstance(error, PipelineError) else error.__class__.__name__
        print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
