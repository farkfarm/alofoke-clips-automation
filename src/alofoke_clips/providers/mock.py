from pathlib import Path
from typing import Any

from ..errors import ProviderError
from ..models import Analysis, Transcript


class MockTranscriber:
    def __init__(self, fixture: Path):
        self.fixture = fixture
        self.metrics: dict[str, Any] = {"provider": "mock", "model_loaded": False}

    def transcribe(self, audio: Path, duration: float) -> Transcript:
        transcript = Transcript.model_validate_json(self.fixture.read_text(encoding="utf-8"))
        if transcript.segments and max(s.end for s in transcript.segments) > duration + 0.1:
            raise ProviderError("mock transcript extends beyond the supplied recording")
        return transcript.model_copy(
            update={"provider": "mock", "is_mock": True, "duration": duration}
        )


class MockAnalyzer:
    def __init__(self, fixture: Path):
        self.fixture = fixture
        self.metrics: dict[str, Any] = {"provider": "mock", "model_loaded": False}

    def analyze(self, transcript: Transcript) -> Analysis:
        return Analysis.model_validate_json(self.fixture.read_text(encoding="utf-8"))
