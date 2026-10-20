from __future__ import annotations

import json
import platform
import shutil
import time
from pathlib import Path
from typing import Any

from .config import Settings, require_gpu_permission
from .detection import SCORE_WEIGHTS, clip_identity, evaluate, select
from .errors import ConfigurationError, JobPaused, PipelineError
from .ingestion import ingest_local
from .media import MediaTools
from .models import Analysis, ClipMetadata, Transcript
from .observability import EventLog, Measurements, utc_now
from .providers.base import Analyzer, Transcriber
from .storage import Database, LocalArtifacts, sha256_file
from .subtitles import clip_transcript, write_subtitles


def make_providers(
    settings: Settings, request: dict[str, Any], db: Database, job_id: str
) -> tuple[Transcriber, Analyzer]:
    require_gpu_permission(settings, request.get("allow_paid_gpu", False))
    if settings.mode == "mock":
        from .providers.mock import MockAnalyzer, MockTranscriber

        if not request.get("mock_transcript") or not request.get("mock_analysis"):
            raise ConfigurationError(
                "MOCK requires explicit --mock-transcript and --mock-analysis fixtures"
            )
        return MockTranscriber(Path(request["mock_transcript"])), MockAnalyzer(
            Path(request["mock_analysis"])
        )
    if settings.mode == "local":
        from .providers.faster_whisper import FasterWhisperTranscriber
        from .providers.qwen import QwenAnalyzer

        if settings.analysis.backend == "llama_cpp" and settings.transcription.device == "cuda":
            raise ConfigurationError(
                "Use Ollama for automatic GPU unloading, or set transcription.device=cpu "
                "when using a separately managed llama.cpp server"
            )
        return FasterWhisperTranscriber(settings.transcription), QwenAnalyzer(settings.analysis)
    from .providers.runpod import RunPodAnalyzer, RunPodClient, RunPodTranscriber

    client = RunPodClient(
        settings.gpu,
        request.get("allow_paid_gpu", False),
        lambda amount: db.reserve_cloud(
            job_id, amount, settings.gpu.monthly_budget_usd, settings.gpu.max_job_usd
        ),
    )
    return RunPodTranscriber(client), RunPodAnalyzer(client, settings.analysis)


