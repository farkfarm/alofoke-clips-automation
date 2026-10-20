from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Seconds = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Word(Record):
    start: Seconds
    end: Seconds
    text: Annotated[str, Field(min_length=1)]
    probability: Probability = 1.0

    @model_validator(mode="after")
    def valid_range(self) -> Self:
        if self.end <= self.start:
            raise ValueError("word end must be after start")
        return self


class Segment(Record):
    id: Annotated[str, Field(min_length=1, max_length=80)]
    start: Seconds
    end: Seconds
    text: Annotated[str, Field(min_length=1, max_length=20000)]
    words: list[Word] = Field(default_factory=list)
    no_speech_probability: Probability = 0.0
    avg_logprob: Annotated[float, Field(allow_inf_nan=False)] = 0.0

    @model_validator(mode="after")
    def valid_range(self) -> Self:
        if self.end <= self.start:
            raise ValueError("segment end must be after start")
        previous = self.start
        for word in self.words:
            if word.start < previous - 0.001 or word.end > self.end + 0.05:
                raise ValueError("word timestamps must be ordered and inside the segment")
            previous = word.end
        return self


class Transcript(Record):
    schema_version: Literal[1] = 1
    language: Literal["es"] = "es"
    duration: Seconds
    provider: str
    is_mock: bool = False
    segments: list[Segment]

    @model_validator(mode="after")
    def valid_segments(self) -> Self:
        seen: set[str] = set()
        previous = 0.0
        for segment in self.segments:
            if segment.id in seen:
                raise ValueError("duplicate segment id")
            if segment.start < previous or segment.end > self.duration + 0.1:
                raise ValueError("segment timestamps must be ordered and inside the recording")
            seen.add(segment.id)
            previous = segment.start
        return self


class Factor(Record):
    value: Annotated[int, Field(ge=0, le=5, strict=True)]
    reason: Annotated[str, Field(min_length=8, max_length=600)]


class Factors(Record):
    hook: Factor
    emotion: Factor
    novelty: Factor
    payoff: Factor
    context: Factor


class Evidence(Record):
    segment_id: str
    quote: Annotated[str, Field(min_length=8, max_length=2000)]


class Proposal(Record):
    segment_ids: Annotated[list[str], Field(min_length=1, max_length=100)]
    category: Literal["conflicto", "revelacion", "humor", "emocion", "logro", "otro"]
    title: Annotated[str, Field(min_length=5, max_length=120)]
    caption: Annotated[str, Field(min_length=8, max_length=1200)]
    confidence: Probability
    factors: Factors
    evidence: Annotated[list[Evidence], Field(min_length=1, max_length=12)]


class Analysis(Record):
    candidates: Annotated[list[Proposal], Field(max_length=2000)]
    abstention_reason: Annotated[str, Field(max_length=1500)]


class MediaInfo(Record):
    duration: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]
    video_index: int
    audio_index: int
    video_codec: str
    audio_codec: str
    size_bytes: int
    fps: Annotated[float, Field(gt=0, allow_inf_nan=False)]


class Candidate(Record):
    id: str
    start: Seconds
    end: Seconds
    score: float
    proposal: Proposal
    text: str
    decision: str = "pending"
    duplicate_of: str | None = None


class ClipMetadata(Record):
    schema_version: Literal[1] = 1
    clip_id: str
    job_id: str
    source_sha256: str
    source_start: Seconds
    source_end: Seconds
    score: float
    score_weights: dict[str, int]
    proposal: Proposal
    transcript: Transcript
    mode: Literal["mock", "local", "gpu"]
    review_required: Literal[True] = True
    publication_status: Literal["disabled"] = "disabled"
    video_sha256: str
    render_seconds: float
    framing: str
    artifacts: dict[str, str]
