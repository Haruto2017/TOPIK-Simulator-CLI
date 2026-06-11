# Content-Authoring Context

Content authors should load `skills/topik-content-authoring/SKILL.md`, then create JSON exam packs that follow `docs/CONTENT_CONTRACT.md`. In Claude Code, delegate whole-exam authoring to the `topik-test-author` agent (`.claude/agents/topik-test-author.md`).

Expected workflow:

1. Create or edit a pack file.
2. Validate it with `python -m topik_sim validate-content <pack.json>`.
3. Import it with `python -m topik_sim import-pack <pack.json>`.
4. Run `python -m topik_sim inspect-content <pack.json>` to review section and question counts.
5. Optionally run `python -m topik_sim take <pack_id>` to experience the pack.
6. For listening content, run `python -m topik_sim audio warm <pack_id>@<version>` so first playback is instant (skip if no TTS runtime).

Content pack expectations:

- Use original, licensed, public-domain, or user-provided material.
- Include answer keys and teaching notes for every question.
- Add Korean vocabulary and grammar explanations where useful.
- Keep each question independently addressable by a stable `question_id`.
- Bump `pack_version` whenever imported content changes.
