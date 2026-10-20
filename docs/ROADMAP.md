# Roadmap

## Milestone 1 — local clipping engine

Implemented: local media validation/extraction, provider interfaces, mock flow, Faster-Whisper CPU/CUDA adapter and CPU fallback, Qwen Ollama/llama.cpp adapter, evidence/score gates, vertical rendering, SRT/ASS, metadata, duplicate detection, logs/timings, basic durable queue, pause/retry, diagnostics and ten-minute benchmark command.

Validation order:

1. Keep laptop development on MOCK; test actual FFmpeg outputs, queue failures, zero highlights and duplicate suppression.
2. On the desktop, with separately approved downloads/runtime preparation, verify the actual GPU, CUDA libraries, pre-downloaded Whisper model and quantized Qwen 3B–4B model.
3. Benchmark a permitted ten-minute recording with real Dominican Spanish. Inspect transcription, word timing, captions and candidate choices manually. Record CUDA versus CPU fallback, cold/warm timings, process RAM and device VRAM.
4. Repeat on a permitted one-hour recording and a deliberately uninteresting source. Record throughput, missed highlights, false positives, boundary cuts, silence hallucinations and duplicate behavior.
5. Evaluate a representative CPU environment for eventual VPS use. No production hardware or capacity promise until these measurements exist.

## Milestone 2 — independent cloud execution

Design direction: CPU VPS for ingestion of authorized recordings, a persistent queue, CPU processing and artifact management. Personal devices are optional test clients and never an availability requirement. Before buying/deploying: compare measured CPU completion time and storage against required source hours/day and turnaround. Add on-demand RunPod open-source inference only if those measurements require it and the user approves both infrastructure and spending.

Future work: queue/control transport for independent remote workers, leases and heartbeat recovery, request-level idempotency for ambiguous remote submissions, model packaging, better audio chunk overlap/merging, Cloudflare R2 storage adapter, quotas/retention/backups, observability and provider-side budget ceilings. Keep SQLite for the first single-host CPU worker; migrate only when demonstrated contention or remote-worker coordination needs justify it.

The $50–$100/month infrastructure target is a planning constraint, not a demonstrated operating cost. Reconcile measured workload and current provider quotes before choosing a plan.

## Milestone 3 — review and Buffer distribution

Build an editorial review workflow, platform-specific metadata validation, Buffer account/channel authorization, scheduling, idempotent publication records and publication receipts. Only Buffer may automate Facebook, Instagram, TikTok and X distribution. No YouTube publishing path. Do not publish test content without explicit approval.

## Deferred acquisition

No platform capture, downloader, credential scraping or livestream acquisition is implemented. Confirm an authorized footage source and method before designing acquisition. The current contract is a permitted local recording, asserted by the operator at submission.
