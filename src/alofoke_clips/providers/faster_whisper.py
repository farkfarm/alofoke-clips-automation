import gc
from pathlib import Path
from typing import Any

from ..config import TranscriptionConfig
from ..errors import ProviderError
from ..models import Segment, Transcript, Word


class FasterWhisperTranscriber:
    def __init__(self, config: TranscriptionConfig):
        self.config = config
        self.metrics: dict[str, Any] = {
            "provider": "faster_whisper",
            "device": config.device,
            "compute_type": config.compute_type,
        }

    def transcribe(self, audio: Path, duration: float) -> Transcript:
        if not (self.config.model_path / "model.bin").is_file():
            raise ProviderError(
                "Faster-Whisper weights missing; explicitly download a CTranslate2 model "
                "and set transcription.model_path (automatic downloads are disabled)"
            )
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise ProviderError(
                "install the optional transcription extra: pip install '.[transcribe]'"
            ) from error
        try:
            return self._run(
                WhisperModel, audio, duration, self.config.device, self.config.compute_type
            )
        except ProviderError as error:
            if self.config.device != "cuda" or not self.config.cpu_fallback:
                raise
            self.metrics["cuda_failure"] = str(error)
            self.metrics["cpu_fallback_used"] = True
            return self._run(WhisperModel, audio, duration, "cpu", "int8")

    def _run(
        self, model_type, audio: Path, duration: float, device: str, compute_type: str
    ) -> Transcript:
        model = None
        segments = None
        try:
            model = model_type(
                str(self.config.model_path),
                device=device,
                compute_type=compute_type,
                cpu_threads=self.config.cpu_threads,
                local_files_only=True,
            )
            segments, info = model.transcribe(
                str(audio),
                language="es",
                word_timestamps=True,
                vad_filter=True,
                beam_size=self.config.beam_size,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
            )
            output: list[Segment] = []
            filtered = 0
            for segment in segments:
                if (
                    not segment.text.strip()
                    or segment.end <= segment.start
                    or (segment.no_speech_prob > 0.6 and segment.avg_logprob < -1)
                ):
                    filtered += 1
                    continue
                end = min(float(segment.end), duration)
                if end <= segment.start:
                    continue
                words = [
                    Word(
                        start=max(float(w.start), float(segment.start)),
                        end=min(float(w.end), end),
                        text=w.word.strip(),
                        probability=w.probability,
                    )
                    for w in (segment.words or [])
                    if w.word.strip() and min(w.end, end) > max(w.start, segment.start)
                ]
                output.append(
                    Segment(
                        id=f"s{len(output):06d}",
                        start=segment.start,
                        end=end,
                        text=segment.text.strip(),
                        words=words,
                        no_speech_probability=segment.no_speech_prob,
                        avg_logprob=segment.avg_logprob,
                    )
                )
            self.metrics.update(
                device=device,
                compute_type=compute_type,
                filtered_segments=filtered,
                language_probability=info.language_probability,
                model_path=str(self.config.model_path),
            )
            return Transcript(duration=duration, provider="faster_whisper", segments=output)
        except ProviderError:
            raise
        except Exception as error:
            raise ProviderError(f"Faster-Whisper failed: {error.__class__.__name__}") from error
        finally:
            # Exhausted generators can hold the model. Release both before starting Qwen.
            del segments
            del model
            gc.collect()
