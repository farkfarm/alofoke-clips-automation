# Architecture

## Scope and production direction

Milestone 1 is a local executable and a basic persistent queue. The production design targets a CPU VPS that owns scheduling, the queue, storage references and a CPU worker. An optional GPU worker consumes the same logical jobs if measured CPU throughput or quality requires it. Neither personal computer is a production dependency. No cloud resource, database server, scheduler or publisher has been deployed.

```mermaid
flowchart LR
  A[Authorized local recording] --> Q[Persistent job queue]
  Q --> W[Serial Python worker]
  W --> I[FFprobe ingestion and SHA-256]
  I --> AU[FFmpeg mono 16kHz audio]
  AU --> T[Transcriber interface]
  T --> AN[Analyzer interface]
  AN --> S[Grounding, scoring and deduplication]
  S --> R[FFmpeg 1080x1920 and ASS subtitles]
  R --> FS[Artifacts and SQLite metadata]
  FS --> HR[Human review]
  HR -. future explicit approval .-> B[Buffer only]
```

## Module boundaries

| Module | Responsibility |
| --- | --- |
| `ingestion`, `media` | Local authorization assertion, FFprobe stream checks, hashing, extraction and rendering; subprocess argument lists, no shell execution |
| `providers.base` | `Transcriber` and `Analyzer` protocols independent of workflow and hardware |
| `providers.mock` | Explicit timestamped transcript/proposal fixtures, always labelled synthetic |
| `providers.faster_whisper` | Lazy local model import, Spanish VAD/word timestamps, CPU or CUDA and optional CPU fallback, no weight downloads |
| `providers.qwen` | Qwen through loopback Ollama or llama.cpp, bounded overlapping windows, structured output, Spanish editorial prompt |
| `providers.runpod` | Optional existing-endpoint transport and the same model contracts; disabled by default, no provisioning |
| `detection` | Deterministic score formula, transcript grounding, minimum context/payoff and confidence, duration/silence filtering, ranking and deduplication |
| `subtitles` | Clip-relative timestamps, word-timed cues when available, wrapped SRT/ASS, neutralized ASS control sequences |
| `storage` | Local artifact store interface, atomic JSON replacement, SQLite queue, exclusive claims, clip registry and conservative cloud reservations |
| `pipeline`, `cli` | Ordered orchestration, checkpoints, attempts, worker control, command-line entry points |
| `diagnostics`, `observability` | Read-only environment inspection, monotonic timings, structured logs and sampled memory |
| `publishing` | Disabled Buffer boundary; future platforms: Facebook, Instagram, TikTok, X |

## Modes and resource ownership

- **MOCK:** no inference imports or model/API calls. FFmpeg is real. Both fixture paths are required, preventing plausible-looking fabricated transcripts from arbitrary footage.
- **LOCAL:** pre-downloaded Faster-Whisper weights plus an already running loopback Qwen server. No account or paid service. CUDA is a device option within LOCAL, not a requirement. Only HTTP loopback model endpoints are accepted; no cloud fallback or hidden API substitution exists.
- **GPU:** existing RunPod Serverless endpoint using open-source models. Requires `gpu.allow_paid=true`, a per-job approval flag, a key, endpoint ID, a conservative per-second rate and a successful budget reservation. This mode was exercised with transport doubles only.

The desktop example uses Qwen `qwen3:4b`, an explicitly configurable quantized 4B model, and Faster-Whisper `small`. Those are initial test settings, not a production hardware recommendation. The laptop continues using MOCK. Installing the base package does not install Faster-Whisper or download any weights.

For Ollama, the pipeline unloads the configured Qwen model before transcription, releases the Faster-Whisper model/generator before analysis, then unloads Qwen after analysis even if analysis fails. No application-owned AI workloads run concurrently. FFmpeg uses CPU `libx264`; no GPU encoder competes with inference. Unrelated games/processes can still occupy VRAM; CPU fallback records that it was used. A separately managed llama.cpp server cannot be reliably unloaded by this application, so CUDA transcription with that backend is refused; use CPU transcription or the managed Ollama path.

## Analysis and quality gates

Each proposal contains contiguous segment IDs, Spanish title/caption, category, confidence, literal transcript evidence and five 0–5 factors with reasons. The deterministic engagement score is:

`score = 25×hook/5 + 20×emotion/5 + 20×novelty/5 + 20×payoff/5 + 15×context/5`

Default gates: score ≥70, confidence ≥0.75, context and payoff ≥3, 15–60 seconds, ≥15 words and speech occupancy ≥35%. Low ASR confidence/no-speech estimates reject candidates. Padding is removed when needed to respect the maximum without truncating speech. Candidates with unsupported quotes, missing IDs, reordered IDs or disconnected context are rejected. Empty speech bypasses analysis and yields zero clips. The model can also abstain with `candidates=[]`. There is a maximum quantity, never a minimum quota.

