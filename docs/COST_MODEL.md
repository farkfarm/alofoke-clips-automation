# Cost model — unvalidated production target

Target: **$50–$100 USD/month**. No paid service, infrastructure or model API was used or purchased for this implementation. No production budget or hardware recommendation is established by the synthetic tests.

## Cost inputs to measure

| Input | How to obtain it | Current state |
| --- | --- | --- |
| Source hours/day and required turnaround | Owner's operating schedule | Unknown |
| CPU transcription time per source hour | Real ten-minute and one-hour benchmarks on the intended CPU class | Unknown |
| Qwen analysis time, tokens/sec and context cost | Per-window Ollama metrics in the benchmark | Unknown for real models |
| Peak RAM and GPU VRAM | Process-tree sampling, model-server metrics, `nvidia-smi` | Synthetic measurements only; see validation report |
| Render seconds/output minute | Benchmark `stage_seconds.clip_rendering` | Synthetic measured; real footage unmeasured |
| Retained input/output GB and retention days | Actual artifact sizes and selected clip count | Unknown production workload |
| CPU VPS price, included storage/transfer | Current provider quote after sizing | No plan selected |
| GPU execution, cold start, billing minimum and idle time | Approved provider's billing and measured endpoint runs | No endpoint provisioned |
| R2, transfer, Buffer plan/API availability | Current plans plus actual storage/publishing workload | Deferred; no assumption of free API access |

## Formulas

For `H` source hours/day and measured CPU real-time factor `r`:

`monthly CPU processing hours = 30 × H × r + analysis hours + render hours`

A single serial worker has at most 24 wall-clock hours/day before downtime and contention. A cheap CPU VPS may fail the turnaround requirement regardless of its price. Benchmark the proposed CPU class before purchase; desktop results do not establish VPS performance.

For `N` approved GPU jobs:

`GPU estimate = Σ (billed execution + cold-start/idle seconds) × applicable $/second + storage + transfer`

`monthly total = VPS plan + extra disk/backups + GPU + object storage/transfer + applicable Buffer fees + other infrastructure`

Local testing has no paid AI API charge, but electricity, hardware wear, bandwidth and the owner's time are not measured or free by assumption. GPU execution estimates in reports exclude idle/cold-start/storage charges unless separately supplied and reconciled. Actual invoice cost remains unknown.

## Storage arithmetic

Mono 16 kHz PCM16 audio uses about `16,000 × 2 × 3,600 = 115,200,000 bytes` per source hour, plus a WAV header. It is removed after success by default. A source at an illustrative 6 Mb/s uses about 2.7 GB/hour; this is arithmetic, not an observed recording bitrate. Vertical output size depends on CRF, scene complexity and duration. Measure files before choosing retention. The pipeline performs a conservative free-disk precheck, not an enforceable filesystem quota.

## Spending controls

MOCK and LOCAL have no cloud processing client calls. RunPod is disabled by default and requires both configuration opt-in and explicit per-job authorization. The GPU adapter reserves a conservative maximum request estimate against two SQLite limits before submission:

- `gpu.monthly_budget_usd=50` by default, configurable from zero through 100.
- `gpu.max_job_usd=2` by default.
- `gpu.usd_per_second=0` means **unknown**, so paid requests are refused until configured.

Reservations remain spent in this protective ledger after failures or ambiguous outcomes; an operator must reconcile externally. The limit covers this adapter's reserved processing, not the whole account or infrastructure invoice. Provider-side hard limits and verified endpoint execution ceilings are still needed before real paid use. Queued jobs preserve their configuration snapshots, including budget limits; changing limits does not rewrite already queued jobs.

Decision gate: measure real models and footage, project monthly utilization and storage, then compare current quotes. Until that is done, do not claim the $50–$100 target is feasible and do not provision anything.
