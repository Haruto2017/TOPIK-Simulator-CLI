# CLI Contract

All commands are run from the repository root.

If the package is not installed, set `PYTHONPATH=src` first.

## `validate-content`

Validates a content pack.

```powershell
python -m topik_sim validate-content <pack.json>
```

Exit behavior:

- `0`: pack is valid.
- Non-zero: pack is invalid; errors are printed.

## `inspect-content`

Prints pack metadata and section/question counts.

```powershell
python -m topik_sim inspect-content <pack.json>
```

## `simulate`

Runs an interactive exam simulation in the terminal.

```powershell
python -m topik_sim simulate <pack.json> [--section <section_id>] [--limit <n>] [--show-teaching]
```

Behavior:

- Presents questions in pack order.
- Prompts for an answer.
- Grades each answer.
- Prints a final score.
- Prints teaching feedback after every answer.
- Pauses after feedback; press Enter to move on.
- `--show-teaching` is kept for compatibility; feedback is always shown.

## `take`

Runs an interactive test and saves the attempt after each answer.

```powershell
python -m topik_sim take <pack.json-or-pack_ref> [--library <library_dir>] [--attempt-dir <attempt_dir>] [--section <section_id>] [--limit <n>] [--speak-question] [--speak-teaching]
```

Pack references:

- A direct JSON path, such as `examples/content/topik_i_mini_pack.json`.
- A library pack ID, such as `topik-i-mini-pack`.
- A pinned library pack ID and version, such as `topik-i-mini-pack@0.1.0`.

Default runtime locations:

- Library: `content/library`
- Attempts: `data/attempts`

TTS behavior:

- Listening questions automatically generate and play Korean audio from transcript-backed `passage` text during `take`.
- Listening transcripts are hidden by default during `take`.
- Listening transcripts are printed after the learner answers.
- At the answer prompt, enter `/replay`, `/r`, or `replay` to play the current question audio again.
- After feedback, press Enter for the next question or enter `/replay`, `/r`, or `replay` to hear the just-answered question audio again.
- `--show-transcript`: show listening transcripts for content debugging.
- `--no-listening-audio`: disable automatic listening audio.
- `--speak-question`: generate Korean audio for non-listening question passages too.
- `--speak-teaching`: generate Korean audio for vocabulary and grammar examples in feedback.
- `--tts-play`: play generated audio immediately.
- `--tts-provider supertonic`: default provider; reuses the Anki Supertonic runtime when available.
- `--tts-provider melo --tts-device cuda:0`: run MeloTTS on the first CUDA GPU.
- `--tts-volume <gain>`: set generated WAV volume, where `1.0` is unchanged.
- `--tts-speaker-id <id-or-name>`: choose a provider speaker or voice preset when supported.
- `--tts-onnx-provider dml`: use Supertonic with DirectML on Windows.
- `--tts-steps <n>`: set Supertonic synthesis steps.
- `--tts-python <python.exe>`: choose the Python runtime used for subprocess-based TTS.
- Generated audio is cached under `data/audio_cache` by default.

For the local CUDA TTS runtime in this workspace, prefer:

```powershell
$env:PYTHONPATH = "src"
.\tools\runtime\python311-full\tools\python.exe -m topik_sim take topik-i-level-1-full-sample@0.1.0 --tts-provider melo
```

For the Anki-proven Supertonic runtime, plain Python can now call the same engine automatically when `H:\software\anki\.tts-venv` exists:

```powershell
$env:PYTHONPATH = "src"
python -m topik_sim take topik-i-level-1-full-sample@0.1.0 --tts-provider supertonic
```

To hear teaching notes read aloud after answers:

```powershell
python -m topik_sim take topik-i-level-1-full-sample@0.1.0 --speak-teaching --tts-play
```

To keep using older scripts that pass `--show-teaching`:

```powershell
python -m topik_sim take topik-i-level-1-full-sample@0.1.0 --show-teaching --speak-teaching --tts-play
```

To make listening audio quieter or louder:

```powershell
python -m topik_sim take topik-i-level-1-full-sample@0.1.0 --tts-volume 0.8
```

## `resume-attempt`

Loads a saved in-progress attempt and continues from the first unanswered question. If no attempt path is provided, it lists recent attempts and asks which one to load.

```powershell
python -m topik_sim resume-attempt data/attempts/<attempt_id>.json [--library <library_dir>] [--speak-question] [--speak-teaching]
python -m topik_sim resume-attempt [--attempt-dir <attempt_dir>] [--recent <n>]
```

Behavior:

