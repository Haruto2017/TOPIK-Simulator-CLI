# Test Format and Learning Tool Framework

This document defines how new test formats and learning tools plug into the simulator without destabilizing the content contract or existing flows.

## Layers

| Layer | Module | Responsibility |
| --- | --- | --- |
| Content packs | `docs/CONTENT_CONTRACT.md` | What authors write: sections, questions, answers, teaching notes. |
| Question types | `src/topik_sim/question_types.py` | Validate and grade one answer format. |
| Activities | `src/topik_sim/activities.py` | Select and order questions into a learning exercise (exam, drill, …). |
| Session engine | `src/topik_sim/session.py` | Attempt lifecycle: present → submit → advance → finalize, saved after every answer. |
| Frontends | `src/topik_sim/cli.py`, `src/topik_sim/ui/` | Classic CLI flows and the interactive shell; future web UI. All drive `ExamSession`. |
| Audio plan | `src/topik_sim/tts.py`, `audio_cache.py`, `prefetch.py` | Cached, prefetched speech. See `docs/AUDIO_DESIGN.md`. |

The invariants: content packs are pure data; the session engine never knows about terminals; frontends never grade; audio is always a cache lookup first.

## Adding a Question Format

1. Register a `QuestionTypeSpec` in `question_types.py` with `validate(answer, question, path)` and `grade(question, normalized_response)`. Nothing else in the validator or grader changes.
2. If the format needs new rendering beyond prompt + options, extend `ui/render.question_card` and `cli.print_question`.
3. Document the answer shape in `docs/CONTENT_CONTRACT.md` and add an example question to a pack under `examples/content/`.
4. Add tests: contract validation accepts the new shape and rejects malformed ones; grading is correct for right/wrong/blank responses.
5. Versioning: new *optional* fields and new answer types are additive — `schema_version` stays `topik-sim.content.v1`. Changing required fields or the meaning of existing ones bumps the schema version and needs a migration note in `docs/DATA_PIPELINE.md`.

Candidate formats this design anticipates: `multiple_select`, `ordering` (sentence scramble), `cloze` (fill-in-the-blank with banks), `dictation` (graded against the spoken transcript), rubric-graded `writing`.

## Adding a Learning Activity

An activity is a strategy for building an attempt, not a new engine:

1. Write a builder that returns an attempt dict — use `create_attempt(pack, question_ids=..., activity="<name>")` like `create_drill_attempt` does. Extra metadata fields on the attempt are additive and allowed.
2. Wire a slash command in `ui/commands.py` + a `cmd_*` method on `Shell`, and (when useful standalone) a CLI subcommand.
3. Reuse `ExamSession` for the run loop. Only selection, ordering, and presentation hints should be new code.
4. Add tests that drive `Shell.handle_line` with scripted input — no terminal needed.

Shipped activities: `exam` (default), `drill` (re-practice the misses of a completed attempt). Anticipated: dictation sprints, vocabulary flashcards from explanation entries, timed mode, cross-attempt review queues (SRS).

## Grading Extensions

`QuestionTypeSpec.grade` is deterministic and offline. Rubric or AI-assisted grading (e.g. TOPIK II writing) should be introduced as a separate asynchronous review step over a saved attempt — never inline in the answer loop — so attempts stay reproducible and gradable without network access.
