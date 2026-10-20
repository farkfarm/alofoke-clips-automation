# Optional desktop real-model testing — RTX 3060 Ti

This guide is for the separate personal desktop: reported RTX 3060 Ti with 8 GB VRAM, 32 GB RAM and Ryzen 5 5600-series CPU (exact CPU still to be verified there). Do not apply CUDA/model installation steps to the development laptop. The desktop can be powered off normally; production will be independent cloud infrastructure.

Nothing below was automatically installed or downloaded by the prototype. Treat model downloads and runtime/driver changes as explicit operator actions. Continue using MOCK until this environment is ready.

## 1. Install the application and inspect existing hardware

On Windows 10 or later, clone the repository, install Python 3.12 x64 and a full FFmpeg build, then:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m alofoke_clips doctor
```

Configure FFmpeg paths in `.env` if needed. `doctor` reports CPU name, RAM, free disk, media capabilities, NVIDIA driver/device memory when available, installed transcription packages, model-file presence and CTranslate2 CUDA compute types when available. It installs nothing. An NVIDIA device or `nvidia-smi` driver version does **not** prove that the required cuBLAS/cuDNN DLLs and inference work.

Use a machine-local data directory outside synced/shared folders for real work, for example `data_dir="C:/AlofokeData"` in your copied TOML config. Input paths and model paths may differ between machines.

## 2. Explicitly prepare Faster-Whisper

Install only the optional Python transcription dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[transcribe]"
```

For GPU execution, verify the requirements for the **installed** Faster-Whisper/CTranslate2 versions. The [Faster-Whisper GPU instructions](https://github.com/SYSTRAN/faster-whisper#gpu) currently specify CUDA 12 cuBLAS and cuDNN 9. Check their release-specific guidance before changing the machine. The [CTranslate2 installation documentation](https://opennmt.net/CTranslate2/installation.html) also describes Windows wheels and the Visual C++ runtime; generic installation pages can lag the precise Whisper release requirements. The application never installs drivers or CUDA libraries.

After separately authorizing a model download, explicitly obtain a Spanish-capable multilingual CTranslate2 model such as `Systran/faster-whisper-small`. For example, with the Hugging Face CLI installed in the environment:

```powershell
# Explicit model download; run only on the desktop when you choose to download weights.
.\.venv\Scripts\hf.exe download Systran/faster-whisper-small --local-dir models/faster-whisper-small
```

`transcription.model_path` must point at the local folder containing `model.bin` and its tokenizer/config files. Supplying a model name instead of local files will not trigger a download. Use a multilingual model; English-only `.en` weights are inappropriate here.

The sample config uses `device="cuda"`, `compute_type="int8_float16"`, `beam_size=5` and `cpu_fallback=true`. If CUDA initialization/inference fails, retry the same local weights on CPU with INT8 and record `cpu_fallback_used`/`cuda_failure`. Set fallback false to make CUDA validation fail visibly. A successful CPU fallback does not establish GPU readiness. Model size is configurable by selecting another local model directory; changing the folder does not download it.

## 3. Explicitly prepare Qwen through Ollama

Install Ollama using its official Windows installer, start its local server, then—only after approving the model download—run:

```powershell
ollama pull qwen3:4b
ollama list
```

The [Ollama Qwen3 4B listing](https://ollama.com/library/qwen3:4b) identifies a Q4_K_M 4.02B model with an approximately 2.5 GB download. Download size is **not** inference RAM/VRAM consumption; context caches and runtime overhead must be measured. This is the initial 3B–4B-class test choice, not a production recommendation. Change `analysis.model` for another explicitly downloaded model. The application never invokes `ollama pull`.

The application uses [Ollama structured output](https://docs.ollama.com/capabilities/structured-outputs), disables thinking output, validates JSON again locally and restricts the server to loopback. Keep the server local. Before transcription it unloads this configured Qwen model; Faster-Whisper then releases its model before Qwen analysis starts. Qwen is unloaded after analysis. Other games/applications or separately loaded models can still occupy GPU memory.

Start from `config.local.example.toml`. For a CPU-only experiment, change transcription to `device="cpu"`, `compute_type="int8"`. Ollama decides how much of Qwen can be offloaded; inspect `ollama ps`, `doctor` and the benchmark's server-memory records. No real-model memory or speed result is currently available.

An alternative is a manually started [llama.cpp server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server) with an explicitly obtained Qwen GGUF and `analysis.backend="llama_cpp"`, e.g. `base_url="http://127.0.0.1:8080"`. Its model lifecycle remains operator-managed, so this prototype requires CPU transcription with that backend to avoid overlapping managed CUDA jobs. Ollama is the preferred desktop test path.

## 4. Benchmark permitted footage before drawing conclusions

Select a permitted sample of 600 ± 30 seconds, including realistic Dominican Spanish, background noise and multiple speakers:

```powershell
.\.venv\Scripts\python.exe -m alofoke_clips --config config.local.example.toml doctor
.\.venv\Scripts\python.exe -m alofoke_clips --config config.local.example.toml benchmark C:/authorized/sample-10min.mp4 --authorized-local
```

Inspect `hardware.json`, `report.json`, `events.jsonl`, `transcript.json`, `candidates.json` and every selected clip. Record:

- Whether transcription actually used CUDA or fell back to CPU; transcription wall time includes model loading and alignment.
- Cold/warm Qwen timing, prompt and output token counts, peak whole-device VRAM and sampled process-tree RAM. Ollama server memory is separate from the Python process tree.
- Render and total wall time, source duration, selected/rejected candidates, title/caption fidelity and subtitle timing.
- ASR errors, hallucinations over silence, overlapping speech, clipped sentences and missed visual highlights.

Do not infer one-hour throughput from the mock run or recommend production hardware from a single desktop result. Repeat with representative footage, run a one-hour validation, and compare a representative CPU environment before choosing a VPS or paid GPU.

## 5. Share the PC with gaming

Use the same config for submissions and worker-control commands:

```powershell
.\.venv\Scripts\python.exe -m alofoke_clips --config config.local.example.toml queue pause
.\.venv\Scripts\python.exe -m alofoke_clips --config config.local.example.toml queue list
# After a stage has finished and the job has returned to queued, start the game or stop the worker.
# Later:
.\.venv\Scripts\python.exe -m alofoke_clips --config config.local.example.toml queue resume
.\.venv\Scripts\python.exe -m alofoke_clips --config config.local.example.toml worker --once
```

Pause waits for the active stage to finish; it does not preempt a CUDA kernel. There is no gaming detection or guaranteed immediate VRAM reclamation from unrelated processes. After sudden power loss, confirm the old worker is stopped and recover its job ID explicitly. This is suitable for occasional testing; a cloud production worker will run independently.