- When no path is passed, scans recent attempt JSON files from `data/attempts`.
- Loads the pack from the attempt's saved `pack_id@pack_version`.
- Prints progress as `<answered>/<total> answered`.
- Skips already answered questions.
- Saves back to the same attempt JSON file after each new answer.
- Prints teaching feedback after every answer.
- Prints listening transcripts after the learner answers.
- Pauses after feedback; press Enter for the next question or enter `/replay`, `/r`, or `replay` to hear the just-answered question audio again.
- Completes and grades the attempt after the last unanswered question.

## `list-attempts`

Lists recent saved attempts without resuming them.

```powershell
python -m topik_sim list-attempts [--attempt-dir <attempt_dir>] [--limit <n>]
```

Each row includes status, answered count, pack reference, update time, attempt ID, and file path.

## `review-attempt`

Prints progress, score, and item-level feedback from a saved attempt.

```powershell
python -m topik_sim review-attempt data/attempts/<attempt_id>.json
```

## `grade`

Grades an answer file without interaction.

```powershell
python -m topik_sim grade <pack.json> <answers.json>
```

Accepted answer file shapes:

```json
{
  "answers": [
    { "question_id": "r-001", "response": "B" }
  ]
}
```

## `import-pack`

Validates and imports a content pack into the versioned library.

```powershell
python -m topik_sim import-pack <pack.json> [--library <library_dir>] [--replace]
```

Behavior:

- Copies the source pack to `packs/<pack_id>/<pack_version>.json`.
- Records metadata in `manifest.json`.
- Records a SHA-256 checksum for integrity checks.
- Rejects duplicate `pack_id@pack_version` imports unless `--replace` is used.

## `list-packs`

Lists packs currently imported into the content library.

```powershell
python -m topik_sim list-packs [--library <library_dir>]
```

## `validate-library`

Validates the library manifest, imported pack files, and recorded checksums.

```powershell
python -m topik_sim validate-library [--library <library_dir>]
```

## `speak`

Generates Korean TTS audio for direct text. This command remains available under `topik-sim`, but TTS-only workflows should prefer the dedicated `topik-tts` CLI.

```powershell
python -m topik_sim speak "안녕하세요. 오늘은 날씨가 좋습니다." [--tts-play]
python -m topik_sim.tts_cli speak "안녕하세요. 오늘은 날씨가 좋습니다."
```

`topik-sim speak` writes to the audio cache and prints the path. `topik-tts speak` plays directly by default and cleans up its temporary WAV. Use `--save` with `topik-tts speak` to keep the generated WAV and print its path.

Default provider:

- `supertonic`, using the same Supertonic setup as `H:\software\anki` when available.

CUDA provider:

- `melo`, using MeloTTS with `--tts-language KR` and `--tts-device cuda:0`.

Alternate provider:

- `xtts-v2`, using Coqui XTTS-v2. Requires `--tts-speaker-wav`.

## `list-tts-speakers`

Lists provider voices that can be passed to `--tts-speaker-id`. TTS-only workflows should prefer `topik-tts list-speakers`.

```powershell
python -m topik_sim list-tts-speakers [--tts-provider supertonic]
python -m topik_sim.tts_cli list-speakers [--tts-provider supertonic]
```

For Supertonic, use a printed voice preset such as `F1`. For MeloTTS Korean, use either the printed speaker name or numeric ID. XTTS-v2 uses `--tts-speaker-wav` instead of a built-in speaker list.

## Dedicated TTS CLI

Use this when you only want speech generation, voice listing, or WAV playback without the exam simulator commands.

```powershell
python -m topik_sim.tts_cli speak "안녕하세요."
python -m topik_sim.tts_cli speak "안녕하세요." --save
python -m topik_sim.tts_cli list-speakers
python -m topik_sim.tts_cli play data/audio_cache/<file>.wav
```

When installed as a package, the same commands are exposed as:

```powershell
topik-tts speak "안녕하세요."
topik-tts speak "안녕하세요." --save
topik-tts list-speakers
topik-tts play data/audio_cache/<file>.wav
```

See `docs/TTS_SETUP.md` for installation and GPU verification.

or:

```json
{
  "r-001": "B"
}
```

Output shape:

```json
{
  "pack_id": "topik-i-mini",
  "score": 1,
  "max_score": 2,
  "results": [
    {
      "question_id": "r-001",
      "correct": true,
      "points_awarded": 1,
      "max_points": 1,
      "response": "B",
      "feedback": {
        "summary": "...",
        "teaching_points": []
      }
    }
  ]
}
```
