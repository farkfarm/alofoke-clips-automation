import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from alofoke_clips.config import AnalysisConfig, GPUConfig, Settings, TranscriptionConfig
from alofoke_clips.errors import ConfigurationError, ProviderError
from alofoke_clips.models import Segment, Transcript
from alofoke_clips.pipeline import make_providers
from alofoke_clips.providers.faster_whisper import FasterWhisperTranscriber
from alofoke_clips.providers.mock import MockTranscriber
from alofoke_clips.providers.qwen import QwenAnalyzer, transcript_windows
from alofoke_clips.providers.runpod import RunPodClient
from alofoke_clips.storage import Database


class FakeHTTP:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, url, payload, timeout, token=None):
        self.calls.append((url, payload))
        return self.responses.pop(0)


@pytest.mark.parametrize("backend", ["ollama", "llama_cpp"])
def test_qwen_schema_output_and_span_contract(transcript, analysis, backend):
    response = (
        {"done": True, "response": analysis.model_dump_json(), "eval_count": 99}
        if backend == "ollama"
        else {
            "choices": [
                {"finish_reason": "stop", "message": {"content": analysis.model_dump_json()}}
            ]
        }
    )
    http = FakeHTTP([response])
    analyzer = QwenAnalyzer(AnalysisConfig(backend=backend), http)
    result = analyzer.analyze(transcript)
    assert len(result.candidates) == 1
    payload = http.calls[0][1]
    assert "schema" in json.dumps(payload)
    if backend == "ollama":
        assert payload["think"] is False
        assert "pull" not in http.calls[0][0]


@pytest.mark.parametrize(
    "response",
    [
        {"done": True, "response": "not JSON"},
        {"done": True, "done_reason": "length", "response": "{}"},
        {"done": False, "response": "{}"},
    ],
)
def test_bad_qwen_output_fails_closed(transcript, response):
    with pytest.raises(ProviderError):
        QwenAnalyzer(AnalysisConfig(), FakeHTTP([response])).analyze(transcript)


def test_unknown_qwen_segment_ids_rejected(transcript, analysis):
    analysis.candidates[0].segment_ids = ["invented"]
    http = FakeHTTP([{"done": True, "response": analysis.model_dump_json()}])
    with pytest.raises(ProviderError, match="outside"):
        QwenAnalyzer(AnalysisConfig(), http).analyze(transcript)


def test_long_recording_windows_cover_segments():
    segments = [
        Segment(id=f"s{i}", start=i * 5, end=i * 5 + 5, text="Texto de prueba.") for i in range(720)
    ]
    transcript = Transcript(duration=3600, provider="test", segments=segments)
    windows = list(transcript_windows(transcript, AnalysisConfig()))
    assert {s.id for w in windows for s in w} == {s.id for s in segments}
    assert len(windows) > 20
    assert all(w[-1].end - w[0].start <= 180 for w in windows)
    assert set(s.id for s in windows[0]) & set(s.id for s in windows[1])


def test_character_limit_does_not_drop_segments():
    transcript = Transcript(
        duration=50,
        provider="test",
        segments=[
            Segment(id=f"s{i}", start=i * 5, end=i * 5 + 5, text="palabra " * 80) for i in range(10)
        ],
    )
    config = AnalysisConfig(max_window_chars=1000)
    windows = list(transcript_windows(transcript, config))
    assert {s.id for w in windows for s in w} == {s.id for s in transcript.segments}


def test_missing_whisper_weights_never_download(tmp_path):
    transcriber = FasterWhisperTranscriber(TranscriptionConfig(model_path=tmp_path))
    with pytest.raises(ProviderError, match="automatic downloads are disabled"):
        transcriber.transcribe(Path("no-audio.wav"), 22)


def test_cuda_fallback_and_model_release(monkeypatch, tmp_path):
    (tmp_path / "model.bin").write_bytes(b"fake")
    events = []

    class FakeModel:
        def __init__(self, *args, **kwargs):
            events.append(kwargs)
            if kwargs["device"] == "cuda":
                raise RuntimeError("CUDA runtime unavailable")

        def transcribe(self, *args, **kwargs):
            assert kwargs["language"] == "es" and kwargs["word_timestamps"]
            segment = SimpleNamespace(
                text="Hola equipo", start=1, end=3, words=[], no_speech_prob=0.1, avg_logprob=-0.1
            )
            return iter([segment]), SimpleNamespace(language_probability=0.9)

        def __del__(self):
            events.append("released")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))
    transcriber = FasterWhisperTranscriber(
        TranscriptionConfig(model_path=tmp_path, device="cuda", compute_type="int8_float16")
    )
    result = transcriber.transcribe(Path("fake.wav"), 22)
    assert len(result.segments) == 1
    assert transcriber.metrics["cpu_fallback_used"] is True
    assert transcriber.metrics["device"] == "cpu"
    assert events[0]["local_files_only"] is True
    assert events[-1] == "released"


def test_unload_ollama_only_for_managed_model():
    http = FakeHTTP([{"models": [{"name": "qwen3:4b"}]}, {"done": True}])
    QwenAnalyzer(AnalysisConfig(), http).unload()
    assert http.calls[1][1]["keep_alive"] == 0
    assert not http.responses


def test_mock_rejects_fixture_outside_source(fixture_paths):
    with pytest.raises(ProviderError, match="beyond"):
        MockTranscriber(fixture_paths[0]).transcribe(Path("unused.wav"), 5)


def test_cloud_disabled_even_if_credentials_exist(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-only-placeholder")
    with pytest.raises(ProviderError, match="disabled"):
        RunPodClient(GPUConfig(), False, lambda amount: None)
    db = Database(tmp_path / "queue.sqlite3")
    with pytest.raises(ConfigurationError, match="GPU requires"):
        make_providers(Settings(mode="gpu"), {"allow_paid_gpu": False}, db, "job")


def test_runpod_client_contract_budget_and_status(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-only-placeholder")
    reservations = []
    http = FakeHTTP(
        [
            {"id": "job-1", "status": "IN_QUEUE"},
            {"status": "COMPLETED", "output": {"value": "ok"}, "executionTime": 100},
        ]
    )
    client = RunPodClient(
        GPUConfig(allow_paid=True, endpoint_id="test", poll_seconds=0.01, usd_per_second=0.0001),
        True,
        lambda amount: reservations.append(amount) or "reservation",
        http,
    )
    assert client.execute({"task": "test"}) == {"value": "ok"}
    assert reservations == pytest.approx([0.09])
    assert http.calls[0][0] == "https://api.runpod.ai/v2/test/run"
    assert client.metrics["jobs"][0]["budget_reservation"] == "reservation"
