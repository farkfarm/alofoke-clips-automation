# Milestone 1 acceptance — 2026-10-22

MOCK acceptance passed; smooth playback and perceived audio quality remain follow-up checks. Browser playback could not be verified because the provided browser inventory was empty. No application defect was found and no application code changed.

## Recorded environment and results

- Branch `codex/milestone-1`; HEAD, reviewed commit and fetched `origin/codex/milestone-1` were `b7b0c3ead2b50a364e43bae69ad8d735d2d2abaa`; ahead/behind `0/0`. Initial worktree was clean. This report records the acceptance run at the reviewed application revision; generated evidence remains local and ignored by Git.
- Isolated Python **3.12.10** virtual environment; existing FFmpeg/FFprobe/FFplay **9.0.2**. The system default Python 3.14 was not used. Only MOCK/test dependencies and the editable application were installed; no inference runtime, model weights or cloud SDK was installed. `pip check` passed.
- `python -m pytest -q --cov=alofoke_clips --cov-report=term-missing`: **76 passed in 26.56 s**, **85% coverage**; command wall time **35.078 s**. `python -m ruff check .` and `python -m ruff format --check .` passed.
- Existing `scripts/make_synthetic.py` generated a fresh **22 s, 640×360, 10 fps** color-and-tone source and labelled Spanish fixtures. It contains **no Spanish speech**.
- Complete MOCK: **1 candidate, 1 selected clip, no errors**; source interval **1.75–17.25 s**, fixture score **79**. CLI wall time **5.689 s**, reported pipeline **4.281 s**, render **3.472 s**. MOCK fixture loading is not AI inference speed.
- Output: **1080×1920**, H.264 High, `yuv420p`, **30 fps**, AAC **48 kHz stereo**, container duration **15.5 s**. FFmpeg decoded the complete video and audio with `-xerror -err_detect explode` without error (**1.338 s**).
- PNGs decoded from the MP4 alone at 0/3/8/13 s were saved. Visual inspection at 3/8/13 s confirmed readable white Spanish subtitles with accents in the lower black padding; no SRT/ASS sidecar was loaded. The 3 s subtitle region contained **19,586 bright pixels** and **209,934 dark pixels**.
- Existing native FFplay ran with a normal SDL display, `-autoexit -stats -loglevel info -x 360 -y 640 -volume 0`. It advanced to **15.45 s**, then exited automatically with **exit 0**; wall time including startup **20.811 s**, without a codec/display/audio-device error. Its statistics recorded **40 dropped frames**, mostly at startup; this run does not establish smooth playback or hardware throughput. Audio was muted and was not listened to.
- The in-app browser returned `Browser is not available: iab`; browser/app inventory was `[]`. Opening the local page through Codex was queued but yielded no controllable browser. Browser playback remains unverified. The temporary server bound only to `127.0.0.1` and was stopped.
- Duplicate processing completed with **0 new clips**; empty analysis completed with **0 candidates/0 clips**. Expected job reports/logs and all five clip files exist. SQLite contained **0 cloud reservations**.
- Tests and pipeline children used an acceptance guard that blocked external connections and real-model imports. **No guard events** occurred. Both providers reported `mock`, `model_loaded=false`; publishing remained `disabled`, with review required. There were no AI model calls, paid API calls, GPU jobs, infrastructure changes, platform captures or publishing. Package installation used the package registry; the Colab plan used a read-only official FAQ lookup.

## Preserved first assertion failure

The first harness incorrectly required exactly 465 frames (`15.5×30`). The source is 10 fps and the 1.75 s trim falls between its 1.7/1.8 s frames. The first retained video frame maps to **0.066667 s** on the output grid. The video duration is **15.433333 s**, containing **463 frames**, ending at **15.5 s**, aligned with audio/container duration. The corrected check allows source/output frame-grid rounding and validates the actual frame count against video duration. No renderer change was justified.

The original `acceptance-results.json` remains unchanged and is also copied to `acceptance-results.initial-failed.json`. Continued checks are in `acceptance-resume-results.json`; the consolidated outcome is `acceptance-final.json`.

## Exact local output and opening instructions

Acceptance evidence directory:

```text
<repository-root>/data\acceptance\2026-10-22-154006-386c01
```

Clip folder, containing `video.mp4`, `subtitles.srt`, `subtitles.ass`, `metadata.json` and `transcript.json`:

```text
<repository-root>/data\acceptance\2026-10-22-154006-386c01\output\jobs\0a0b8b1de246483997b7c3657a7c378f\clips\9c3d2f537de841c179e877dd
```

From the repository root in PowerShell:

```powershell
$acceptedRun = Get-Content -LiteralPath 'data/acceptance/latest-run.txt'
$acceptedVideo = Join-Path $acceptedRun 'output/jobs/0a0b8b1de246483997b7c3657a7c378f/clips/9c3d2f537de841c179e877dd/video.mp4'
Invoke-Item -LiteralPath $acceptedVideo
```

