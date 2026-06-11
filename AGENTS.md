# Agent Instructions

This repository is for TOPIK simulation software. Keep the software and exam content cleanly separated.

## Priorities

- Preserve the CLI/content contract before adding features.
- Prefer small, testable modules over large scripts.
- Keep generated or user-authored exam content out of core code.
- Make content validation strict enough that a separate content-authoring session can work independently.
- Use original, licensed, public-domain, or user-provided content only. Do not scrape or reproduce copyrighted TOPIK materials without permission.

## Current Architecture

- Runtime code lives in `src/topik_sim/`.
- Content packs are JSON files following `docs/CONTENT_CONTRACT.md`.
- Imported content libraries are versioned with `docs/DATA_PIPELINE.md`.
- CLI commands are documented in `docs/CLI_CONTRACT.md`; `python -m topik_sim` with no arguments opens the interactive shell.
- New test formats and learning activities plug in through the registries described in `docs/FRAMEWORK.md`.
- Generated speech follows the cache design in `docs/AUDIO_DESIGN.md`.
- Sample content is intentionally tiny and original; it is for contract testing, not a real exam.
- `CLAUDE.md` is the working manual for Claude Code sessions, including the test-implement loop.

## Test-Implement Loop

1. Start from a failing or new `unittest` under `tests/` (shell behavior is tested by driving `Shell.handle_line` with scripted lines).
2. Implement the smallest change in `src/topik_sim/`.
3. Run `python -m unittest discover -s tests` with `PYTHONPATH=src`; the suite is offline and mocks TTS.
4. Update `docs/CLI_CONTRACT.md` / `docs/CONTENT_CONTRACT.md` in the same change when behavior or schema moves.
5. Commit one logical unit per commit with an imperative subject.

## Session Split

For software-building sessions:

- Improve CLI behavior, grading, storage, feedback, UX, tests, and eventually UI.
- Update docs when command behavior or content schema changes.
- Add migration notes if the content contract changes.

For content-authoring sessions:

- Load `skills/topik-content-authoring/SKILL.md` before adding exam packs, answer explanations, or tutorial material. In Claude Code, the `topik-test-author` agent (`.claude/agents/topik-test-author.md`) runs the full authoring loop.
- Add or revise exam packs under `content/` or `examples/content/`.
- Run `python -m topik_sim validate-content <pack.json>` before handoff.
- Run `python -m topik_sim import-pack <pack.json>` to test the versioned loading pipeline.
- Do not change simulator code unless the content contract is insufficient.
