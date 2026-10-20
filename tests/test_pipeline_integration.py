from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from alofoke_clips.config import MediaConfig, Settings, load_settings
from alofoke_clips.errors import MediaError, PipelineError
from alofoke_clips.media import MediaTools
from alofoke_clips.models import ClipMetadata
from alofoke_clips.pipeline import run_claimed
from alofoke_clips.publishing import BufferPublisher
from alofoke_clips.storage import Database


@pytest.fixture(scope="module")
def media_config():
    config = load_settings().media
    if not shutil.which(config.ffmpeg) or not shutil.which(config.ffprobe):
        pytest.skip("FFmpeg and FFprobe not available; see setup instructions")
    return MediaConfig(**(config.model_dump() | {"preset": "ultrafast", "fps": 10, "threads": 1}))


@pytest.fixture(scope="module")
def recording(tmp_path_factory, media_config):
    directory = tmp_path_factory.mktemp("source with spaces and 'apostrophe'")
    source = directory / "recording's sample.mp4"
    MediaTools(media_config).run(
        "ffmpeg",
        [
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x1c3150:s=640x360:r=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000",
            "-t",
            "22",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-threads",
            "1",
            "-c:a",
            "aac",
            str(source),
        ],
    )
    return source


def submit(db, settings, recording, fixtures, **overrides):
    request = {
        "source": str(recording),
        "authorized_local": True,
        "settings": settings.model_dump(mode="json"),
        "mock_transcript": str(fixtures[0]),
        "mock_analysis": str(fixtures[1]),
        **overrides,
    }
    identity = db.enqueue(request)
    claimed = db.claim(identity)
    assert claimed
    return run_claimed(db, claimed)


@pytest.mark.integration
def test_real_render_subtitles_metadata_and_persistent_duplicates(
    tmp_path, media_config, recording, fixture_paths
):
    settings = Settings(data_dir=tmp_path / "data", media=media_config)
    db = Database(settings.data_dir / "queue.sqlite3")
    report = submit(db, settings, recording, fixture_paths)
    assert report["status"] == "completed", report["errors"]
    assert len(report["clips"]) == 1
    metadata_path = Path(report["clips"][0])
    metadata = ClipMetadata.model_validate_json(metadata_path.read_text(encoding="utf-8"))
    assert metadata.review_required and metadata.publication_status == "disabled"
    assert metadata.transcript.is_mock
    assert metadata.score == 79
    info = MediaTools(media_config).validate(metadata_path.parent / "video.mp4")
    assert (info.width, info.height) == (1080, 1920)
    assert info.duration == pytest.approx(15.5, abs=0.25)
    assert metadata.video_sha256
    # This area is black padding before subtitles. White pixels prove real ASS burn-in occurred.
    pixels = subprocess.run(
        [
            media_config.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-threads",
            "1",
            "-ss",
            "3",
            "-i",
            str(metadata_path.parent / "video.mp4"),
            "-vf",
            "crop=900:260:90:1400,format=gray",
            "-frames:v",
            "1",
            "-threads",
            "1",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout
    assert max(pixels) > 180
    duplicate = submit(db, settings, recording, fixture_paths)
    assert duplicate["status"] == "completed"
    assert duplicate["selected_this_attempt"] == 0
    assert duplicate["clips"] == []
    assert (settings.data_dir / "jobs" / report["job_id"] / "events.jsonl").is_file()
    assert report["stage_seconds"]["clip_rendering"] > 0
    assert report["total_seconds"] > 0 and report["peak_process_tree_rss_bytes"] > 0


@pytest.mark.integration
def test_zero_highlights_and_invalid_input_report_errors(
    tmp_path, media_config, recording, fixture_paths
):
    empty = tmp_path / "empty.json"
    empty.write_text(
        '{"candidates":[],"abstention_reason":"Conversacion rutinaria."}', encoding="utf-8"
    )
    settings = Settings(data_dir=tmp_path / "data", media=media_config)
    db = Database(settings.data_dir / "queue.sqlite3")
    report = submit(db, settings, recording, (fixture_paths[0], empty))
    assert report["status"] == "completed" and report["clips"] == []
    invalid = tmp_path / "broken.mp4"
    invalid.write_bytes(b"not a video")
    failed = submit(db, settings, invalid, fixture_paths)
    assert failed["status"] == "failed"
    assert failed["errors"][0]["type"] == "MediaError"
    assert Path(failed["report_path"]).is_file()
    assert db.list_jobs()[-1]["status"] == "failed"


@pytest.mark.integration
def test_pause_retries_same_id_using_transcript_checkpoint(
    monkeypatch, tmp_path, media_config, recording, fixture_paths
):
    from alofoke_clips.providers.mock import MockTranscriber

    settings = Settings(data_dir=tmp_path / "data", media=media_config)
    db = Database(settings.data_dir / "queue.sqlite3")
    original = MockTranscriber.transcribe
    calls = []

    def pause_after_transcribing(self, audio, duration):
        calls.append("transcribe")
        result = original(self, audio, duration)
        db.set_paused(True)
        return result

    monkeypatch.setattr(MockTranscriber, "transcribe", pause_after_transcribing)
    report = submit(db, settings, recording, fixture_paths)
    assert report["status"] == "paused"
    assert db.list_jobs()[0]["status"] == "queued"
    db.set_paused(False)
    completed = run_claimed(db, db.claim(report["job_id"]))
    assert completed["status"] == "completed", completed["errors"]
    assert completed["job_id"] == report["job_id"]
    assert calls == ["transcribe"]
    assert "transcription" in completed["cached_stages"]


@pytest.mark.integration
def test_failure_can_retry_without_repeating_completed_ai_stages(
    monkeypatch, tmp_path, media_config, recording, fixture_paths
):
    settings = Settings(data_dir=tmp_path / "data", media=media_config)
    db = Database(settings.data_dir / "queue.sqlite3")
    original = MediaTools.render

    def fail(*args, **kwargs):
        raise MediaError("simulated renderer failure")

    monkeypatch.setattr(MediaTools, "render", fail)
    report = submit(db, settings, recording, fixture_paths)
    assert report["status"] == "failed"
    monkeypatch.setattr(MediaTools, "render", original)
    db.recover(report["job_id"])
    completed = run_claimed(db, db.claim(report["job_id"]))
    assert completed["status"] == "completed"
    assert completed["attempt"] == 2
    assert completed["cached_stages"] == ["audio_extraction", "transcription", "analysis"]


@pytest.mark.integration
def test_benchmark_refuses_non_ten_minute_sample(tmp_path, media_config, recording, fixture_paths):
    settings = Settings(data_dir=tmp_path / "data", media=media_config)
    report = submit(
        Database(settings.data_dir / "queue.sqlite3"),
        settings,
        recording,
        fixture_paths,
        benchmark=True,
    )
    assert report["status"] == "failed"
    assert "10-minute" in report["errors"][0]["message"]


@pytest.mark.parametrize("extension", [".m3u8", ".txt", ".concat"])
def test_remote_references_and_playlists_refused(tmp_path, extension):
    source = tmp_path / ("input" + extension)
    source.write_text("https://example.com/live")
    with pytest.raises(MediaError, match="extension"):
        MediaTools(MediaConfig()).validate(source)


def test_publishing_always_disabled():
    with pytest.raises(PipelineError, match="disabled"):
        BufferPublisher().publish("clip", "tiktok")
