"""Opt-in client for an EXISTING endpoint. It never creates infrastructure or installs models."""

from __future__ import annotations

import base64
import io
import os
import re
import time
import wave
from pathlib import Path
from typing import Any

from ..config import GPUConfig
from ..errors import ProviderError
from ..models import Analysis, Segment, Transcript, Word
from .http import JsonHTTP
from .qwen import SYSTEM_PROMPT


class RunPodClient:
    def __init__(
        self, config: GPUConfig, approved: bool, reserve_budget, http: JsonHTTP | None = None
    ):
        if not approved or not config.allow_paid:
            raise ProviderError("paid GPU requests are disabled")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", config.endpoint_id):
            raise ProviderError("configure an existing RunPod endpoint_id")
        if not os.environ.get("RUNPOD_API_KEY"):
            raise ProviderError("RUNPOD_API_KEY is missing")
        self.config = config
        if not config.usd_per_second:
            raise ProviderError("configure a conservative GPU rate before enabling paid requests")
        self.reserve_budget = reserve_budget
        self.http = http or JsonHTTP()
        self.metrics: dict[str, Any] = {"provider": "runpod", "jobs": []}

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        reservation = self.reserve_budget(self.config.timeout_seconds * self.config.usd_per_second)
        base = f"https://api.runpod.ai/v2/{self.config.endpoint_id}"
        token = os.environ["RUNPOD_API_KEY"]
        deadline = time.monotonic() + self.config.timeout_seconds
        result = self.http.request(base + "/run", {"input": payload}, 30, token)
        job_id = result.get("id", "")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", job_id):
            raise ProviderError(
                "RunPod returned no valid job id; submission outcome unknown, do not retry blindly"
            )
        self.metrics["jobs"].append(
            {"id": job_id, "status": result.get("status"), "budget_reservation": reservation}
        )
        record = self.metrics["jobs"][-1]
        while result.get("status") in {"IN_QUEUE", "IN_PROGRESS"}:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                try:
                    self.http.request(base + "/cancel/" + job_id, {}, 10, token)
                    record["cancel_requested"] = True
                except ProviderError:
                    record["cancel_requested"] = False
                raise ProviderError("RunPod deadline exceeded; check remote job status and billing")
            time.sleep(min(self.config.poll_seconds, remaining))
            result = self.http.request(base + "/status/" + job_id, None, min(30, remaining), token)
        record.update(
            {k: result[k] for k in ("status", "delayTime", "executionTime") if k in result}
        )
        if result.get("status") != "COMPLETED" or not isinstance(result.get("output"), dict):
            raise ProviderError("RunPod job did not complete successfully; inspect its dashboard")
        milliseconds = result.get("executionTime")
        if isinstance(milliseconds, (int, float)) and self.config.usd_per_second:
            record["estimated_execution_usd"] = milliseconds / 1000 * self.config.usd_per_second
            record["cost_note"] = (
                "Estimate excludes cold start, idle time, storage and transfer; not invoice cost"
            )
        return result["output"]


class RunPodTranscriber:
    def __init__(self, client: RunPodClient):
        self.client = client
        self.metrics = client.metrics

    def transcribe(self, audio: Path, duration: float) -> Transcript:
        output = []
        with wave.open(str(audio), "rb") as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (
                1,
                2,
                16000,
            ):
                raise ProviderError("GPU transcription requires 16kHz mono PCM16 WAV")
            frames_per_chunk = self.client.config.audio_chunk_seconds * 16000
            offset = 0.0
            while frames := source.readframes(frames_per_chunk):
                buffer = io.BytesIO()
                with wave.open(buffer, "wb") as chunk:
                    chunk.setnchannels(1)
                    chunk.setsampwidth(2)
                    chunk.setframerate(16000)
                    chunk.writeframes(frames)
                chunk_duration = len(frames) / 32000
                raw = self.client.execute(
                    {
                        "task": "transcribe",
                        "language": "es",
                        "audio_wav_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
                        "duration": chunk_duration,
                    }
                )
                transcript = Transcript.model_validate(raw)
                if transcript.duration > chunk_duration + 0.1:
                    raise ProviderError("GPU transcript exceeds its audio chunk")
                for segment in transcript.segments:
                    output.append(
                        Segment(
                            id=f"s{len(output):06d}",
                            start=segment.start + offset,
                            end=segment.end + offset,
                            text=segment.text,
                            no_speech_probability=segment.no_speech_probability,
                            avg_logprob=segment.avg_logprob,
                            words=[
                                Word(
                                    start=w.start + offset,
                                    end=w.end + offset,
                                    text=w.text,
                                    probability=w.probability,
                                )
                                for w in segment.words
                            ],
                        )
                    )
                offset += chunk_duration
        return Transcript(duration=duration, provider="runpod_faster_whisper", segments=output)


class RunPodAnalyzer:
    def __init__(self, client: RunPodClient, config):
        self.client = client
        self.config = config
        self.metrics = client.metrics

    def analyze(self, transcript: Transcript) -> Analysis:
        from .qwen import transcript_windows

        candidates, reasons = [], []
        for window in transcript_windows(transcript, self.config):
            raw = self.client.execute(
                {
                    "task": "analyze",
                    "model": self.config.model,
                    "system": SYSTEM_PROMPT,
                    "schema": Analysis.model_json_schema(),
                    "max_candidates": self.config.max_candidates_per_window,
                    "segments": [s.model_dump(exclude={"words"}) for s in window],
                }
            )
            result = Analysis.model_validate(raw)
            if len(result.candidates) > self.config.max_candidates_per_window:
                raise ProviderError("GPU analysis exceeded per-window candidate limit")
            allowed = {s.id for s in window}
            if any(set(p.segment_ids) - allowed for p in result.candidates):
                raise ProviderError("GPU analysis cited ids outside its input window")
            candidates.extend(result.candidates)
            reasons.append(result.abstention_reason)
        return Analysis(candidates=candidates, abstention_reason="; ".join(reasons)[:1500])
