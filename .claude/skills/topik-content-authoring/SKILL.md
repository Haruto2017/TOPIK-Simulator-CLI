---
name: topik-content-authoring
description: Add or update TOPIK simulator content - exam packs, answer keys, explanations, vocabulary, grammar notes, and tutorial material. Use when asked to create TOPIK questions, fill or revise content JSON packs, validate or import packs, or prepare content handoff. Not for simulator code changes.
---

# TOPIK Content Authoring (Claude Code)

The canonical authoring guide lives at `skills/topik-content-authoring/SKILL.md` (shared across agent tools). Read it first, then its `references/exam-pack-authoring.md` or `references/tutorial-authoring.md` depending on the task.

Hard requirements, in order:

1. Content is data only — never edit `src/` in a content session. If the contract in `docs/CONTENT_CONTRACT.md` cannot express the material, report the gap.
2. Original, licensed, public-domain, or user-provided content only.
3. Run the verification loop before handoff (PowerShell, from the repo root):

```powershell
$env:PYTHONPATH = "src"
python -m topik_sim validate-content <pack.json>
python -m topik_sim import-pack <pack.json> --replace
python -m topik_sim validate-library
python -m topik_sim grade <pack.json> <sample_answers.json>
```

4. For listening content, prefer warming audio so first playback is instant: `python -m topik_sim audio warm <pack_id>@<version>` (skip gracefully when no TTS runtime exists).
5. UTF-8 in, UTF-8 out. Never rewrite Korean text from garbled console output.

For end-to-end authoring of a whole exam, delegate to the `topik-test-author` agent (`.claude/agents/topik-test-author.md`), which runs this loop itself.
