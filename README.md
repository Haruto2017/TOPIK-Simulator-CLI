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
python -m topik_sim list-attempts
python -m topik_sim resume-attempt data/attempts/<attempt_id>.json
python -m topik_sim resume-attempt
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

## Workspace Map

- `AGENTS.md`: standing instructions for future coding agents.
- `context/`: concise context files for session handoff.
- `skills/topik-content-authoring/`: reusable agent skill for adding exams and tutorials.
- `docs/`: architecture, CLI, content contract, and roadmap.
- `docs/TTS_SETUP.md`: optional local GPU Korean TTS setup.
- `src/topik_sim/`: simulator CLI and core logic.
- `examples/`: minimal content and answer files used to prove the contract.
- `tests/`: focused tests for contract validation and grading.

Runtime data is written under `data/` and ignored by Git. Content authors should keep source packs in `examples/content/` or a future `content/source/` folder, then import them into the local library with `import-pack`.

Optional Korean TTS uses local model dependencies. See `docs/TTS_SETUP.md`.
