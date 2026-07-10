# Session State (handoff checkpoint)

A durable snapshot so the project survives conversation compaction or a fresh session. Update this when the high-level state changes; it is the one file to read first.

## Where things stand

- **Project:** TOPIK exam simulator — Python CLI + interactive shell, `H:\software\TOPIK`. Core is stdlib-only; `prompt_toolkit` optional.
- **Released:** `v1.0.0` and `v1.1.0` are tagged; `__version__ = "1.1.0"`. `main` has the practice work merged (PR #1, `feature/practice-enhancements`).
- **Verify:** `$env:PYTHONPATH = "src"; python -m unittest discover -s tests` (offline, mocks TTS). Must be green before any commit.
- **Launch:** `.\topik.cmd` (anchors to the workspace); `.\setup-tts.ps1` once for Korean speech; `.\topik.cmd doctor` to diagnose.

## Feature inventory

- **Exam:** `/take` (timed sections, countdown), `/resume`, `/drill` (missed questions), `/review` (spaced repetition), grading with teaching feedback, `/stats`, `/report`.
- **Practice modes** (shell): `/flashcards`, `/grammar`, `/recall` (EN→KO word), `/dictation`, `/typing` (두벌식 trainer + `/keyboard`), `/facts` (Korea facts), `/compose` (grammar-structure sentence writing), `/course` (guided curriculum).
- **Content (six authentic-difficulty exams + practice content):** 4 authentic TOPIK I mock packs + 2 starter samples in the library; `/facts` ≈ 263 cards across 14 genres; `/compose` ≈ 65 grammar structures; `/course` = guided curricula for the 4 mock packs.

## Architecture conventions (important)

- **Overlay content lives in per-item files, read directly (no import):**
  - `content/facts/<genre>.json` (`topik-sim.facts.v1`) → `/facts`
  - `content/compose/<set>.json` (`topik-sim.compose.v1`) → `/compose`
  - `content/courses/<pack_id>.json` (`topik-sim.course.v1`) → `/course` (one file per pack; questions partition the pack; ≤12 new vocab / ≤3 new grammar per course)
  - Exam packs stay in the versioned library (`content/source/` tracked sources, `content/library/` generated/ignored).
- **Authoring workflow:** one agent owns one file (disjoint files → parallel, no merge conflicts). Agents author + self-check; the supervising session validates (loaders + `validate_*` helpers), runs the suite, and commits. Agents are often sandboxed from running Python, so they hand off and the supervisor verifies.
- Contracts: `docs/CLI_CONTRACT.md`, `docs/CONTENT_CONTRACT.md`. New shell commands need a `details` block (a test enforces it).

## Open threads / next ideas

- Releasing: confirm whether `v1.1.0` is pushed to the remote (`origin` = github.com/Haruto2017/TOPIK-Simulator-CLI). Never move a pushed tag.
- Possible next work: TOPIK II content (would also unlock grounding for the level-2 `/compose` structures); fan out more `/facts` genres, `/compose` sets, or `/course` packs (one agent per file); a local web UI reusing `ExamSession`.
- Stale background-agent notifications from an earlier crashed process may still surface; their work was redone and committed — safe to ignore.
