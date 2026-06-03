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
- CLI commands are documented in `docs/CLI_CONTRACT.md`.
- Sample content is intentionally tiny and original; it is for contract testing, not a real exam.

## Session Split

For software-building sessions:

- Improve CLI behavior, grading, storage, feedback, UX, tests, and eventually UI.
- Update docs when command behavior or content schema changes.
- Add migration notes if the content contract changes.

For content-authoring sessions:

- Add or revise exam packs under `content/` or `examples/content/`.
- Run `python -m topik_sim validate-content <pack.json>` before handoff.
- Run `python -m topik_sim import-pack <pack.json>` to test the versioned loading pipeline.
- Do not change simulator code unless the content contract is insufficient.
