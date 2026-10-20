from pathlib import Path
from typing import Any, Protocol

from ..models import Analysis, Transcript


class Transcriber(Protocol):
    metrics: dict[str, Any]

    def transcribe(self, audio: Path, duration: float) -> Transcript: ...


class Analyzer(Protocol):
    metrics: dict[str, Any]

    def analyze(self, transcript: Transcript) -> Analysis: ...
