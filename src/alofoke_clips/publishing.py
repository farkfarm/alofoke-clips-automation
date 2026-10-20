from typing import Literal, Protocol

from .errors import PipelineError

Platform = Literal["facebook", "instagram", "tiktok", "x"]


class Publisher(Protocol):
    def publish(self, clip_id: str, platform: Platform) -> str: ...


class BufferPublisher:
    """Boundary for the sole permitted automated publisher. No network implementation in M1."""

    def publish(self, clip_id: str, platform: Platform) -> str:
        raise PipelineError(
            "Publishing is disabled in Milestone 1; future publishing must use Buffer"
        )
