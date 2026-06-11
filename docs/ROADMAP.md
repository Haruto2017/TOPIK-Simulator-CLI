# Roadmap

## Phase 1: Contract and CLI — done

- Content validation.
- Interactive simulation.
- Batch grading.
- Teaching feedback for correct and incorrect answers.

## Phase 2: Learner Experience — done

- Save attempt history, resume, and review.
- Korean TTS playback for passages, vocabulary, and grammar examples.
- Interactive shell with slash commands (`/say`, `/replay`, `/drill`, …).
- Drill activity over missed questions.
- Audio cache warming, pruning, and background prefetch.

## Phase 3: Content Production — in progress

- Build real question packs through the content-authoring contract.
- Add metadata for levels, skills, difficulty, and source rights.
- Add import/export helpers.

## Phase 4: Quality of Life

Shell and study flow:

- `/hint` command revealing one vocabulary item without the full answer.
- Timed mode with a countdown in the status toolbar and per-question timing stats.
- `stats` command: per-skill accuracy (listening vs reading), trends across attempts.
- Cross-attempt review queue with spaced repetition over missed questions.
- Dictation activity: hear a sentence, type it, diff-based feedback.
- Vocabulary flashcards generated from pack explanation entries.
- Export an attempt as a Markdown study report (misses, vocab, grammar to review).
- Fuzzy pack/attempt pickers and `/take` autocompletion of pack ids.
- A `topik.toml` config file for default TTS provider, volume, voice, and directories.

Content and engine:

- `multiple_select`, `ordering`, and `cloze` question types via the registry.
- Rubric-based (optionally AI-assisted) review for TOPIK II writing as a post-attempt step.
- Pack-level statistics in `inspect-content` (skill mix, difficulty spread).

Audio:

- Opus/OGG transcoding when `ffmpeg` is available (~10x smaller cache).
- Exportable per-pack audio bundles for offline devices.
- Per-voice warming so two voices can be A/B compared.

## Phase 5: Interface

- Local web UI reusing `ExamSession`, grading, and the audio cache.
- Desktop-style packaging once the web UI stabilizes.
