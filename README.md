# Alofoke 3 Clips

Milestone 1 is a Python 3.12+ prototype that turns **authorized local recordings** into reviewable 1080×1920 clips with Spanish subtitles and explainable highlight scores. It works on a laptop in MOCK mode without a GPU, AI weights, credentials, or paid APIs.

The final production direction is a **cloud CPU VPS**, independent of both personal computers, with optional on-demand GPU workers if measurements justify them. Nothing in this repository has been deployed or purchased. The $50–$100/month target is **not yet validated**.

## What is implemented

- FFprobe validation; FFmpeg audio extraction, accurate segment re-encoding, 1080×1920 H.264/AAC rendering and subtitle burn-in.
- Spanish transcription adapters: explicit mock fixtures, local Faster-Whisper with CUDA or CPU, and a gated future RunPod endpoint contract.
- Qwen analysis through loopback Ollama or llama.cpp, bounded overlapping transcript windows, JSON schema validation, Spanish titles/captions, evidence and factor explanations.
- Quality filtering, abstention, source/time and fuzzy transcript deduplication, clip metadata, JSONL logs, timings and sampled memory metrics.
- Persistent SQLite queue, exclusive worker claims, optional submission idempotency keys, cooperative pause/resume, checkpointed retries and cloud budget reservations.
- Read-only hardware diagnostics and a ten-minute sample benchmark command.

**Publishing is disabled.** Buffer is the only permitted future automated publisher, targeting Facebook, Instagram, TikTok and X. YouTube publishing and platform livestream capture are excluded.

## Operating modes

| Mode | Models and execution | Current validation |
| --- | --- | --- |
| MOCK | Explicit JSON fixtures; real FFmpeg; no model or API calls | Automated unit/integration tests and synthetic benchmark |
| LOCAL | Pre-downloaded Faster-Whisper; Qwen on local Ollama or llama.cpp; CPU or CUDA | Provider contracts tested using doubles; real models still need desktop testing |
| GPU | Existing RunPod Serverless endpoint implementing the documented contract | Opt-in client and budget/contract tests only; no endpoint provisioned or contacted |

The laptop is for MOCK development. The personal RTX 3060 Ti desktop is for occasional real-model tests, not a production dependency. LOCAL may also run on a future CPU VPS. See [desktop setup](docs/DESKTOP_SETUP.md), [architecture](docs/ARCHITECTURE.md) and [validation](docs/VALIDATION.md).

## Laptop setup — Windows PowerShell

