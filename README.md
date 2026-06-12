# TOPIK Simulation Software

Sit authentic TOPIK I mock exams on your own computer: timed sections with listening audio, grading with teaching feedback on every question, and practice tools (drills, spaced review, flashcards, dictation, typing) to close the gaps — all offline.

## Quickstart

No programming knowledge needed:

1. **Install Python 3.9 or newer** — from [python.org/downloads](https://www.python.org/downloads/) (tick *"Add python.exe to PATH"* during setup) or from the Microsoft Store.
2. **Optional, recommended:** open a terminal and run `pip install prompt_toolkit` for the nicer shell (autocompletion, status toolbar). Everything also works without it.
3. **Launch:** double-click `topik.cmd` in this folder, or run `.\topik.cmd` from a terminal (PowerShell users can also run `.\topik.ps1`). The launcher works from any directory — no `PYTHONPATH`, no module syntax.
4. **First run:** say yes when the shell offers to import the bundled mock exams.
5. **Press Enter** at the prompt to open the guided menu (Take a test / Practice / Progress / Settings).

If something does not work, run `.\topik.cmd doctor` — it checks your Python, audio, and content setup line by line and tells you how to fix each problem. The full learner manual is `docs/USER_GUIDE.md`.

## Interactive Shell (recommended)

The launchers above are shorthand for:

```powershell
$env:PYTHONPATH = "src"
python -m topik_sim
```

This opens a persistent prompt styled after modern agent CLIs: history, slash-command autocompletion (with `prompt_toolkit`), and a status toolbar. **New here? Just press Enter** — a numbered menu walks you through everything by area (Take a test / Practice / Progress / Settings). Plain input answers the current question; anything starting with `/` is a command and never counts as an answer:

- `/take topik-i-level-1-full-sample` — start a test (pack ids autocomplete); `/resume`, `/pause`, `/attempts`
- `/say 안녕하세요` — pronounce any sentence mid-question; `/hint` reveals one vocabulary item
- `/replay`, `/transcript`, `/skip`
- `/drill` — re-practice the questions you missed in your last completed attempt
- `/review` — spaced-repetition session over everything you have missed before
- `/flashcards <pack>`, `/grammar`, `/recall`, `/dictation <pack>` — vocabulary cards, grammar patterns, type-the-Korean recall, listen-and-type practice
- `/typing`, `/keyboard on` — Korean keyboard trainer and 두벌식 layout chart with keystroke hints everywhere you type
- `/stats`, `/report` — accuracy trends and a Markdown study sheet
- `/tts volume 0.8`, `/tts off` — change speech settings live
- `/help`, `/quit`

Workspace defaults (TTS voice/volume, directories, shell behavior) can live in `topik.config.json`; see `examples/topik.config.example.json`.

## Classic CLI

Run from this folder:

```powershell
$env:PYTHONPATH = "src"
python -m topik_sim validate-content examples/content/topik_i_mini_pack.json
python -m topik_sim import-pack examples/content/topik_i_mini_pack.json
python -m topik_sim list-packs
python -m topik_sim inspect-content examples/content/topik_i_mini_pack.json
python -m topik_sim take topik-i-mini-pack --section reading --limit 2
python -m topik_sim list-attempts
python -m topik_sim resume-attempt data/attempts/<attempt_id>.json
python -m topik_sim resume-attempt
python -m topik_sim drill data/attempts/<attempt_id>.json
python -m topik_sim review
python -m topik_sim review-writing data/attempts/<attempt_id>.json
python -m topik_sim stats
python -m topik_sim report data/attempts/<attempt_id>.json --output exports/report.md
python -m topik_sim audio warm topik-i-level-1-full-sample@0.1.0
python -m topik_sim audio stats
python -m topik_sim audio prune --max-mb 500
python -m topik_sim audio compress --older-than-days 14
python -m topik_sim audio bundle topik-i-level-1-full-sample@0.1.0
python -m topik_sim.tts_cli speak "안녕하세요. 오늘은 날씨가 좋습니다."
python -m topik_sim.tts_cli speak "안녕하세요. 오늘은 날씨가 좋습니다." --save
python -m topik_sim grade examples/content/topik_i_mini_pack.json examples/answers/sample_answers.json
```

For the Anki-proven local Korean TTS path, the default provider now uses Supertonic and automatically reuses `H:\software\anki\.tts-venv` when it exists:

```powershell
$env:PYTHONPATH = "src"
python -m topik_sim take topik-i-level-1-full-sample@0.1.0
```

During a listening question, type `/replay` at the answer prompt to hear the audio again. After answering, the app pauses on the explanation; press Enter for the next question or type `/replay` to hear the previous question audio again. Use `--tts-volume 0.8` or another gain value to adjust generated audio volume.

## Project Overview

This workspace is for building a TOPIK exam simulator that can run practice exams, grade answers, and return teaching-focused feedback.

The project is intentionally split into two workstreams:

1. Software building: CLI, validation, grading, feedback flow, storage, and later UI.
2. Content authoring: TOPIK question packs, answers, explanations, vocabulary, grammar notes, and teaching guidance.

The handoff between those workstreams is the content contract in `docs/CONTENT_CONTRACT.md` and the CLI contract in `docs/CLI_CONTRACT.md`.

## Workspace Map

- `AGENTS.md`: standing instructions for future coding agents.
- `CLAUDE.md`: working manual for Claude Code sessions (commands, architecture, test-implement loop).
- `.claude/agents/topik-test-author.md`: agent that authors and verifies exam packs end to end.
- `context/`: concise context files for session handoff.
- `skills/topik-content-authoring/`: reusable agent skill for adding exams and tutorials.
- `docs/`: architecture, CLI contract, content contract, extension framework, audio design, and roadmap.
- `docs/TTS_SETUP.md`: optional local GPU Korean TTS setup.
- `src/topik_sim/`: simulator CLI, interactive shell, and core logic.
- `examples/`: minimal content and answer files used to prove the contract.
- `content/source/`: tracked source packs; `content/library/` is the generated import library (ignored).
- `tests/`: offline unittest suite for contracts, grading, audio cache, and the shell.

Runtime data is written under `data/` and ignored by Git. Content authors should keep source packs in `examples/content/` or a future `content/source/` folder, then import them into the local library with `import-pack`.

Optional Korean TTS uses local model dependencies. See `docs/TTS_SETUP.md`.
