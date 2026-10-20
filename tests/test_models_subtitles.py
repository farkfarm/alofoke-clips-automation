import pytest
from pydantic import ValidationError

from alofoke_clips.config import AnalysisConfig, SelectionConfig
from alofoke_clips.models import Segment, Transcript, Word
from alofoke_clips.subtitles import _timestamp, clip_transcript, subtitle_cues, write_subtitles


@pytest.mark.parametrize(
    "start,end", [(1, 0), (1, 1), (0, float("nan")), (0, float("inf")), (-1, 2)]
)
def test_bad_timestamps_rejected(start, end):
    with pytest.raises(ValidationError):
        Segment(id="s", start=start, end=end, text="texto")


def test_word_times_must_be_inside_segment():
    with pytest.raises(ValidationError):
        Segment(id="s", start=1, end=2, text="hola", words=[Word(start=0, end=1.5, text="hola")])


def test_transcript_ids_unique(transcript):
    raw = transcript.model_dump()
    raw["segments"].append(raw["segments"][0])
    with pytest.raises(ValidationError):
        Transcript.model_validate(raw)


def test_word_subtitles_use_relative_timestamps(transcript, tmp_path):
    transcript.segments[0].words = [
        Word(start=2, end=3, text="Hola"),
        Word(start=3, end=4, text="equipo"),
    ]
    clipped = clip_transcript(transcript, 1.75, 17.25)
    assert clipped.segments[0].words[0].start == 0.25
    cues = subtitle_cues(clipped)
    assert cues[0][:2] == (0.25, 2.25)
    write_subtitles(clipped, tmp_path)
    assert "00:00:00,250 --> 00:00:02,250" in (tmp_path / "subtitles.srt").read_text()


def test_subtitle_injection_neutralized(tmp_path):
    transcript = Transcript(
        duration=5,
        provider="mock",
        segments=[Segment(id="s", start=0, end=5, text=r"Hola {\pos(0,0)} mundo\N <b>prueba</b>")],
    )
    write_subtitles(transcript, tmp_path)
    ass = (tmp_path / "subtitles.ass").read_text(encoding="utf-8")
    assert r"{\pos" not in ass
    assert "&lt;b&gt;" in (tmp_path / "subtitles.srt").read_text(encoding="utf-8")


def test_timestamp_carry():
    assert _timestamp(59.9996) == "00:01:00,000"
    assert _timestamp(59.996, ass=True) == "0:01:00.00"


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example.com",
        "http://192.168.1.2:11434",
        "http://user:secret@localhost:11434",
        "http://localhost/path",
    ],
)
def test_local_provider_cannot_use_remote_cloud(url):
    with pytest.raises(ValidationError):
        AnalysisConfig(base_url=url)


def test_invalid_config_ranges():
    with pytest.raises(ValidationError):
        AnalysisConfig(window_seconds=60, overlap_seconds=60)
    with pytest.raises(ValidationError):
        SelectionConfig(min_seconds=60, max_seconds=15)
