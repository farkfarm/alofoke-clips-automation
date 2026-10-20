from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from .config import MediaConfig
from .errors import MediaError
from .models import MediaInfo
from .observability import EventLog


class MediaTools:
    def __init__(self, config: MediaConfig, log: EventLog | None = None):
        self.config = config
        self.log = log

    def executable(self, name: str) -> str:
        configured = getattr(self.config, name)
        found = shutil.which(configured)
        if not found:
            raise MediaError(f"{name} executable missing; install FFmpeg or configure its path")
        return found

    def run(self, name: str, args: list[str], cwd: Path | None = None) -> str:
        import time

        started = time.perf_counter()
        try:
            result = subprocess.run(
                [self.executable(name), *args],
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=self.config.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise MediaError(f"{name} timed out after {self.config.timeout_seconds}s") from error
        except OSError as error:
            raise MediaError(f"could not start {name}: {error.__class__.__name__}") from error
        if self.log:
            self.log.emit(
                "media_command",
                tool=name,
                seconds=time.perf_counter() - started,
                returncode=result.returncode,
            )
        if result.returncode:
            raise MediaError(f"{name} exited {result.returncode}: {result.stderr[-3000:].strip()}")
        return result.stdout

    def validate(self, path: Path) -> MediaInfo:
        if re.match(r"^[a-zA-Z]+://", str(path)) or not path.is_file():
            raise MediaError("input must be an existing local file")
        if path.suffix.lower() not in {".mp4", ".mkv", ".mov", ".webm", ".m4v", ".ts", ".avi"}:
            raise MediaError(
                "unsupported recording extension; playlists and remote sources are disabled"
            )
        try:
            raw = json.loads(
                self.run(
                    "ffprobe",
                    [
                        "-v",
                        "error",
                        "-protocol_whitelist",
                        "file,pipe",
                        "-show_streams",
                        "-show_format",
                        "-of",
                        "json",
                        str(path.resolve()),
                    ],
                )
            )
            formats = set(raw["format"]["format_name"].split(","))
            if not formats & {"mov", "mp4", "matroska", "webm", "mpegts", "avi"}:
                raise MediaError("unsupported recording container")
            videos = [
                s
                for s in raw["streams"]
                if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")
            ]
            audios = [s for s in raw["streams"] if s["codec_type"] == "audio"]
            if not videos or not audios:
                raise MediaError("recording must contain a video stream and an audio stream")
            video, audio = videos[0], audios[0]
            info = MediaInfo(
                duration=float(raw["format"]["duration"]),
                width=int(video["width"]),
                height=int(video["height"]),
                video_index=int(video["index"]),
                audio_index=int(audio["index"]),
                video_codec=video["codec_name"],
                audio_codec=audio["codec_name"],
                size_bytes=path.stat().st_size,
                fps=float(Fraction(video.get("avg_frame_rate", "0/1"))),
            )
        except (KeyError, ValueError, ZeroDivisionError, TypeError) as error:
            raise MediaError(f"invalid FFprobe result: {error.__class__.__name__}") from error
        if info.duration > self.config.max_input_hours * 3600:
            raise MediaError("recording exceeds configured max_input_hours")
        if info.width * info.height > 7680 * 4320:
            raise MediaError("recording exceeds the supported 8K frame size")
        return info

    def check_capabilities(self) -> dict[str, str]:
        versions = {
            name: self.run(name, ["-version"]).splitlines()[0] for name in ("ffmpeg", "ffprobe")
        }
        filters = self.run("ffmpeg", ["-hide_banner", "-filters"])
        encoders = self.run("ffmpeg", ["-hide_banner", "-encoders"])
        if (
            not re.search(r"\bass\s+", filters)
            or "libx264" not in encoders
            or " aac " not in encoders
        ):
            raise MediaError("FFmpeg requires libass (ass filter), libx264, and AAC")
        return versions

    def extract_audio(self, source: Path, info: MediaInfo, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        self.run(
            "ffmpeg",
            [
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(source.resolve()),
                "-map",
                f"0:{info.audio_index}",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                # Keep audio aligned with the source timeline, including an initial A/V offset.
                "-af",
                "aresample=async=1:first_pts=0",
                "-c:a",
                "pcm_s16le",
                str(output.resolve()),
            ],
        )

    def render(
        self, source: Path, info: MediaInfo, start: float, end: float, directory: Path
    ) -> Path:
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= info.duration):
            raise MediaError("invalid render time range")
        scale = "increase" if self.config.framing == "crop" else "decrease"
        framing = (
            "crop=1080:1920"
            if self.config.framing == "crop"
            else "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black"
        )
        filters = (
            "scale=trunc(iw*sar/2)*2:ih,setsar=1,"
            f"scale=1080:1920:force_original_aspect_ratio={scale}:force_divisible_by=2,"
            f"{framing},setsar=1,fps={self.config.fps},ass=filename=subtitles.ass"
        )
        output = directory / "video.mp4"
        temporary = directory / "video.partial.mp4"
        try:
            self.run(
                "ffmpeg",
                [
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-nostdin",
                    "-y",
                    "-filter_threads",
                    str(self.config.threads),
                    "-protocol_whitelist",
                    "file,pipe",
                    "-ss",
                    f"{start:.6f}",
                    "-i",
                    str(source.resolve()),
                    "-t",
                    f"{end - start:.6f}",
                    "-map",
                    f"0:{info.video_index}",
                    "-map",
                    f"0:{info.audio_index}",
                    "-vf",
                    filters,
                    "-c:v",
                    "libx264",
                    "-preset",
                    self.config.preset,
                    "-crf",
                    str(self.config.crf),
                    "-threads",
                    str(self.config.threads),
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    "-map_metadata",
                    "-1",
                    "-map_chapters",
                    "-1",
                    "-movflags",
                    "+faststart",
                    str(temporary.resolve()),
                ],
                cwd=directory,
            )
            rendered = self.validate(temporary)
            if (rendered.width, rendered.height) != (1080, 1920):
                raise MediaError("render did not produce 1080x1920")
            if abs(rendered.duration - (end - start)) > max(0.25, 2 / self.config.fps):
                raise MediaError("render duration differs from the selected range")
            temporary.replace(output)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return output
