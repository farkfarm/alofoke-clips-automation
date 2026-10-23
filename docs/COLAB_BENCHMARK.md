# Milestone 2 — manual Colab benchmark

Open `notebooks/02_colab_real_benchmark.ipynb` in your own Colab account. This prepares a bounded experiment using the existing application. It does not deploy a worker, purchase compute, start RunPod, or enable publishing.

Download the notebook from `codex/milestone-2-colab`, then use Colab **File → Upload notebook**. Start with a CPU runtime for the MOCK smoke test. For real benchmarking, explicitly select an available GPU runtime yourself and rerun from initialization in that fresh runtime; no particular GPU or paid tier is required or selected by the notebook. For a private repository, set `PRIVATE_SOURCE = True` before running source checkout and answer the hidden token prompt. The notebook itself need not be in the accepted source revision it checks out.

Milestone 1 status: **MOCK acceptance passed; smooth playback and perceived audio quality remain follow-up checks.** The sanitized acceptance report is preserved on `codex/milestone-1`; the notebook defaults to accepted commit `c1f9b16157ff72874ec554c3acca34d4ff8f8859`. Change `REVISION` explicitly to test another revision; the resolved full commit is printed and exported. Do not use a moving branch without recording its resolved commit.

## Run order

1. **Source:** public Git HTTPS or a hidden private-source token prompt. Private access uses a temporary askpass script containing no secret; the token lives in a child environment only and is removed afterward. Use a short-lived read-only token. Never put credentials in a URL, cell, saved output or Git remote. Source authentication diagnostics are not saved. No organization/access changes are automated.
2. **Inspect/setup:** Python ≥3.12, existing FFmpeg/FFprobe with libx264/AAC/libass, package versions, RAM/disk and actual GPU. Baseline installation uses the project's normal editable package plus test tools, without the `transcribe` extra. If FFmpeg is absent, manually install the OS package before continuing. No CUDA driver installation is provided.
3. **MOCK:** the existing `scripts/make_synthetic.py` and `python -m alofoke_clips --config … process … --mode mock` run against a new queue. This stage works without a GPU or models. It must complete with one fixture-driven clip. The synthetic source is color/tone, not speech.
4. **Proposal:** review the exact model IDs, sizes and configuration. Click **Approve downloads** deliberately. The button only grants a one-use, in-memory permission; it does not download anything itself. Run all resets permissions and cannot authorize models or inference. Do not edit gate code to bypass a missing approval.
5. **Input:** select one permitted existing recording explicitly, optionally mounting Drive yourself. Type the permission phrase. The file is copied into the unique runtime workspace; the original is never processed in place or overwritten. This first benchmark requires 600 ±30 seconds because it uses the actual `benchmark` CLI contract.
6. **Real setup:** an assigned NVIDIA GPU and an existing Ollama Linux binary are required. Installing the binary is a separate manual operation following [official Ollama Linux instructions](https://docs.ollama.com/linux); no installer or driver script is executed by the notebook. Reapprove if you rerender the proposal cell. The approved cell installs the project's optional transcription dependencies and downloads the proposed weights. It starts only its own Ollama process on `127.0.0.1:11434`, refuses an occupied port, and records the downloaded model digest and runtime/package versions.
7. **Inference:** record your actual Colab compute-unit balance if available, then click **Approve real inference**. The capability is tied to this workspace, source hash, proposal and downloaded model digest, and is consumed once. The existing LOCAL pipeline runs Faster-Whisper CUDA then Qwen/Ollama sequentially, with CPU libx264 rendering and `selection.max_clips=3`. No mock/heuristic fallback occurs. CUDA CPU fallback is disabled for this controlled measurement. Failures remain errors; zero clips is valid.
8. **Export/cleanup:** enter the actual after-balance or leave it unknown. Export the report, transcripts, candidates, captions, SRT/ASS and videos as a downloadable archive or to an explicitly selected mounted Drive folder. A unique archive name and exclusive creation prevent overwriting an existing Drive archive. Input, weights, environments and credentials are excluded. Review transcripts and metadata for sensitive content before sharing the archive. Run cleanup even after failure to stop only the notebook-owned server. Colab sessions are temporary; export promptly.

## Proposed models and resource caveats

| Component | Exact proposed identity | Approximate download |
| --- | --- | --- |
| Faster-Whisper multilingual small | `Systran/faster-whisper-small`, revision `536b0662742c02347bc0e980a01041f333bce120` | 486 MB |
| Qwen | Ollama `qwen3:4b`, Q4_K_M; resolved digest recorded after pull | 2.5 GB |

Sizes are from the [Whisper repository listing](https://huggingface.co/Systran/faster-whisper-small/tree/main) and [Ollama Qwen listing](https://ollama.com/library/qwen3:4b), checked October 23, 2026. Qwen's tag is mutable: compare the exported digest across runs; do not describe a tag alone as a reproducible weight version. Runtime binaries, dependencies, KV cache and inference memory are additional. These are proposed test models, not a production hardware recommendation. No weights were downloaded during preparation.

## Measurements and limitations

- Source checkout, baseline dependencies, input copying, inference dependencies and each model download have separate setup timers.
- The actual benchmark report retains all stage durations and end-to-end pipeline total. A child wrapper times the existing Whisper model constructor without replacing provider logic. Its value excludes lazy initialization that can happen during decoding. Both inclusive transcription time and constructor-subtracted estimate are exported.
- Ollama reports per-call load time in nanoseconds; that is exported separately and subtracted only as an estimate from inclusive analysis time. Models are not preloaded twice just to obtain a timing. No cold/warm result is invented; rerun with a fresh workspace and label conditions if comparing warm/cold behavior.
- The existing pipeline samples whole-device GPU memory approximately once per second. It includes other processes and can miss short peaks; this is not per-model allocation or guaranteed VRAM requirement. Python/child RSS excludes the separate Ollama server; its available model-memory snapshot is recorded separately.
- Compute-unit fields are manual, optional and nullable. A before/after difference includes other account/runtime activity and is not a consumption rate or dollar cost. No balance, cost, subscription requirement, A100 assignment or A100 performance is assumed.
- If model setup fails after source selection, the export cell can still preserve the setup timers, recorded errors and proposed identities with real execution marked `not_run`. A model that was never loaded has no invented load or inference timing.
- The package's `gpu` mode means its gated RunPod adapter. This notebook uses `local` with CUDA in the Colab VM. No RunPod or OpenAI/Gemini API is used. Publishing stays disabled; Buffer is the only future automated publisher.

The [Colab FAQ](https://research.google.com/colaboratory/faq.html) describes variable availability/limits and temporary VMs. Do not attach this notebook to a persistent production queue or treat it as an unattended server. Production remains independent CPU VPS execution with optional GPU only when measured needs justify it; $50–$100/month feasibility is not established.

## Validation boundary

Preparation is validated locally with the existing test suite, Ruff, notebook JSON/schema validation, compilation of every Python cell, fail-closed gate checks, and execution of the notebook's actual MOCK cell using the installed local FFmpeg paths. Notebook outputs and execution counts are stripped before commit.

Not yet tested: your Colab account/runtime, Linux package setup, private-source authentication in Colab, Drive mount/export, widgets in the Colab frontend, Ollama installation/startup, approved model downloads, CUDA/cuDNN compatibility, real inference, resource consumption or perceived output quality. These are account-side execution checks, not successful results from this preparation. A missing GPU/runtime/binary or failed real inference is a blocker to investigate, not permission to change providers or incur charges.

### Recorded preparation checks — October 23, 2026

Windows laptop, Python **3.12.10**, FFmpeg/FFprobe **9.0.2**, pytest **9.1.1**, Ruff **0.17.1**, nbformat **5.11.1**:

- **82 tests passed in 22.24 seconds**, including executing the notebook's actual MOCK configuration/generator/CLI cell, checking that unapproved download/inference stages fail before execution, and preserving setup failures without inventing inference results.
- `ruff check .` and `ruff format --check .` passed after formatting the notebook.
- `nbformat.validate`, Python compilation of all **11 code cells**, and compilation of the generated private-source askpass and model-timing launcher scripts passed. All saved execution counts remain null and outputs empty.
- An initial local smoke attempt failed because a pre-existing relative FFmpeg environment setting overrode the fresh config path. The notebook now sets resolved absolute media executable paths for its child commands. The corrected smoke test passed; no application provider/pipeline change was needed.

The acceptance report commit is `c1f9b16157ff72874ec554c3acca34d4ff8f8859`. Notebook preparation is on its child branch `codex/milestone-2-colab`; there was no default-branch merge or force push. No real-model performance, GPU-memory requirement, compute-unit consumption, cost or A100 result has been measured during preparation.
