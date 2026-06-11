# Software-Building Context

Goal: build a TOPIK simulation app that can administer practice exams, grade answers, and teach from submitted answers.

Current phase:

- Stable CLI and content contract, saved attempts, versioned content library.
- Interactive shell (`python -m topik_sim`) with slash commands; plain input answers, `/commands` never do.
- Local Korean TTS with a content-addressed audio cache, warming, pruning, and background prefetch.
- Pluggable question types and activities (see `docs/FRAMEWORK.md`).
- Keep implementation dependency-light: stdlib core, `prompt_toolkit` optional.

Working rules:

- Follow the test-implement loop in `CLAUDE.md` / `AGENTS.md`; run the unittest suite before every commit.
- Preserve `docs/CLI_CONTRACT.md` and `docs/CONTENT_CONTRACT.md`; update them with behavior changes.
- Make the content workflow safe for a separate session dedicated to questions, answers, and teaching.

Non-goals for this phase:

- Real TOPIK copyrighted question import.
- User account system.
- Advanced natural-language grading inline in the answer loop.
