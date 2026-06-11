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

## Phase 4: Quality of Life — done

Shell and study flow:

- `/hint` revealing one vocabulary item per call.
- Per-question timing with a countdown toolbar against pack time limits and pace in summaries.
- `stats` command and `/stats`: per-skill accuracy, pace, trends, per-pack best/last.
- Cross-attempt spaced-repetition review queue (`review`, `/review`).
- Dictation activity with diff-based feedback (`/dictation`).
- Vocabulary flashcards from pack explanations (`/flashcards`).
- Markdown study reports (`report`, `/report`).
- Fuzzy pack suggestions and `/take` pack-id autocompletion.
- `topik.config.json` workspace config for TTS, paths, and shell defaults (JSON instead of TOML: Python 3.10 has no tomllib and the core stays stdlib-only).

Content and engine:

- `multiple_select`, `ordering`, and `cloze` question types via the registry.
- `essay` type with rubric-based manual scoring via `review-writing`.
- Pack-level statistics in `inspect-content` (skill mix, answer types, difficulty).

Audio:

- Opus transcoding via ffmpeg with transparent restore on playback (`audio compress`).
- Per-pack audio bundle export (`audio bundle`).
- Multi-voice warming for A/B comparison (`audio warm --voices`).

## Phase 5: Interface

- Local web UI reusing `ExamSession`, grading, and the audio cache.
- Desktop-style packaging once the web UI stabilizes.

## Later Ideas

- AI-assisted essay scoring suggestions feeding `review-writing`.
- Sample-rate normalization for even smaller cached audio.
- Cross-pack review sessions once attempts can span packs.