Alternatively, open that folder in File Explorer and double-click `video.mp4`. The subtitles are already burned into the image. `frames/`, `native-playback.stderr.log`, `native-playback-results.json`, `tests.xml`, command logs, and configuration/provenance files preserve local evidence. Generated media, databases, virtual environment and harness files are ignored by Git.

## Reproduce without deduplicating the accepted run

These commands reuse the installed acceptance environment but create a **new config and output directory**. Do not rerun the original full harness against its existing queue: successful deduplication will suppress the previously exported clip.

```powershell
$repo = (Get-Location).Path
$acceptedRun = Get-Content -LiteralPath 'data/acceptance/latest-run.txt'
$python = Join-Path $acceptedRun 'venv/Scripts/python.exe'
$replay = Join-Path $repo ('data/acceptance/replay-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $replay | Out-Null
$ffmpeg = Join-Path $repo '.tools/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe'
$ffprobe = Join-Path $repo '.tools/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe'
$config = Join-Path $replay 'acceptance.toml'
$toml = @"
mode = "mock"
data_dir = "output"
[media]
ffmpeg = "$($ffmpeg.Replace('\', '/'))"
ffprobe = "$($ffprobe.Replace('\', '/'))"
[gpu]
allow_paid = false
monthly_budget_usd = 0
"@
[IO.File]::WriteAllText($config, $toml, [Text.UTF8Encoding]::new($false))
$env:ALOFOKE_FFMPEG = $ffmpeg
$env:ALOFOKE_FFPROBE = $ffprobe
$env:PYTHONPATH = Join-Path $acceptedRun 'guard'
$env:ALOFOKE_ACCEPTANCE_GUARD_LOG = Join-Path $replay 'guard-events.jsonl'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:COVERAGE_FILE = Join-Path $replay 'coverage.dat'
$env:RUFF_CACHE_DIR = Join-Path $replay 'ruff-cache'
& $python -m pytest --cov=alofoke_clips --cov-report=term-missing -o "cache_dir=$replay/pytest-cache"
& $python -m ruff check .
& $python -m ruff format --check .
& $python -m alofoke_clips --config $config doctor
& $python scripts/make_synthetic.py --config $config --output "$replay/synthetic" --seconds 22
$result = (& $python -m alofoke_clips --config $config process "$replay/synthetic/source.mp4" --authorized-local --mode mock --mock-transcript "$replay/synthetic/transcript.json" --mock-analysis "$replay/synthetic/analysis.json") | ConvertFrom-Json
$video = Join-Path (Split-Path -Parent $result.clips[0]) 'video.mp4'
& $ffprobe -v error -count_frames -show_streams -show_format -of json $video
& $ffmpeg -hide_banner -v error -xerror -err_detect explode -i $video -map 0:v:0 -map 0:a:0 -f null -
& (Join-Path (Split-Path -Parent $ffmpeg) 'ffplay.exe') -autoexit -stats -loglevel info -window_title 'Alofoke MOCK acceptance' -x 360 -y 640 -volume 0 $video
```

For a separate fresh virtual environment, install `requirements-dev.lock` (MOCK/dev packages only) plus the editable application, without the optional `transcribe` extra. This run used pinned MOCK/test requirements excluding the unused `build` and `pyproject_hooks` tools; its exact installed versions are saved in `packages.json` and `requirements-mock-test.txt`.

## Milestone 2 — Colab plan only

1. Pin the accepted commit; check Python ≥3.12, FFmpeg/FFprobe and available hardware in a manually started Colab session. Reproduce MOCK first with a fresh temporary output directory.
2. Only after separate approval, obtain Faster-Whisper weights and a quantized Qwen 3B/4B model. Use the existing LOCAL interfaces through Ollama or llama.cpp; CUDA belongs to LOCAL here. The repository's `gpu` mode denotes the separately gated RunPod endpoint contract.
3. Run a manual, authorized ten-minute real-footage benchmark. Record model/version/quantization, cold/warm timings, CPU/RAM/VRAM, render time, errors and editorial review of Spanish transcription, subtitle timing and highlight quality.
4. Export clips, reports and configuration before ending the session. Review measurements before choosing independent CPU VPS production and any optional GPU worker. The proposed $50–$100/month target remains unvalidated.

The [official Colab FAQ](https://research.google.com/colaboratory/faq.html) states that GPU availability/resource limits vary and VMs are deleted after idle time or an enforced lifetime. Therefore, the proposed use is a bounded manual experiment; treating Colab as a persistent production worker would be inappropriate for this plan. No notebook, Colab runtime, model download or Milestone 2 implementation was created.

Real Dominican Spanish, overlapping speakers, highlight usefulness, one-hour throughput and production cost remain unmeasured. Synthetic acceptance proves the MOCK/software/media path only.
