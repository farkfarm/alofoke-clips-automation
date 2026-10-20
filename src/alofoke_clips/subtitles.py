from __future__ import annotations

import html
import math
import re
import textwrap
from pathlib import Path

from .models import Segment, Transcript, Word


def clip_transcript(transcript: Transcript, start: float, end: float) -> Transcript:
    output = []
    for segment in transcript.segments:
        if segment.end <= start or segment.start >= end:
            continue
        words = [
            Word(
                start=max(w.start, start) - start,
                end=min(w.end, end) - start,
                text=w.text,
                probability=w.probability,
            )
            for w in segment.words
            if w.end > start and w.start < end
        ]
        output.append(
            Segment(
                id=segment.id,
                start=max(segment.start, start) - start,
                end=min(segment.end, end) - start,
                text=segment.text,
                words=words,
                no_speech_probability=segment.no_speech_probability,
                avg_logprob=segment.avg_logprob,
            )
        )
    return Transcript(
        duration=end - start,
        provider=transcript.provider,
        is_mock=transcript.is_mock,
        segments=output,
    )


def subtitle_cues(transcript: Transcript) -> list[tuple[float, float, str]]:
    cues = []
    for segment in transcript.segments:
        # Use actual ASR word timing when available. Segment-only input is labelled in metadata.
        if segment.words:
            group: list[Word] = []
            for word in segment.words:
                prospective = " ".join([*(w.text for w in group), word.text])
                if group and (
                    len(prospective) > 64
                    or word.end - group[0].start > 4.0
                    or word.start - group[-1].end > 0.6
                ):
                    cues.append((group[0].start, group[-1].end, " ".join(w.text for w in group)))
                    group = []
                group.append(word)
            if group:
                cues.append((group[0].start, group[-1].end, " ".join(w.text for w in group)))
        else:
            # No fabricated per-word alignment: keep the known segment's full time interval.
            cues.append((segment.start, segment.end, segment.text))
    output = []
    for start, end, text in sorted(cues):
        text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
        wrapped = "\n".join(textwrap.wrap(text, width=32, break_long_words=True))
        # Split overlong segment-only cues into balanced blocks with explicit interpolation.
        lines = wrapped.splitlines()
        blocks = ["\n".join(lines[i : i + 2]) for i in range(0, len(lines), 2)]
        for index, block in enumerate(blocks):
            block_start = start + (end - start) * index / len(blocks)
            block_end = start + (end - start) * (index + 1) / len(blocks)
            if output and block_start < output[-1][1]:
                block_start = output[-1][1]
            if round(block_end * 100) > round(block_start * 100):
                output.append((block_start, min(block_end, transcript.duration), block))
    return output


def _timestamp(seconds: float, ass: bool = False) -> str:
    units = 100 if ass else 1000
    ticks = max(0, math.floor(seconds * units + 0.5))
    hours, rest = divmod(ticks, 3600 * units)
    minutes, rest = divmod(rest, 60 * units)
    secs, fraction = divmod(rest, units)
    return (
        f"{hours}:{minutes:02}:{secs:02}.{fraction:02}"
        if ass
        else f"{hours:02}:{minutes:02}:{secs:02},{fraction:03}"
    )


def write_subtitles(transcript: Transcript, directory: Path) -> dict[str, str]:
    cues = subtitle_cues(transcript)
    srt = "\n\n".join(
        f"{i}\n{_timestamp(start)} --> {_timestamp(end)}\n{html.escape(text, quote=False)}"
        for i, (start, end, text) in enumerate(cues, 1)
    )
    (directory / "subtitles.srt").write_text(srt + "\n", encoding="utf-8")
    style_fields = (
        "Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
    )
    style = (
        "Default,Arial,56,&H00FFFFFF,&H000000FF,&H00101010,&H90000000,"
        "-1,0,0,0,100,100,0,0,1,3,1,2,90,90,300,1"
    )
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: {style_fields}
Style: {style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for start, end, text in cues:
        # Neutralize ASS override tags and escape sequences supplied by speech/model text.
        safe = text.replace("\\", "＼").replace("{", "（").replace("}", "）").replace("\n", r"\N")
        events.append(
            f"Dialogue: 0,{_timestamp(start, True)},{_timestamp(end, True)},Default,,0,0,0,,{safe}"
        )
    (directory / "subtitles.ass").write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return {"srt": "subtitles.srt", "ass": "subtitles.ass"}
