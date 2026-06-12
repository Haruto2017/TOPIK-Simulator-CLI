# Release 1.0 — Product Plan

## Persona and promise

**Persona:** a self-studying Korean learner preparing for TOPIK I on Windows. Not a developer. Has Python installed (or can follow one install step), has the Windows Korean IME, may or may not have a TTS runtime or speakers.

**Promise of v1.0:** one tool, one entry point, the whole study loop — sit authentic mock exams, get teaching feedback, drill what you missed, practice vocabulary/grammar/listening/typing, and watch your accuracy trend — without ever editing an environment variable.

## The study loop v1.0 must serve end to end

1. Launch → see what to do (menu).
2. Sit a timed mock exam with listening audio.
3. Review: feedback per question, study report, stats.
4. Practice: drill misses, spaced review, flashcards, grammar, recall, dictation, typing.
5. Repeat daily; resume anything interrupted.

Everything in 2–5 already ships. v1.0 closes the gaps in 1 and in resilience.

## Needs

| # | Need | Acceptance criteria |
| --- | --- | --- |
| N1 | **Zero-friction launch.** A learner must never set `PYTHONPATH` or know module syntax. | `topik.cmd` / `topik.ps1` in the repo root start the shell from any CWD (they anchor to the workspace). Arguments pass through (`topik doctor`). `pip install -e .` exposes `topik-sim` and `topik-tts` (already wired). |
| N2 | **First-run onboarding.** An empty library must not greet the learner with "No packs imported". | On shell start with an empty library and bundled sources present, offer a one-keystroke import of every pack under `content/source/`; `topik-sim setup` does the same non-interactively and idempotently (already-imported versions are skipped, not clobbered). Ends by pointing at the Enter-menu. |
| N3 | **Self-diagnosis.** "Why doesn't it work?" must be one command. | `topik-sim doctor` checks: Python version, prompt_toolkit, TTS runtime reachability, ffmpeg, config file parse, library validity, pack count, data-dir writability. Each line PASS/WARN/FAIL with a one-line remedy; exit code 1 only on FAIL. |
| N4 | **Soundless mode is fully usable.** Listening questions must be answerable with no TTS runtime, no speakers, or `/tts off`. | When a listening question produces no playable audio, the shell reveals the transcript before the answer with a notice. A full mock exam is completable end to end with TTS unavailable. |
| N5 | **Version identity.** | `topik_sim.__version__ == "1.0.0"`, `python -m topik_sim --version` prints it, `pyproject.toml` matches, `CHANGELOG.md` exists with a 1.0.0 entry. |
| N6 | **Learner documentation.** Docs written for the learner, not the contributor. | `docs/USER_GUIDE.md`: install, first session walkthrough, daily/pre-exam study routines, command cheatsheet, FAQ (no sound, garbled Hangul, Korean IME setup, where my data lives). README opens with a non-developer quickstart. |
| N7 | **Release hygiene.** | Full unittest suite green; `validate-library` clean; `docs/CLI_CONTRACT.md` covers new commands; tagged `v1.0.0`. |

Out of scope for 1.0 (already on the roadmap): web UI, AI-assisted essay scoring, cross-pack review sessions.

## Workstreams

| WS | Owner | Needs | Files (exclusive) |
| --- | --- | --- | --- |
| A | programmer agent | N2 setup + first-run, N3 doctor, N4 transcript fallback, N5 `--version`/`__version__` | `src/topik_sim/**`, `tests/**`, `docs/CLI_CONTRACT.md` |
| B | programmer agent | N1 launchers, N5 pyproject + CHANGELOG, README quickstart | `topik.cmd`, `topik.ps1`, `pyproject.toml`, `CHANGELOG.md`, `README.md` |
| C | programmer agent | N6 user guide | `docs/USER_GUIDE.md` |
| PM | supervising session | N7 integration, verification, tag | — |
