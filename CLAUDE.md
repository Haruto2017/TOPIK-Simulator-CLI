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
./setup-tts-qwen3.sh                             # optional: Qwen3-TTS engine on Apple Silicon (.venv-qwen3)
```

Tests are stdlib `unittest`, run offline, and mock all TTS synthesis — never require a GPU or model download.

## Architecture

- `src/topik_sim/content.py` — pack loading + contract validation
- `src/topik_sim/question_types.py` — pluggable answer formats (validate + grade, `manual` flag for essays); register a spec to add a format
- `src/topik_sim/grading.py` — scoring + teaching feedback assembly
- `src/topik_sim/attempts.py` / `session.py` — attempt persistence, timing, and the present→submit→advance→finalize state machine
- `src/topik_sim/activities.py` / `srs.py` — attempt builders (exam, drill) and the spaced-repetition review queue
- `src/topik_sim/courses.py` / `homework.py` — guided courses over a pack and per-lesson auto-generated homework (recall, meaning/pattern choice, cloze, sentence composing, conjugation) with saved best scores
- `src/topik_sim/conjugation.py` — a class-based Korean conjugation engine (classify verb → derive 아/어 and 으 stems → assemble 16 endings across tense/politeness/connectives/modality, all irregular classes handled by rule); powers `/conjugate`, the web Conjugation mode, and homework conjugation/cloze items. Never guesses: verbs it cannot resolve with certainty are skipped.
- `src/topik_sim/vocab_srs.py` — spaced-repetition scheduler for vocabulary (Leitner boxes, `vocab_review.json`); the `/vocab` review session and web Vocabulary-review mode. Distinct from `srs.py`, which schedules missed exam questions.
- `src/topik_sim/pronunciation.py` — curated sound-change rules (연음/경음화/비음화/유음화/격음화/구개음화/ㅎ) with spelled→spoken examples; `/sounds` reference + drill.
- `src/topik_sim/curriculum.py` — the staged study path (`content/curriculum/`): textbook-style units resolved at runtime to courses/compose/dialogues/drills, with progress from the existing trackers; `/path` + web Study Path
- `src/topik_sim/dialogues.py` — situational conversation practice loaded from `content/dialogues/`; `/dialogue` produce-your-line flow (self-graded like `/compose`).
- `src/topik_sim/flashcards.py` / `dictation.py` / `numbers.py` / `colors.py` — shell-side practice modes (`numbers.py` renders Sino/native Korean numbers and builds the `/numbers` drill; `colors.py` holds the color lexicon — 색 noun, ㅎ-irregular modifier, Sino-Korean synonym — and builds the `/colors` drill, whose swatches render as true-color blocks in the terminal and as CSS swatches in the web UI)
- `src/topik_sim/exam_vocab.py` — mechanical vocabulary mining from packs: lemmatizes Korean text by string surgery (particles, 하다-verbs, copula, contracted past, ㄴ/ㄹ modifiers) and resolves lemmas against known glosses plus every conjugation-engine-generated form. Produces a bare word list, so vocabulary can be built for copyrighted material without the material being read; `mine-vocab`
- `src/topik_sim/media.py` — `file:` audio/image references in packs (real recordings and figures for past-paper packs), resolved under `content/private/` first; preferred over TTS on every surface
- `src/topik_sim/stats.py` / `report.py` — cross-attempt accuracy stats and Markdown study reports
- `src/topik_sim/library.py` — versioned content library with checksums
- `src/topik_sim/config.py` — `topik.config.json` workspace defaults (flags always win)
- `src/topik_sim/tts.py`, `audio_cache.py`, `prefetch.py` — providers (supertonic default; `qwen3` = Qwen3-TTS via mlx-audio on Apple Silicon, each a subprocess helper in its own venv under `tools/`), content-addressed WAV cache with Opus cold storage, background prefetch (`docs/AUDIO_DESIGN.md`)
- `src/topik_sim/ui/` — interactive shell (commands registry, renderer, prompt_toolkit frontend with plain fallback)
- `src/topik_sim/web/` — local web UI: `app.py` is a transport-free JSON API over the same core (unit-tested by calling `handle()` directly, TTS stubbed), `server.py` the stdlib HTTP bridge, `static/` the vanilla-JS single-page app; `python -m topik_sim web`
- `src/topik_sim/cli.py` — argparse surface; documented in `docs/CLI_CONTRACT.md`

Extension guide for new test formats and learning tools: `docs/FRAMEWORK.md`.

## Surface Parity (CLI ↔ Web)

Every learner-facing feature is drivable without a browser; the web UI is a thin JSON layer over the same core, so agents can experiment and debug entirely from the CLI or from Python:

- **Shell**: drive `Shell.handle_line("<line>")` from a script or test — no terminal, no prompt_toolkit needed. All state transitions go through it.
- **Web API without HTTP**: call `WebApp.handle(method, path, query, body)` directly — the server in `web/server.py` is just transport. Or curl a running `topik-sim web`.
- **Parity map** (each exists as a shell command *and* a web endpoint, sharing the same data files): exams (take/resume/drill/review/course) · homework · flashcards · grammar cards · recall · typing (incl. advanced) · numbers (incl. the learn cheat sheet) · colors (incl. the learn table) · dictation · misses/weak-items drill · compose · facts · hangul primer · lookup · hints · transcripts · slow replay · stats + practice log · reports · TTS settings · keyboard chart · doctor · setup.
- **CLI-only by design** (ops/authoring, not learner flow): `import-pack`, `validate-content`, `validate-library`, `mine-vocab`, `inspect-content`, `hide-pack`/`show-pack`, `audio` cache management (warm/prune/compress/bundle), `review-writing` (essay rubric scoring — no bundled pack ships essay questions), `grade`, `simulate`.

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
