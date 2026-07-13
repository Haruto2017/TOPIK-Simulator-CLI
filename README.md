# TOPIK Simulation Software

Sit authentic TOPIK I mock exams on your own computer: timed sections with listening audio, grading with teaching feedback on every question, and practice tools (drills, spaced review, flashcards, dictation, typing) to close the gaps — all offline.

## Quickstart

No programming knowledge needed:

1. **Install Python 3.9 or newer** — from [python.org/downloads](https://www.python.org/downloads/) (tick *"Add python.exe to PATH"* during setup) or from the Microsoft Store.
2. **Optional, recommended:** open a terminal and run `pip install prompt_toolkit` for the nicer shell (autocompletion, status toolbar). Everything also works without it.
3. **Launch:** double-click `topik.cmd` in this folder, or run `.\topik.cmd` from a terminal (PowerShell users can also run `.\topik.ps1`). The launcher works from any directory — no `PYTHONPATH`, no module syntax. **macOS/Linux:** there is no launcher — run `pip install -e ".[shell]"` once from this folder, then launch with `topik-sim` (or `PYTHONPATH=src python3 -m topik_sim` without installing). TTS setup on macOS/Linux: create a venv and `pip install -r requirements-tts.txt` into it as `.venv-tts` (the PowerShell script's steps, run by hand).
4. **First run:** say yes when the shell offers to import the bundled mock exams.
5. **Press Enter** at the prompt to open the guided menu (Take a test / Practice / Progress / Settings).
6. **Optional — spoken listening audio:** run `.\setup-tts.ps1` once (see *Korean speech* below). Exams work without it; transcripts are shown instead of audio.

If something does not work, run `.\topik.cmd doctor` — it checks your Python, audio, and content setup line by line and tells you how to fix each problem. The full learner manual is `docs/USER_GUIDE.md`.

Prefer a proper install? `pip install -e .[shell]` from this folder gives you the `topik-sim` command (with the nicer prompt included); the launchers keep working either way.

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
- `/homework <pack> [lesson]` — textbook-style homework for each course lesson, auto-generated from what it taught: recall, meaning and pattern multiple choice, and fill-the-blank; best scores tracked per lesson
- `/flashcards <pack>`, `/grammar`, `/recall`, `/dictation <pack>` — vocabulary cards, grammar patterns, type-the-Korean recall, listen-and-type practice
- `/conjugate [form]` — practice conjugating verbs across 16 endings (present/past/future, -(으)면, -(으)ㄹ 수 있어요, -고 싶어요, honorific, …); a rule-based class engine conjugates every irregular class (ㅂ, ㄷ, ㅅ, 르, 으, ㅎ) correctly, never guessed
- `/hangul` — learn to *read* Korean from zero: letter sounds, syllable blocks, 받침, and worked examples; `/lookup 학생` searches everything your packs teach
- `/numbers [category]` — Korean number practice across both systems (Sino- and native-Korean): dates, counting objects, money, time, math, phone numbers, ordinals — every answer typed in Hangul, no digits; `/numbers learn` shows the tables first
- `/typing`, `/keyboard on` — Korean keyboard trainer and 두벌식 layout chart with keystroke hints everywhere you type
- `/stats`, `/report` — accuracy trends and a Markdown study sheet
- `/tts volume 0.8`, `/tts off` — change speech settings live
- `/help`, `/quit`

Workspace defaults (TTS voice/volume, directories, shell behavior) can live in `topik.config.json`; see `examples/topik.config.example.json`.

## Web UI

Prefer a browser? The same simulator ships a local web app:

```powershell
$env:PYTHONPATH = "src"          # Windows PowerShell
python -m topik_sim web
```

```bash
PYTHONPATH=src python3 -m topik_sim web    # macOS / Linux (or just: topik-sim web)
```

Your browser opens at `http://127.0.0.1:8765` with everything the shell has: timed mock exams with listening audio and teaching feedback, resume/drill/spaced review, guided courses with per-lesson homework, the full practice suite (flashcards, grammar, recall, typing, numbers, dictation, sentence writing, Korea facts), progress charts, study reports, and live TTS settings. It shares the shell's attempt files and library — pause a test in one, resume in the other. Local and offline: the server binds to localhost only and makes no external requests.

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

## Korean speech (listening audio)

Listening questions are spoken by a local TTS engine. One-time setup:

```powershell
.\setup-tts.ps1
```

This creates a private `.venv-tts` environment and installs the default Supertonic engine (DirectML — works on any DirectX 12 GPU, CUDA not required; `--tts-onnx-provider cpu` for CPU-only machines). The simulator finds it automatically; the voice model downloads once the first time audio plays. Verify anytime with `.\topik.cmd doctor`.

Without TTS everything still works — listening questions show their transcripts instead. During a listening question, `/replay` plays the audio again, and `/tts volume 0.8` adjusts loudness live. Advanced options (other providers, an existing Supertonic environment via `TOPIK_SUPERTONIC_PYTHON`): see `docs/TTS_SETUP.md`.

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

## License & Security

MIT — see [LICENSE](LICENSE). The simulator is a local, offline tool; [SECURITY.md](SECURITY.md) describes the threat model, what the optional components may download, and where your data lives.