def run_claimed(db: Database, job: dict[str, Any]) -> dict[str, Any]:
    request = json.loads(job["request_json"])
    settings = Settings.model_validate(request["settings"])
    source = Path(request["source"])
    job_id = job["id"]
    attempt = job.get("attempts", 0) + 1
    directory = settings.data_dir / "jobs" / job_id
    directory.mkdir(parents=True, exist_ok=True)
    log = EventLog(directory / "events.jsonl")
    store = LocalArtifacts()
    media = MediaTools(settings.media, log)
    measurements = Measurements(log)
    started = time.perf_counter()
    report: dict[str, Any] = {
        "schema_version": 1,
        "job_id": job_id,
        "attempt": attempt,
        "mode": settings.mode,
        "started_at": utc_now(),
        "status": "running",
        "clips": [],
        "errors": [],
        "warnings": [],
        "benchmark": bool(request.get("benchmark")),
        "synthetic_ai": settings.mode == "mock",
        "python": platform.python_version(),
        "cached_stages": [],
        "publication_status": "disabled",
        "cloud_cost_usd": None,
    }
    transcriber = analyzer = None

    def checkpoint() -> None:
        if db.is_paused():
            raise JobPaused("worker paused at a stage boundary; resume to continue this job")

    log.emit("job_started", job_id=job_id, attempt=attempt, mode=settings.mode)
    audio = directory / "audio.wav"
    try:
        with measurements:
            checkpoint()
            with measurements.stage("capabilities"):
                report["media_versions"] = media.check_capabilities()
            with measurements.stage("ingestion"):
                info, source_hash = ingest_local(
                    source, request.get("authorized_local", False), media
                )
                if request.get("benchmark") and abs(info.duration - 600) > 30:
                    raise PipelineError("benchmark requires a 10-minute sample (600 ± 30 seconds)")
                report["source_duration_seconds"] = info.duration
                source_record = directory / "source.json"
                if source_record.exists():
                    previous = json.loads(source_record.read_text(encoding="utf-8"))
                    if previous["sha256"] != source_hash:
                        raise PipelineError(
                            "source changed since this job started; submit a new job"
                        )
                store.write_json(
                    source_record,
                    {
                        "path": str(source),
                        "sha256": source_hash,
                        "authorized_local": True,
                        "media": info.model_dump(),
                        "settings": request["settings"],
                    },
                )
                required = int(
                    info.duration * 32000
                    + settings.selection.max_clips * settings.selection.max_seconds * 1_000_000
                    + 256 * 1024 * 1024
                )
                if shutil.disk_usage(directory).free < required:
                    raise PipelineError(
                        "insufficient disk space for audio and estimated clip outputs"
                    )
            transcriber, analyzer = make_providers(settings, request, db, job_id)
            transcript_path = directory / "transcript.json"
            if transcript_path.is_file():
                transcript = Transcript.model_validate_json(
                    transcript_path.read_text(encoding="utf-8")
                )
                report["cached_stages"].extend(["audio_extraction", "transcription"])
            else:
                with measurements.stage("audio_extraction"):
                    if not audio.is_file():
                        temporary = directory / "audio.partial.wav"
                        try:
                            media.extract_audio(source, info, temporary)
                            temporary.replace(audio)
                        finally:
                            temporary.unlink(missing_ok=True)
                checkpoint()
                if settings.mode == "local" and settings.analysis.backend == "ollama":
                    with measurements.stage("release_qwen_before_transcription"):
                        analyzer.unload()
                with measurements.stage("transcription"):
                    transcript = transcriber.transcribe(audio, info.duration)
                    store.write_json(transcript_path, transcript.model_dump(mode="json"))
                    (directory / "transcript.txt").write_text(
                        "\n".join(
                            f"[{s.start:.3f}–{s.end:.3f}] {s.text}" for s in transcript.segments
                        ),
                        encoding="utf-8",
                    )
            checkpoint()  # Faster-Whisper's model is released before this boundary.
            analysis_path = directory / "analysis.json"
            if analysis_path.is_file():
                analysis = Analysis.model_validate_json(analysis_path.read_text(encoding="utf-8"))
                report["cached_stages"].append("analysis")
            else:
                with measurements.stage("analysis"):
                    try:
                        # Silence/empty ASR never causes model-generated speculative highlights.
                        analysis = (
                            analyzer.analyze(transcript)
                            if transcript.segments
                            else Analysis(
                                candidates=[], abstention_reason="No se detecto habla util."
                            )
                        )
                        if settings.mode == "local":
                            report["analysis_server_memory"] = analyzer.server_memory()
                        store.write_json(analysis_path, analysis.model_dump(mode="json"))
                    finally:
                        if settings.mode == "local" and settings.analysis.unload_after_analysis:
                            analyzer.unload()
            checkpoint()
            with measurements.stage("selection"):
                candidates = evaluate(analysis, transcript, settings.selection)
                existing = db.existing_clips(settings.mode)
                report["clips"] = [
                    item["metadata_path"] for item in existing if item["job_id"] == job_id
                ]
                selected = select(candidates, source_hash, existing, settings.selection)
                report["candidate_count"] = len(candidates)
                report["selected_this_attempt"] = len(selected)
                report["abstention_reason"] = analysis.abstention_reason
                store.write_json(
                    directory / "candidates.json", [c.model_dump(mode="json") for c in candidates]
                )
            for candidate in selected:
                checkpoint()
                clip_id = clip_identity(source_hash, candidate, settings.mode)
                clip_dir = directory / "clips" / clip_id
                clip_dir.mkdir(parents=True, exist_ok=True)
                with measurements.stage("subtitles"):
                    clipped = clip_transcript(transcript, candidate.start, candidate.end)
                    subtitles = write_subtitles(clipped, clip_dir)
                    store.write_json(clip_dir / "transcript.json", clipped.model_dump(mode="json"))
                render_start = time.perf_counter()
                with measurements.stage("clip_rendering"):
                    video = media.render(source, info, candidate.start, candidate.end, clip_dir)
                render_seconds = time.perf_counter() - render_start
                with measurements.stage("storage"):
                    video_hash = sha256_file(video)
                    metadata = ClipMetadata(
                        clip_id=clip_id,
                        job_id=job_id,
                        source_sha256=source_hash,
                        source_start=candidate.start,
                        source_end=candidate.end,
                        score=candidate.score,
                        score_weights=SCORE_WEIGHTS,
                        proposal=candidate.proposal,
                        transcript=clipped,
                        mode=settings.mode,
                        video_sha256=video_hash,
                        render_seconds=render_seconds,
                        framing=settings.media.framing,
                        artifacts={
                            "video": "video.mp4",
                            "transcript": "transcript.json",
                            **subtitles,
                        },
                    )
                    metadata_path = clip_dir / "metadata.json"
                    store.write_json(metadata_path, metadata.model_dump(mode="json"))
                    db.save_clip(
                        id=clip_id,
                        job_id=job_id,
                        source_hash=source_hash,
                        start=candidate.start,
                        end=candidate.end,
                        text=candidate.text,
                        video_hash=video_hash,
                        metadata_path=str(metadata_path),
                        mode=settings.mode,
                    )
                    report["clips"].append(str(metadata_path))
                    log.emit(
                        "clip_saved", clip_id=clip_id, score=candidate.score, seconds=render_seconds
                    )
            report["status"] = "completed"
    except JobPaused as error:
        report["status"] = "paused"
        report["warnings"].append(str(error))
        log.emit("job_paused", reason=str(error))
    except (Exception, KeyboardInterrupt) as error:
        # Do not leak model output, environment secrets, or unhandled library exception bodies.
        message = str(error) if isinstance(error, PipelineError) else error.__class__.__name__
        report["status"] = "failed"
        report["errors"].append({"type": error.__class__.__name__, "message": message})
        log.emit("job_failed", error_type=error.__class__.__name__, message=message)
    finally:
        report["stage_seconds"] = measurements.stages
        report["total_seconds"] = time.perf_counter() - started
        report["peak_process_tree_rss_bytes"] = measurements.peak_rss_bytes
        report["peak_device_gpu_used_mib"] = measurements.gpu_peak_used_mib
        report["gpu_memory_samples"] = measurements.gpu_samples
        report["memory_scope"] = (
            "Sampled Python/child-process RSS; excludes separate Ollama/llama.cpp. "
            "GPU metric is whole-device usage, including other applications."
        )
        if transcriber:
            report["transcription_metrics"] = transcriber.metrics
        if analyzer:
            report["analysis_metrics"] = analyzer.metrics
        seconds = measurements.stages.get("transcription")
        if seconds and report.get("source_duration_seconds"):
            report["transcription_realtime_factor"] = seconds / report["source_duration_seconds"]
            report["transcription_speed_x_realtime"] = report["source_duration_seconds"] / seconds
            report["speed_note"] = (
                "Mock fixture loading is not AI model speed"
                if settings.mode == "mock"
                else "Includes model load, decoding and word alignment"
            )
        report["finished_at"] = utc_now()
        report["report_path"] = str(directory / "report.json")
        store.write_json(directory / f"attempt-{attempt}.json", report)
        store.write_json(directory / "report.json", report)
        error = report["errors"][0]["message"] if report["errors"] else None
        db.finish(
            job_id,
            "queued" if report["status"] == "paused" else report["status"],
            directory / "report.json",
            error,
        )
        if report["status"] == "completed" and not settings.media.keep_audio:
            audio.unlink(missing_ok=True)
        log.emit("job_finished", status=report["status"], total_seconds=report["total_seconds"])
    return report
