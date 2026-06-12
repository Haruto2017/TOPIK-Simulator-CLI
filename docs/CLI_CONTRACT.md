# CLI Contract

All commands are run from the repository root.

If the package is not installed, set `PYTHONPATH=src` first.

Running `python -m topik_sim` with no arguments opens the interactive shell (see `shell`).

## Configuration

Optional workspace defaults live in `topik.config.json` at the repo root (or a file pointed to by the `TOPIK_CONFIG` environment variable). CLI flags always override the config; the config overrides built-in defaults. Sections: `tts` (provider, voice, volume, speed, steps, onnx_provider, device, language, output_dir), `paths` (library, attempts), `shell` (audio, show_transcript). See `examples/topik.config.example.json`.

## `shell`

Interactive session styled after modern agent CLIs: a persistent prompt with history, slash-command autocompletion (when `prompt_toolkit` is installed), and a status toolbar. Plain input answers the current question; input starting with `/` is always a command and is never submitted as an answer.

```powershell
python -m topik_sim shell [--library <dir>] [--attempt-dir <dir>] [--show-transcript] [TTS options]
python -m topik_sim   # same as: shell
```

First-time navigation:

- Pressing Enter at an idle prompt (or `/menu`, alias `/m`) opens a numbered menu of functional areas — Take a test, Practice, Progress, Library & settings, While answering, Shell. Picking a number drills into that area's commands; picking again runs one. Enter goes back, then closes. Slash commands keep working at every level.
- `/help` lists commands grouped by the same categories.
- `/take`, `/flashcards`, and `/dictation` with no argument open a numbered pack picker instead of demanding a pack id.

Slash commands:

- `/take [pack] [section] [limit]`: start a test from a library ref or pack file; with no argument a pack picker opens. Pack ids autocomplete; typos get close-match suggestions.
- `/resume [n|path]`: resume an in-progress attempt. With no argument and several candidates, an interactive numbered picker opens (type the number, Enter cancels); a single candidate resumes directly. Tab after `/resume ` completes attempt numbers with status and progress.
- `/drill [n|path]`: build and run a drill over the questions missed in a completed attempt. Same picker and completion behavior as `/resume`, over completed attempts.
- `/review [pack]`: spaced-repetition session over due previously-missed questions (see `review`).
- `/flashcards <pack>` (alias `/cards`): vocabulary card drill built from the pack's teaching notes; Enter flips, y/n grades.
- `/dictation <pack> [limit]`: hear listening transcripts and type them; diff-based feedback with accuracy percentages.
- `/grammar [pack] [count]` (alias `/gram`): grammar pattern cards built from teaching explanations — front shows the pattern, the flip shows its explanation and an example sentence (`/say` speaks it). Scoped to one pack, or to every imported pack when bare (default 20 cards; `count` overrides).
- `/recall [pack] [count]` (alias `/translate`): active vocabulary production — the English gloss is shown and the Korean must be typed. Any Korean word taught with that gloss counts as correct; a miss reveals the answer with its 두벌식 keys. Pack-scoped or library-wide when bare (default 10 words).
- `/typing [pack] [count]`: Korean keyboard trainer ramping jamo → syllables → real words. The word stage uses the given pack's vocabulary, or the union of every imported pack's vocabulary when no pack is named; random syllables are only the empty-library fallback. A miss reveals the 두벌식 keystrokes.
- `/keyboard [on|off|pin|unpin]` (alias `/kb`): print the 두벌식 layout chart. `on` enables keyboard mode: a compact chart is pinned to the bottom toolbar — hovering above the input line, never scrolled away — and keystroke hints (`Keys: skf·Tl`, uppercase = Shift) render consistently in dictation feedback, flashcard backs, and `/typing` misses. `pin`/`unpin` control just the docked chart. The hovering chart needs the prompt_toolkit frontend; the plain fallback prints the chart inline only. Defaults from `shell.keyboard_hints` / `shell.keyboard_pinned` in the config.
- `/attempts`, `/packs`: list saved attempts / imported packs.
- `/say <text>` (alias `/speak`): pronounce any sentence aloud without affecting the current answer. With no text during flashcards, speaks the current card.
- `/hint`: reveal one vocabulary item for the current question per call.
- `/replay` (alias `/r`): replay the current question audio.
- `/transcript` (alias `/t`): reveal the active listening transcript.
- `/skip`: submit a blank answer for the current question.
- `/pause`: save and leave the current test (or stop flashcards/dictation early).
- `/status`: progress, running score, and TTS settings.
- `/stats`: per-skill accuracy and trends across completed attempts.
- `/report [n|path]`: write a Markdown study report for a completed attempt (interactive picker like `/resume`).
- `/tts [on|off|volume <x>|speed <x>|provider <p>|voice <v>]`: change speech settings mid-session.
- `/help`, `/quit`.

