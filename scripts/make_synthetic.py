"""Generate synthetic color/tone footage and labelled mock Spanish fixtures. No speech or models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from alofoke_clips.config import load_settings
from alofoke_clips.media import MediaTools
from alofoke_clips.models import Segment, Transcript, Word


def create_fixture(output: Path, duration: int, config: Path | None = None) -> None:
    if duration < 22:
        raise ValueError("synthetic source must be at least 22 seconds")
    output.mkdir(parents=True, exist_ok=True)
    settings = load_settings(config)
    tools = MediaTools(settings.media)
    tools.run(
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
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-threads",
            "2",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "32k",
            str((output / "source.mp4").resolve()),
        ],
    )
    texts = [
        "Esto es una prueba sintética. Nadie esperaba que resolviéramos el reto juntos esta noche.",
        "Me emocioné mucho al ver el resultado, "
        "porque al principio pensé que no podríamos terminar.",
        "Pero lo logramos: cada persona ayudó y al final el equipo completó el reto a tiempo.",
    ]
    segments = []
    for index, text in enumerate(texts):
        start = 2.0 + index * 5.0
        tokens = text.split()
        step = 5 / len(tokens)
        segments.append(
            Segment(
                id=f"s{index:06d}",
                start=start,
                end=start + 5,
                text=text,
                words=[
                    Word(
                        start=start + i * step,
                        end=start + (i + 1) * step,
                        text=token,
                        probability=1,
                    )
                    for i, token in enumerate(tokens)
                ],
            )
        )
    transcript = Transcript(
        duration=duration, provider="synthetic_fixture", is_mock=True, segments=segments
    )
    (output / "transcript.json").write_text(
        transcript.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    analysis = {
        "candidates": [
            {
                "segment_ids": [s.id for s in segments],
                "category": "logro",
                "title": "Cada persona ayudó y el equipo completó el reto",
                "caption": (
                    "Prueba sintética: el texto de ejemplo relata cómo "
                    "el equipo completó el reto a tiempo."
                ),
                "confidence": 0.95,
                "factors": {
                    "hook": {
                        "value": 4,
                        "reason": "El texto abre con una expectativa inesperada sobre el reto.",
                    },
                    "emotion": {
                        "value": 4,
                        "reason": "El segmento central expresa emoción y una duda previa.",
                    },
                    "novelty": {
                        "value": 3,
                        "reason": "El resultado conjunto contrasta con la expectativa inicial.",
                    },
                    "payoff": {
                        "value": 4,
                        "reason": "La última frase resuelve el reto con un resultado concreto.",
                    },
                    "context": {
                        "value": 5,
                        "reason": "Las frases incluyen planteamiento, dificultad y resolución.",
                    },
                },
                "evidence": [
                    {"segment_id": "s000002", "quote": "el equipo completó el reto a tiempo"}
                ],
            }
        ],
        "abstention_reason": "",
    }
    (output / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "empty_analysis.json").write_text(
        json.dumps(
            {
                "candidates": [],
                "abstention_reason": "No hay un momento suficientemente interesante.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Synthetic tone/color source ({duration}s) and mock fixtures written to {output.resolve()}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--seconds", type=int, default=22)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    create_fixture(args.output, args.seconds, args.config)