Analysis windows default to 180 seconds with 60 seconds of overlap and an 18,000-character segment payload limit. All segments are covered. Extremely long individual segments fail explicitly; they are not truncated. Word timestamps are omitted from the language-model prompt to reduce context size. Model JSON is validated again locally; malformed, truncated or out-of-window output fails the job without speculative replacement.

Scores are editorial heuristics, not calibrated engagement probabilities. Transcript-only analysis misses visual comedy/action and cannot verify identities, reactions or facts outside speech. Literal evidence checks do not prove the title or reason is fully faithful. Editorial review remains required.

## Subtitles and framing

Full transcript times use the normalized source timeline. Audio is extracted to mono 16 kHz PCM with timestamp compensation; rendering uses accurate re-encoding with source time offsets. Clip transcripts and sidecars subtract the selected start. ASR word timestamps define cues. Segment-only fixtures use the known segment interval; long text is split into balanced two-line blocks with **interpolated** timing, which is not word alignment.

ASS subtitles are burned after resizing, with outlined text and a bottom safe margin. Raw transcript control sequences cannot become ASS positioning commands. `fit` is the default to retain all participants in landscape footage; `crop` is a configurable fixed center crop. Speaker-aware/face-aware reframing, unusual A/V timestamp offsets and real subtitle pacing need further footage validation.

## Persistence, idempotency and retries

```text
queued --exclusive claim--> running --> completed
                              |  |
                              |  +--> failed --explicit retry--> queued
                              +-----> queued (cooperative pause after stage)
```

SQLite uses WAL, parameterized queries and `BEGIN IMMEDIATE` for claims, submission keys and budget reservations. One processing lock per queue serializes expensive stages, which is suitable for the shared test PC and a small CPU VPS. Multiple worker processes can inspect the same **local** database; only one can claim work at a time. Queued jobs survive offline workers. No job can be claimed twice while the lock is held.

The queue stores resolved input paths and a non-secret configuration snapshot. Settings on a restarted worker do not silently rewrite an existing job. Use the same data directory/configuration to inspect its queue. Do not share an active WAL database through OneDrive/SMB or copy live databases between machines. A future network queue/control API will replace that persistence adapter when remote workers are actually required.

`--job-key` deduplicates submissions and rejects changed requests under the same key. Completed input SHA-256, transcript and analysis checkpoints prevent inappropriate resume if the source file changes. Retries preserve job IDs and attempt history. Outputs use temporary files and rename; incomplete video output is discarded. Completed clip rows and source/time/text deduplication prevent duplicate successful clip output on retries. Model fixtures and source files must remain immutable while a job is pending.

Pause is persistent and cooperative at model/stage boundaries. It cannot interrupt a running CUDA operation. A paused job returns to `queued` with checkpoints; no new claim occurs until resume. Ctrl+C records a failure when possible. After an abrupt kill or power loss, the running lock remains until an operator confirms the prior worker is stopped and runs `queue retry`. Automatic lease recovery, transactional outbox, remote queues and distributed scheduling are deferred.

## Duplicate detection

The registry compares source SHA-256/time overlap and normalized transcript similarity across jobs within a mode. Within a run it also suppresses overlapping clips and keeps the highest score. Transcript normalization removes casing, punctuation and accent differences; similarity combines word shingles and sequence matching. Clip IDs derive from source hash, time range and mode; video SHA-256 is recorded. MOCK does not suppress LOCAL clips. No perceptual visual/audio hashing is implemented, so re-edited footage with changed speech can evade detection, and generic repeated phrases can cause false positives. Removed artifact files allow explicit regeneration.

## Future RunPod contract and budget

No endpoint exists as part of this milestone. The adapter expects an independently prepared endpoint:

- `POST /v2/<endpoint>/run` with `input.task=transcribe`, `language=es`, `audio_wav_base64`, `duration`; return a `Transcript` with chunk-relative times in `output`.
- Audio is sent sequentially in ≤60-second mono PCM chunks; no public footage URL or R2 dependency is required. Chunk boundaries can split words; overlap/merging is future quality work.
- `input.task=analyze`, `model`, `system`, `schema`, `max_candidates`, `segments`; return an `Analysis` in `output`.
- Poll `/status/<id>` until completed/failed/deadline. On deadline request cancellation. Unknown POST outcomes are not automatically resubmitted. There is no blind paid retry.

Before each submission reserve `timeout_seconds × usd_per_second` against the UTC month's `monthly_budget_usd` and cumulative per-job `max_job_usd`. Reservations are atomic and conservatively retained even after failure/unknown outcomes. Retry clears paid authorization unless explicitly supplied again. Reported execution time supports an estimated execution cost, never an invoice claim. Set provider-side limits too: this local ledger cannot cap spending from other clients, inaccurate rates, provider billing behavior, cold starts or idle workers. No money was spent validating this adapter.