Install Python 3.12+ and an FFmpeg build containing `ffprobe`, `libx264`, AAC and `libass`. The [FFmpeg download page](https://ffmpeg.org/download.html) links Windows builds. No CUDA or AI models are needed.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

If FFmpeg is not on PATH, edit the ignored `.env` file:

```dotenv
ALOFOKE_FFMPEG=C:/tools/ffmpeg/bin/ffmpeg.exe
ALOFOKE_FFPROBE=C:/tools/ffmpeg/bin/ffprobe.exe
```

Paths in TOML and `.env` resolve relative to the configuration file, or the working directory if no `--config` is provided. Existing environment variables take precedence over `.env`. Keep `data_dir` on a local disk; do not use a concurrently shared/synchronized SQLite database across machines.

```powershell
.\.venv\Scripts\python.exe -m alofoke_clips doctor
.\.venv\Scripts\python.exe scripts/make_synthetic.py --output data/synthetic
.\.venv\Scripts\python.exe -m alofoke_clips process data/synthetic/source.mp4 --authorized-local --mock-transcript data/synthetic/transcript.json --mock-analysis data/synthetic/analysis.json
```

The synthetic video contains a color field and tone, **not Spanish speech**. Its labelled Spanish transcript is a test fixture; its engagement score is not a model evaluation.

On Linux, use `python3.12 -m venv .venv` and `.venv/bin/python` in place of the Windows executable. Install FFmpeg through the operating system's package manager. Windows 10 compatibility is a design target; the recorded local test run used Windows 11.

## Outputs

Each submission returns a job ID. Inspect `data/jobs/<job-id>/`:

```text
source.json          Source checksum, authorization assertion, media info, config snapshot
transcript.json      Full Spanish transcript with source timestamps and optional word alignment
transcript.txt       Readable timestamped transcript
analysis.json        Raw validated proposals and abstention reason
candidates.json      Scores, explanations, selection/rejection and duplicate reasons
events.jsonl         Structured stage/error logs across all attempts
attempt-<n>.json      Timing/error report for each attempt
report.json          Latest attempt's report
clips/<clip-id>/
  video.mp4          1080×1920, H.264/AAC, burned Spanish subtitles
  subtitles.srt      Sidecar subtitles with clip-relative timing
  subtitles.ass      Styled subtitles used for burn-in
  transcript.json    Clip-relative transcript
  metadata.json      Titles, captions, evidence, score breakdown, checksums and review status
```

Audio intermediates are removed after success unless `media.keep_audio=true`. Failed/paused jobs keep checkpoints. All media, local databases, model weights and `.env` files are ignored by Git. A successful run can produce **zero clips**. `fit` framing preserves the entire scene with padding; `crop` is a fixed center crop and can lose off-center speakers.

## Queue and occasional workers

```powershell
.\.venv\Scripts\python.exe -m alofoke_clips enqueue data/synthetic/source.mp4 --authorized-local --job-key synthetic-1 --mock-transcript data/synthetic/transcript.json --mock-analysis data/synthetic/analysis.json
.\.venv\Scripts\python.exe -m alofoke_clips worker --once
.\.venv\Scripts\python.exe -m alofoke_clips queue list
.\.venv\Scripts\python.exe -m alofoke_clips queue pause
.\.venv\Scripts\python.exe -m alofoke_clips queue resume
```

Run `worker` without `--once` to poll until Ctrl+C. Pause in another terminal: the active stage finishes, releases its model, and the job returns to the queue at the next checkpoint. Resume preserves the same job ID and uses completed transcription/analysis checkpoints. A CUDA kernel is not forcibly interrupted, so pause is not instantaneous. Turn the desktop worker off whenever needed; production will not rely on it.

For an explicitly stopped/crashed or failed worker:

```powershell
.\.venv\Scripts\python.exe -m alofoke_clips queue retry JOB_ID --confirm-worker-stopped
.\.venv\Scripts\python.exe -m alofoke_clips worker --once
```

Retry keeps the job ID and increases its attempt count. Stop the old process before recovering a running job. Automatic stale-lock eviction and distributed leases are deliberately deferred. A repeated `--job-key` returns the existing submission; a conflicting request with that key is rejected.

## Tests and benchmark

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=alofoke_clips --cov-report=term-missing
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

External network connections are blocked in tests. AI tests use doubles. FFmpeg integration tests run if both binaries are available and explicitly skip otherwise. CI is manual-only to avoid starting cloud jobs merely by pushing.

Generate a ten-minute **synthetic** sample and run the benchmark with actual media processing:

```powershell
.\.venv\Scripts\python.exe scripts/make_synthetic.py --output data/synthetic-600 --seconds 600
.\.venv\Scripts\python.exe -m alofoke_clips benchmark data/synthetic-600/source.mp4 --authorized-local --mock-transcript data/synthetic-600/transcript.json --mock-analysis data/synthetic-600/analysis.json
```

The benchmark accepts 600 ± 30 seconds, saves `hardware.json`, and reports transcription wall time, speed relative to source duration, clip-render time, total wall time, sampled process-tree RSS, and whole-device GPU memory when `nvidia-smi` is available. MOCK transcription speed measures JSON fixture loading, **not AI inference**. Separate Ollama process memory and model size/VRAM are recorded when that endpoint exposes them. Sampled peaks can miss transient allocations. CPU electricity and cloud invoices are not measured.

After explicitly preparing models on the desktop, run a real benchmark:

```powershell
.\.venv\Scripts\python.exe -m alofoke_clips --config config.local.example.toml benchmark C:/authorized/sample-10min.mp4 --authorized-local
```

No model downloads occur during installation, tests, `doctor`, or the application. Missing weights fail with a setup instruction. No OpenAI package, key, service or account is required.

## Remaining validation

Real Dominican Spanish recognition, multi-speaker overlaps, subtitle accuracy, highlight usefulness, caption fidelity and one-hour throughput remain unmeasured. There is no visual highlight detector, speaker tracking, diarization or guarantee that an engagement score predicts performance. The prototype always requires editorial review. Read [roadmap](docs/ROADMAP.md) and [cost model](docs/COST_MODEL.md) before considering production.