Behavior:

- Attempts are saved after every answer, exactly like `take`; quitting or crashing never loses progress.
- Listening questions auto-play audio and hide transcripts until after the answer.
- The next question's audio is prefetched on a background thread while the learner answers (see `docs/AUDIO_DESIGN.md`).
- Full-pack attempts are timed against the sections' `time_limit_minutes`: the toolbar counts down and summaries report pace.
- Completed attempts feed the spaced-repetition queue; the shell reports how many items are due.
- Falls back to a plain `input()` prompt when `prompt_toolkit` is unavailable.

## `drill`

Non-interactive-shell variant of `/drill`: re-practice the questions missed in a completed attempt.

```powershell
python -m topik_sim drill data/attempts/<attempt_id>.json [--library <dir>] [--attempt-dir <dir>] [TTS options]
```

Behavior:

- Requires a completed attempt; fails with guidance otherwise.
- Creates a new attempt with `"activity": "drill"` restricted to the missed question ids.
- Grades and saves like `take`.

## `review`

Spaced-repetition review across attempts. Misses enter a Leitner queue (box 1, due immediately); correct reviews promote with growing intervals (1/2/4/7/15 days); a top-box success retires the item. The queue lives at `<attempt_dir>/review_queue.json`.

```powershell
python -m topik_sim review                # list due counts per pack
python -m topik_sim review <pack_id> [--limit <n>] [--attempt-dir <dir>] [--library <dir>] [TTS options]
```

## `review-writing`

Scores essay answers in a completed attempt against their rubric (see the essay answer type in `docs/CONTENT_CONTRACT.md`). Prompts for each criterion, recomputes the attempt score, and saves in place. Half marks or better counts as correct.

```powershell
python -m topik_sim review-writing data/attempts/<attempt_id>.json [--library <dir>]
```

## `stats`

Per-skill accuracy, average pace, recent attempt trend, and per-pack best/last scores across completed attempts.

```powershell
python -m topik_sim stats [--attempt-dir <dir>] [--library <dir>]
```

## `report`

Markdown study report for a completed attempt: misses with correct answers, vocabulary, grammar, and common mistakes to review.

```powershell
python -m topik_sim report data/attempts/<attempt_id>.json [--output report.md] [--library <dir>]
```

## `audio`

Audio cache management. See `docs/AUDIO_DESIGN.md` for the design.

```powershell
python -m topik_sim audio stats [--audio-dir <dir>]
python -m topik_sim audio prune [--max-mb <n>] [--older-than-days <n>] [--dry-run] [--audio-dir <dir>]
python -m topik_sim audio warm <pack_ref> [--all-questions] [--teaching] [--voices F1,M1] [--library <dir>] [TTS options]
python -m topik_sim audio compress [--older-than-days <n>] [--bitrate 24k] [--audio-dir <dir>]
python -m topik_sim audio bundle <pack_ref> [--output <zip>] [--all-questions] [--teaching] [TTS options]
```

Behavior:

- `stats`: file count (wav/opus split), total size, least-recently-used timestamp.
- `prune`: deletes least-recently-used entries (wav and opus) until the cache satisfies the constraints; requires at least one of `--max-mb` / `--older-than-days`.
- `warm`: pre-generates listening audio for a pack (all passages with `--all-questions`, teaching audio with `--teaching`, several voice presets with `--voices`).
- `compress`: transcodes cold WAVs to Opus via ffmpeg; playback restores entries transparently on use.
- `bundle`: warms a pack and exports its audio plus a text→file manifest as one zip (default under `exports/`).
- Volume is applied at playback time and does not multiply cached files.

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
