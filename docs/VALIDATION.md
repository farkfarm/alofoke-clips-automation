# Validation record — 2026-10-20

## Environment actually used

Development laptop: Windows 11 build 26200, Python 3.12.10, Intel Core i7-1255U, 10 physical/12 logical cores reported by psutil, 12,596,011,008 bytes system RAM. No `nvidia-smi` was found. No NVIDIA GPU, CUDA runtime, Faster-Whisper package, CTranslate2 package or model weights were assumed or installed. FFmpeg/FFprobe 9.0.2 Gyan essentials build was downloaded locally, verified against its published SHA-256, and used from the ignored `.tools` directory.

The application targets Windows 10+ and Linux; Windows 10 and Linux have not been executed in this session. The optional manual CI matrix covers Windows/Linux when deliberately triggered; it has not been run remotely.

## Automated tests

Final recorded command:

```text
python -m pytest -q --cov=alofoke_clips --cov-report=term-missing --junitxml=data/test-results.xml
76 passed in 14.25s
Total statement coverage: 85%
```

No skipped tests in this local run. The FFmpeg integration tests performed real audio extraction, vertical rendering, FFprobe verification and pixel checks proving subtitle burn-in. Tests also covered source paths containing spaces/apostrophes, clip-relative subtitle timing, ASS injection neutralization, malformed/missing evidence, score thresholds, abstention, duplicate suppression across runs, persistent/exclusive claims, idempotency keys, pause/resume with checkpoints, failed-render retry, conservative cloud budget reservations, CPU fallback/model release doubles, Qwen schema/HTTP contracts, one-hour transcript window coverage and disabled publishing. Test sockets permit loopback only; no model or paid API endpoint was contacted.

`ruff check .` passed. `ruff format --check .` passed after formatting. `pip check` reported no broken requirements. Python compilation and wheel/source-distribution builds succeeded. The recorded development package versions are in `requirements-dev.lock`; optional inference-runtime dependencies are not installed or locked by that file.

Coverage is not a real-model quality test. CUDA/RunPod paths use doubles and hardware-specific diagnostic branches remain unexecuted. See the limitations below.

## Ten-minute synthetic benchmark

Job `5eebb3b8ee2b4d9ba2f5a166699114fd` used a 600-second 640×360/10 fps static color field plus a 440 Hz tone. Its Spanish transcript and analysis were explicit labelled fixtures describing a fictional team challenge in the first 17 seconds. This source contains **no recorded Spanish speech**. No AI model ran.

| Measurement | Observed value |
| --- | ---: |
| Source duration | 600.000 s |
| Audio extraction | 0.3291 s |
| Mock transcript loading/saving | 0.0353 s |
| Mock analysis loading/saving | 0.0171 s |
| FFmpeg clip rendering and output probe | 4.3944 s |
| Total pipeline wall time | 6.3488 s |
| Sampled peak Python + child-process RSS | 318,746,624 bytes (about 304.0 MiB) |
| GPU memory | Unavailable; zero samples, not a zero-VRAM claim |
| Selected clips | 1 |
| Output duration/dimensions | 15.5 s, 1080×1920 |
| Errors | None |

Machine-readable, sanitized results: [benchmark JSON](benchmarks/mock-laptop-2026-10-20.json). Full local reports and the demo remain in ignored `data/jobs/<job-id>/`; generated media is not committed.

This is a real **media-processing** measurement with mock AI. It is not Whisper/Qwen inference throughput, an hourly production benchmark, a CPU VPS prediction, or a demonstration of highlight quality. Static color footage is much simpler than reality-show video. Sampled peaks may miss transient allocations, and RSS excludes separately running model servers. No cloud invoice or electricity cost was measured.

A subsequent run of the same fixture source produced zero additional clips because its candidate was a duplicate. A separate explicit empty-analysis fixture also completed successfully with zero clips. Integration tests intentionally simulated corrupt input and renderer failure and verified error records and safe retries. No real recording was supplied in the repository.

## Validation still required

| Area | Remaining evidence |
| --- | --- |
| Spanish transcription | Real Dominican accents, multiple speakers, music, silence and word alignment; actual CUDA and CPU fallback runs |
| Qwen quality | Real schema success, faithful Spanish titles/captions, useful ranking, abstention on mundane footage, prompt-injection resilience beyond structural constraints |
| Desktop compatibility | Actual RTX 3060 Ti/driver/VRAM, exact Ryzen CPU, CUDA/cuDNN DLL compatibility, cold/warm model memory and release behavior |
| One-hour success criterion | Permitted one-hour recording through real transcription, analysis, rendering, duplicate checks and editorial review |
| Timing/framing | VFR, unusual start offsets/rotation/anamorphic video, precise A/V/subtitle sync and off-center subjects |
| Queue/hosting | Single local SQLite only; remote control/leases, backups, power-loss and cross-host storage strategy before cloud production |
| Cloud GPU | Existing endpoint implementation, provider-side execution caps, cancellation behavior, invoices and benchmarked advantage over CPU |
| Budget | Actual hours/day, CPU VPS throughput, disk/transfer retention and all provider/Buffer costs; $50–$100/month feasibility remains unknown |
| Publishing | Entirely disabled; future Buffer authorization/review/idempotency still required |

No cloud deployment, service purchase, platform capture, CUDA/driver installation, large model download or social publication was performed.
