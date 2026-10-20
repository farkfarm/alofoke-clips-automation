from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from alofoke_clips.models import Analysis, Transcript


@pytest.fixture(autouse=True)
def forbid_external_network(monkeypatch):
    """Tests may use loopback to exercise HTTP, but cannot spend money or download models."""
    original = socket.socket.connect

    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {"localhost", "127.0.0.1", "::1"}:
            raise AssertionError(f"external network forbidden in tests: {address[0]}")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)


@pytest.fixture
def transcript() -> Transcript:
    return Transcript.model_validate_json(
        (Path(__file__).parent / "fixtures/transcript.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def analysis() -> Analysis:
    return Analysis.model_validate_json(
        (Path(__file__).parent / "fixtures/analysis.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def fixture_paths() -> tuple[Path, Path]:
    root = Path(__file__).parent / "fixtures"
    return root / "transcript.json", root / "analysis.json"


def clone_json(model):
    return json.loads(model.model_dump_json())
