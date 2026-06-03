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
- Prints teaching notes for missed questions by default.
- `--show-teaching` also prints teaching notes for correct answers.

## `take`

Runs an interactive test and saves the attempt after each answer.

```powershell
python -m topik_sim take <pack.json-or-pack_ref> [--library <library_dir>] [--attempt-dir <attempt_dir>] [--section <section_id>] [--limit <n>] [--show-teaching] [--speak-question] [--speak-teaching]
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
- At the answer prompt, enter `/replay`, `/r`, or `replay` to play the current question audio again.
- `--show-transcript`: show listening transcripts for content debugging.
- `--no-listening-audio`: disable automatic listening audio.
- `--speak-question`: generate Korean audio for non-listening question passages too.
- `--speak-teaching`: generate Korean audio for vocabulary and grammar examples in feedback.
- `--tts-play`: play generated audio immediately.
- `--tts-device cuda:0`: run provider on the first CUDA GPU.
- `--tts-volume <gain>`: set generated WAV volume, where `1.0` is unchanged.
- `--tts-speaker-id <id-or-name>`: choose a provider speaker when supported.
- Generated audio is cached under `data/audio_cache` by default.

For the local CUDA TTS runtime in this workspace, prefer:

```powershell
$env:PYTHONPATH = "src"
.\tools\runtime\python311-full\tools\python.exe -m topik_sim take topik-i-level-1-full-sample@0.1.0
```

To hear teaching notes after missed answers:

```powershell
.\tools\runtime\python311-full\tools\python.exe -m topik_sim take topik-i-level-1-full-sample@0.1.0 --speak-teaching --tts-play
```

To hear teaching notes for correct answers too:

```powershell
.\tools\runtime\python311-full\tools\python.exe -m topik_sim take topik-i-level-1-full-sample@0.1.0 --show-teaching --speak-teaching --tts-play
```

To make listening audio quieter or louder:

```powershell
.\tools\runtime\python311-full\tools\python.exe -m topik_sim take topik-i-level-1-full-sample@0.1.0 --tts-volume 0.8
```

## `review-attempt`

Prints the score and item-level feedback from a saved attempt.

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

Generates Korean TTS audio for direct text.

```powershell
python -m topik_sim speak "안녕하세요. 오늘은 날씨가 좋습니다." [--tts-play]
```

Default provider:

- `melo`, using MeloTTS with `--tts-language KR` and `--tts-device cuda:0`.

Alternate provider:

- `xtts-v2`, using Coqui XTTS-v2. Requires `--tts-speaker-wav`.

## `list-tts-speakers`

Lists provider voices that can be passed to `--tts-speaker-id`.

```powershell
python -m topik_sim list-tts-speakers [--tts-provider melo] [--tts-language KR]
```

For MeloTTS Korean, use either the printed speaker name or numeric ID. XTTS-v2 uses `--tts-speaker-wav` instead of a built-in speaker list.

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
