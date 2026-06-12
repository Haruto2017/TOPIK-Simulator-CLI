# Security

## Threat model

The TOPIK simulator is a local, offline study tool. It starts no servers, opens no ports, and the core makes no network requests. The surfaces that process input you did not write yourself are:

- **Content packs** (`import-pack`, `setup`): JSON data files. Pack ids and versions are validated as filesystem-safe slugs, and the import additionally refuses any destination outside the library directory, so a hostile pack cannot write elsewhere. Packs contain no executable content — they are validated data only. Still, import packs only from sources you trust, the same judgment you would apply to any file you download.
- **Audio playback**: file paths are escaped before being embedded in the Windows playback command, so paths containing quotes cannot inject commands.
- **Subprocess use**: external tools (the optional TTS runtime, `ffmpeg`) are invoked with argument lists, never through a shell, and only with arguments derived from your own configuration.

## Optional components and the network

Two optional features reach outside the core, both opt-in and documented:

- Local TTS providers (Supertonic/MeloTTS) run in their own Python environment and may download models from Hugging Face on first use (see `docs/TTS_SETUP.md`).
- `audio compress` shells out to `ffmpeg` if you installed it.

Without them, the simulator runs fully offline; exams remain usable with transcripts in place of audio.

## Your data

Everything you produce stays on your machine under `data/` (attempts, review queue, audio cache, shell history) and `content/library/`. Nothing is uploaded anywhere. Note that `data/shell_history.txt` records what you type at the shell prompt.

## Reporting

If you find a security issue, please open an issue in the project tracker (or contact the maintainer privately for anything sensitive) with steps to reproduce.
