---
name: topik-content-authoring
description: Add or update TOPIK simulator content, including exam packs, answer keys, explanations, vocabulary, grammar notes, common mistakes, and tutorial-style teaching material. Use when Codex is asked to create TOPIK questions, fill content JSON files, revise answer explanations, add learning tutorials, validate content packs, import packs into the versioned library, or prepare content handoff for the TOPIK simulator.
---

# TOPIK Content Authoring

## Core Rule

Keep content work separate from simulator code. Add or edit source packs, validate them with the project CLI, and only change code when the content contract cannot express the requested material.

Use original, licensed, public-domain, or user-provided content only. Do not reproduce copyrighted TOPIK questions unless the user provides rights to use them.

## Start Here

1. Read the repository files `docs/CONTENT_CONTRACT.md` and `docs/DATA_PIPELINE.md`.
2. If adding exam questions, read `references/exam-pack-authoring.md`.
3. If adding tutorials or teaching material, read `references/tutorial-authoring.md`.
4. Inspect `examples/content/topik_i_mini_pack.json` as the executable example.
5. Run validation before handoff.

If Korean text looks garbled in shell output, do not rewrite it from that display. Read and write files as UTF-8.

## Workflow

1. Choose or create a source pack path, usually under `examples/content/` during early development or `content/source/` once a larger content corpus exists.
2. Set stable `pack_id`, bumped `pack_version`, and clear `title`.
3. Add sections and questions following the content contract.
4. Include answer keys and teaching material for every question.
5. Validate the source pack:

```powershell
$env:PYTHONPATH = "src"
python -m topik_sim validate-content <pack.json>
```

6. Import the pack to prove the versioned pipeline:

```powershell
python -m topik_sim import-pack <pack.json> --replace
python -m topik_sim validate-library
```

7. Optionally run a learner smoke test:

```powershell
python -m topik_sim take <pack_id>@<pack_version> --limit 2
```

## Content Quality Bar

- Every `question_id` must be stable and unique within the pack.
- Every question must have a correct answer and explanation summary.
- Teaching notes must help both incorrect and correct learners.
- Vocabulary entries should be concise and learner-facing.
- Grammar notes should name the pattern, explain its role, and include an example when useful.
- Common mistakes should identify likely confusion, not merely repeat the correct answer.
- Bump `pack_version` whenever imported content changes.

## Handoff

End a content-authoring pass with:

- Files added or changed.
- Validation commands run and whether they passed.
- Pack references created, such as `topik-i-reading-set-001@0.1.0`.
- Any unresolved content gaps or rights/source questions.

