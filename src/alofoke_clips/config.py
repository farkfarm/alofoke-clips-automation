from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic import Field, model_validator

from .errors import ConfigurationError
from .models import Record


class MediaConfig(Record):
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    timeout_seconds: int = Field(default=7200, ge=1, le=86400)
    max_input_hours: float = Field(default=8, gt=0, le=48, allow_inf_nan=False)
    threads: int = Field(default=2, ge=1, le=64)
    preset: Literal["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"] = (
        "veryfast"
    )
    crf: int = Field(default=21, ge=0, le=40)
    framing: Literal["fit", "crop"] = "fit"
    fps: int = Field(default=30, ge=1, le=60)
    keep_audio: bool = False


class TranscriptionConfig(Record):
    model_path: Path = Path("models/faster-whisper-small")
    device: Literal["cpu", "cuda"] = "cpu"
    compute_type: Literal["int8", "int8_float16", "float16", "float32"] = "int8"
    cpu_threads: int = Field(default=4, ge=1, le=64)
    beam_size: int = Field(default=5, ge=1, le=10)
    cpu_fallback: bool = True


class AnalysisConfig(Record):
    backend: Literal["ollama", "llama_cpp"] = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3:4b"
    timeout_seconds: int = Field(default=600, ge=1, le=7200)
    window_seconds: int = Field(default=180, ge=30, le=1200)
    overlap_seconds: int = Field(default=60, ge=0)
    max_window_chars: int = Field(default=18000, ge=1000, le=100000)
    max_output_tokens: int = Field(default=4096, ge=256, le=16000)
    max_candidates_per_window: int = Field(default=4, ge=1, le=20)
    unload_after_analysis: bool = True

    @model_validator(mode="after")
    def validate_local_endpoint(self) -> Self:
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("LOCAL analysis endpoint must be HTTP on loopback")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("analysis URL cannot contain credentials, queries, or fragments")
        if parsed.path not in {"", "/"}:
            raise ValueError("base_url must contain only scheme, loopback host, and port")
        if self.overlap_seconds >= self.window_seconds:
            raise ValueError("analysis overlap must be shorter than its window")
        return self


class SelectionConfig(Record):
    min_seconds: float = Field(default=15, gt=0, le=180)
    max_seconds: float = Field(default=60, gt=0, le=180)
    max_clips: int = Field(default=5, ge=0, le=50)
    min_score: float = Field(default=70, ge=0, le=100)
    min_confidence: float = Field(default=0.75, ge=0, le=1)
    min_words: int = Field(default=15, ge=1)
    min_speech_ratio: float = Field(default=0.35, ge=0, le=1)
    padding_seconds: float = Field(default=0.25, ge=0, le=2)
    text_duplicate_threshold: float = Field(default=0.88, ge=0.5, le=1)

    @model_validator(mode="after")
    def validate_duration(self) -> Self:
        if self.min_seconds > self.max_seconds:
            raise ValueError("min_seconds exceeds max_seconds")
        return self


class GPUConfig(Record):
    allow_paid: bool = False
    endpoint_id: str = ""
    timeout_seconds: int = Field(default=900, ge=1, le=7200)
    poll_seconds: float = Field(default=2, ge=0.01, le=30)
    audio_chunk_seconds: int = Field(default=45, ge=1, le=60)
    usd_per_second: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    monthly_budget_usd: float = Field(default=50, ge=0, le=100, allow_inf_nan=False)
    max_job_usd: float = Field(default=2, gt=0, le=100, allow_inf_nan=False)


class Settings(Record):
    mode: Literal["mock", "local", "gpu"] = "mock"
    data_dir: Path = Path("data")
    media: MediaConfig = Field(default_factory=MediaConfig)
    transcription: TranscriptionConfig = Field(default_factory=TranscriptionConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    selection: SelectionConfig = Field(default_factory=SelectionConfig)
    gpu: GPUConfig = Field(default_factory=GPUConfig)


def load_settings(path: Path | None = None) -> Settings:
    root = path.resolve().parent if path else Path.cwd()
    # Only an explicitly located workspace env file; never search parent directories.
    load_dotenv(root / ".env", override=False)
    raw = tomllib.loads(path.read_text(encoding="utf-8")) if path else {}
    settings = Settings.model_validate(raw)
    settings.data_dir = (root / settings.data_dir).resolve()
    settings.transcription.model_path = (root / settings.transcription.model_path).resolve()
    settings.media.ffmpeg = os.environ.get("ALOFOKE_FFMPEG") or settings.media.ffmpeg
    settings.media.ffprobe = os.environ.get("ALOFOKE_FFPROBE") or settings.media.ffprobe
    for name in ("ffmpeg", "ffprobe"):
        value = getattr(settings.media, name)
        if "/" in value or "\\" in value:
            setattr(settings.media, name, str((root / value).resolve()))
    return settings


def require_gpu_permission(settings: Settings, per_run_approval: bool) -> None:
    if settings.mode == "gpu" and not (settings.gpu.allow_paid and per_run_approval):
        raise ConfigurationError(
            "GPU requires gpu.allow_paid=true AND --allow-paid-gpu for this run"
        )
