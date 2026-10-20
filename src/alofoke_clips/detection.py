from __future__ import annotations

import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from .config import SelectionConfig
from .models import Analysis, Candidate, Proposal, Transcript

SCORE_WEIGHTS = {"hook": 25, "emotion": 20, "novelty": 20, "payoff": 20, "context": 15}


def engagement_score(proposal: Proposal) -> float:
    return round(
        sum(
            getattr(proposal.factors, name).value * weight / 5
            for name, weight in SCORE_WEIGHTS.items()
        ),
        2,
    )


def normalized_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.findall(r"\w+", text, re.UNICODE))


def text_similarity(left: str, right: str) -> float:
    left, right = normalized_text(left), normalized_text(right)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    def shingles(text: str) -> set[tuple[str, ...]]:
        words = text.split()
        return {tuple(words[i : i + 3]) for i in range(max(0, len(words) - 2))}

    a, b = shingles(left), shingles(right)
    jaccard = len(a & b) / len(a | b) if a and b else 0
    return max(jaccard, SequenceMatcher(None, left, right, autojunk=False).ratio())


def overlap_ratio(start: float, end: float, other_start: float, other_end: float) -> float:
    return max(0.0, min(end, other_end) - max(start, other_start)) / min(
        end - start, other_end - other_start
    )


def _quote_normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def evaluate(
    analysis: Analysis, transcript: Transcript, config: SelectionConfig
) -> list[Candidate]:
    by_id = {segment.id: (i, segment) for i, segment in enumerate(transcript.segments)}
    output = []
    for number, proposal in enumerate(analysis.candidates):
        score = engagement_score(proposal)
        candidate = Candidate(
            id=f"candidate-{number:04d}", start=0, end=0, score=score, proposal=proposal, text=""
        )
        output.append(candidate)
        if len(set(proposal.segment_ids)) != len(proposal.segment_ids) or any(
            segment_id not in by_id for segment_id in proposal.segment_ids
        ):
            candidate.decision = "rejected: unknown or repeated segment ids"
            continue
        indexed = [by_id[s] for s in proposal.segment_ids]
        positions = [i for i, _ in indexed]
        if positions != list(range(positions[0], positions[-1] + 1)):
            candidate.decision = "rejected: non-contiguous or unordered segments"
            continue
        segments = [segment for _, segment in indexed]
        start, end = segments[0].start, max(s.end for s in segments)
        candidate.start = max(0, start - config.padding_seconds)
        candidate.end = min(transcript.duration, end + config.padding_seconds)
        candidate.text = " ".join(segment.text for segment in segments)
        # Cap context padding without truncating spoken content at the duration boundary.
        if (
            candidate.end - candidate.start > config.max_seconds
            and end - start <= config.max_seconds
        ):
            candidate.start, candidate.end = start, end
        duration = candidate.end - candidate.start
        selected_ids = set(proposal.segment_ids)
        if any(
            e.segment_id not in selected_ids
            or _quote_normalized(e.quote) not in _quote_normalized(by_id[e.segment_id][1].text)
            for e in proposal.evidence
        ):
            candidate.decision = "rejected: evidence not found in selected transcript"
        elif not config.min_seconds <= duration <= config.max_seconds:
            candidate.decision = "rejected: duration outside configured limits"
        elif len(candidate.text.split()) < config.min_words:
            candidate.decision = "rejected: insufficient speech"
        elif any(s.no_speech_probability > 0.6 or s.avg_logprob < -1.0 for s in segments):
            candidate.decision = "rejected: unreliable transcription"
        elif any(
            s.words and sum(w.probability for w in s.words) / len(s.words) < 0.5 for s in segments
        ):
            candidate.decision = "rejected: low word confidence"
        elif _speech_duration(segments) / duration < config.min_speech_ratio:
            candidate.decision = "rejected: excessive silence"
        elif proposal.confidence < config.min_confidence:
            candidate.decision = "rejected: low analysis confidence"
        elif proposal.factors.context.value < 3 or proposal.factors.payoff.value < 3:
            candidate.decision = "rejected: insufficient context or payoff"
        elif score < config.min_score:
            candidate.decision = "rejected: below engagement threshold"
        else:
            candidate.decision = "eligible"
    return output


def _speech_duration(segments: list) -> float:
    intervals = sorted((w.start, w.end) for s in segments for w in s.words)
    if not intervals:
        intervals = sorted((s.start, s.end) for s in segments)
    total = 0.0
    previous_end = 0.0
    for start, end in intervals:
        total += max(0, end - max(start, previous_end))
        previous_end = max(previous_end, end)
    return total


def select(
    candidates: list[Candidate],
    source_hash: str,
    existing: list[dict[str, Any]],
    config: SelectionConfig,
) -> list[Candidate]:
    selected: list[Candidate] = []
    for candidate in sorted(candidates, key=lambda c: (-c.score, c.start, c.id)):
        if candidate.decision != "eligible":
            continue
        duplicate = None
        for other in existing:
            if (
                other["source_hash"] == source_hash
                and overlap_ratio(candidate.start, candidate.end, other["start"], other["end"])
                >= 0.7
                or text_similarity(candidate.text, other["text"]) >= config.text_duplicate_threshold
            ):
                duplicate = other["id"]
                break
        for other in selected:
            if overlap_ratio(candidate.start, candidate.end, other.start, other.end) >= 0.3 or (
                text_similarity(candidate.text, other.text) >= config.text_duplicate_threshold
            ):
                duplicate = other.id
                break
        if duplicate:
            candidate.decision = "rejected: duplicate or overlapping highlight"
            candidate.duplicate_of = duplicate
        elif len(selected) >= config.max_clips:
            candidate.decision = "rejected: quality-ranked clip limit"
        else:
            candidate.decision = "selected"
            selected.append(candidate)
    return selected


def clip_identity(source_hash: str, candidate: Candidate, mode: str) -> str:
    key = f"{source_hash}:{candidate.start:.6f}:{candidate.end:.6f}:{mode}"
    return hashlib.sha256(key.encode()).hexdigest()[:24]
