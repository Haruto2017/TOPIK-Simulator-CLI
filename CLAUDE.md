# CLAUDE.md

TOPIK exam simulator: a Python CLI + interactive shell that administers practice exams, grades answers, gives teaching feedback, and speaks Korean via local TTS. `AGENTS.md` holds the standing priorities; this file is the working manual.

## Commands

```powershell
$env:PYTHONPATH = "src"                          # always, unless installed
python -m unittest discover -s tests             # full test suite (must be OK before commit)
python -m topik_sim                              # interactive shell (default entry)
python -m topik_sim validate-content <pack.json> # content contract check
python -m topik_sim import-pack <pack.json> --replace
python -m topik_sim validate-library
python -m topik_sim audio warm <pack_ref>        # pre-generate listening audio
```

Tests are stdlib `unittest`, run offline, and mock all TTS synthesis — never require a GPU or model download.

## Architecture

- `src/topik_sim/content.py` — pack loading + contract validation
- `src/topik_sim/question_types.py` — pluggable answer formats (validate + grade, `manual` flag for essays); register a spec to add a format
- `src/topik_sim/grading.py` — scoring + teaching feedback assembly
- `src/topik_sim/attempts.py` / `session.py` — attempt persistence, timing, and the present→submit→advance→finalize state machine
- `src/topik_sim/activities.py` / `srs.py` — attempt builders (exam, drill) and the spaced-repetition review queue
- `src/topik_sim/flashcards.py` / `dictation.py` — shell-side practice modes
- `src/topik_sim/stats.py` / `report.py` — cross-attempt accuracy stats and Markdown study reports
- `src/topik_sim/library.py` — versioned content library with checksums
- `src/topik_sim/config.py` — `topik.config.json` workspace defaults (flags always win)
- `src/topik_sim/tts.py`, `audio_cache.py`, `prefetch.py` — providers, content-addressed WAV cache with Opus cold storage, background prefetch (`docs/AUDIO_DESIGN.md`)
- `src/topik_sim/ui/` — interactive shell (commands registry, renderer, prompt_toolkit frontend with plain fallback)
- `src/topik_sim/cli.py` — argparse surface; documented in `docs/CLI_CONTRACT.md`

Extension guide for new test formats and learning tools: `docs/FRAMEWORK.md`.

## Test-Implement Loop

1. Start from a failing or new `unittest` in `tests/` (drive `Shell.handle_line` for shell behavior — no terminal needed).
2. Implement the smallest change in `src/topik_sim/`.
3. Run the full suite; it must pass.
4. If command behavior or content schema changed, update `docs/CLI_CONTRACT.md` / `docs/CONTENT_CONTRACT.md` in the same change, with a migration note when the contract breaks.
5. Commit one logical unit with an imperative subject line.

## Conventions

- Core stays standard-library only; `prompt_toolkit` is optional and every frontend must degrade to plain `input()`.
- Read and write files as UTF-8. If Korean looks garbled in shell output, fix the encoding — never retype the text from the garbled display.
- `data/` and `content/library/` are gitignored runtime artifacts; `content/source/` and `examples/content/` are tracked sources.
- Content work belongs to the content-authoring session: use the `topik-test-author` agent (`.claude/agents/topik-test-author.md`), which loads `skills/topik-content-authoring/SKILL.md`. Software sessions do not author exam content, and content sessions do not edit simulator code.
- Original, licensed, public-domain, or user-provided exam content only.
