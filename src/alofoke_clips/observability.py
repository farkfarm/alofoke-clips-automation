from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class EventLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def emit(self, event: str, **fields: Any) -> None:
        record = json.dumps({"time": utc_now(), "event": event, **fields}, ensure_ascii=False)
        for name in ("RUNPOD_API_KEY",):
            if secret := os.environ.get(name):
                record = record.replace(secret, "[REDACTED]")
        with self._lock, self.path.open("a", encoding="utf-8") as output:
            output.write(record + "\n")


class Measurements:
    """Sample process-tree RSS. External model servers and GPU VRAM are separate metrics."""

    def __init__(self, log: EventLog):
        self.log = log
        self.stages: dict[str, float] = {}
        self.peak_rss_bytes = 0
        self.gpu_peak_used_mib: float | None = None
        self.gpu_samples = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        from .diagnostics import gpu_snapshot, nvidia_smi_path

        process = psutil.Process()
        has_gpu_query = nvidia_smi_path() is not None
        next_gpu_sample = 0.0
        while not self._stop.is_set():
            total = 0
            try:
                members = [process, *process.children(recursive=True)]
            except psutil.Error:
                members = [process]
            for member in members:
                try:
                    total += member.memory_info().rss
                except psutil.Error:
                    pass
            self.peak_rss_bytes = max(self.peak_rss_bytes, total)
            if has_gpu_query and time.monotonic() >= next_gpu_sample:
                snapshot = gpu_snapshot()
                if snapshot.get("available"):
                    used = sum(device["used_mib"] for device in snapshot["devices"])
                    self.gpu_peak_used_mib = max(self.gpu_peak_used_mib or 0, used)
                    self.gpu_samples += 1
                next_gpu_sample = time.monotonic() + 1
            self._stop.wait(0.1)

    def __enter__(self) -> Measurements:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    @contextmanager
    def stage(self, name: str):
        started = time.perf_counter()
        self.log.emit("stage_started", stage=name)
        status = "completed"
        try:
            yield
        except BaseException:
            status = "failed"
            raise
        finally:
            elapsed = time.perf_counter() - started
            self.stages[name] = self.stages.get(name, 0.0) + elapsed
            self.log.emit("stage_finished", stage=name, status=status, seconds=elapsed)
