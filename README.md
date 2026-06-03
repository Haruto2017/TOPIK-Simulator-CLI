# TOPIK Simulation Software

This workspace is for building a TOPIK exam simulator that can run practice exams, grade answers, and return teaching-focused feedback.

The project is intentionally split into two workstreams:

1. Software building: CLI, validation, grading, feedback flow, storage, and later UI.
2. Content authoring: TOPIK question packs, answers, explanations, vocabulary, grammar notes, and teaching guidance.

The handoff between those workstreams is the content contract in `docs/CONTENT_CONTRACT.md` and the CLI contract in `docs/CLI_CONTRACT.md`.

## Current CLI

Run from this folder:

```powershell
$env:PYTHONPATH = "src"
python -m topik_sim validate-content examples/content/topik_i_mini_pack.json
python -m topik_sim import-pack examples/content/topik_i_mini_pack.json
python -m topik_sim list-packs
python -m topik_sim inspect-content examples/content/topik_i_mini_pack.json
python -m topik_sim take topik-i-mini-pack --section reading --limit 2
python -m topik_sim grade examples/content/topik_i_mini_pack.json examples/answers/sample_answers.json
```

## Workspace Map

- `AGENTS.md`: standing instructions for future coding agents.
- `context/`: concise context files for session handoff.
- `docs/`: architecture, CLI, content contract, and roadmap.
- `src/topik_sim/`: simulator CLI and core logic.
- `examples/`: minimal content and answer files used to prove the contract.
- `tests/`: focused tests for contract validation and grading.

Runtime data is written under `data/` and ignored by Git. Content authors should keep source packs in `examples/content/` or a future `content/source/` folder, then import them into the local library with `import-pack`.
