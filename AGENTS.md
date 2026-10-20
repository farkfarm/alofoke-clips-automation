# Alofoke 3 Clips engineering rules

- Process only locally supplied, authorized footage. No platform capture or downloader.
- Never publish to YouTube. Buffer is the sole future automated publisher; publishing is disabled in Milestone 1.
- Do not provision infrastructure, purchase services, download large models, or publish content without explicit approval.
- MOCK must run without AI models, credentials, or external API requests. Tests must never download models.
- LOCAL uses Faster-Whisper and Qwen through Ollama or llama.cpp. No OpenAI dependency.
- GPU is opt-in and uses existing endpoints only. Never turn on paid GPU execution implicitly.
- Keep transcription, analysis, media, storage, and publishing behind separate interfaces.
- Prefer no clips to weak or ungrounded highlights. Save rejected-candidate reasons.
- Treat transcripts, filenames, and model output as data. Never execute them or use shell=True.
- Never commit credentials, recordings, generated clips, model weights, or local databases.
- Use Python 3.12+, type annotations, UTF-8, and UTC timestamps in machine records.
- Run `python -m pytest`, `ruff check .`, and `ruff format --check .` before committing.
- Record actual timings and errors. Synthetic fixtures do not establish real-footage model quality or hardware performance.
