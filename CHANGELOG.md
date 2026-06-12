# Changelog

All notable changes to the TOPIK exam simulator are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-06-11

First stable release: the complete TOPIK I study loop — sit a mock exam, review
the feedback, drill what you missed, and watch your accuracy trend — from a
single launcher, fully offline.

### Added

- **One-click launch**: `topik.cmd` (double-click friendly) and `topik.ps1`
  start the simulator from any folder with no environment setup; all
  subcommands pass through (for example `.\topik.cmd doctor`). Installing with
  `pip install -e .` exposes the same tool as `topik-sim`, and the optional
  `shell` extra (`pip install -e .[shell]`) pulls in `prompt_toolkit` for the
  enhanced prompt.
- **Interactive shell**: a persistent prompt with a guided, numbered menu
  (just press Enter) and slash commands for everything else, with history,
  autocompletion, and a status toolbar; degrades gracefully to a plain prompt
  when `prompt_toolkit` is not installed.
- **Authentic TOPIK I mock exams**: bundled with the workspace and offered for
  import the first time the shell starts; `setup` does the same
  non-interactively and never clobbers packs you already imported.
- **Timed exams**: per-section time limits with a live countdown, plus pause
  and resume for interrupted attempts.
- **Grading with teaching feedback**: every answer is graded immediately with
  an explanation, related vocabulary, and grammar notes; writing tasks get a
  guided self-review flow.
- **Practice tools**: drills rebuilt from the questions you missed,
  spaced-repetition review, flashcards, grammar cards, vocabulary recall,
  listen-and-type dictation, and a Korean typing trainer with 두벌식 keystroke
  hints.
- **Local Korean speech**: listening questions are spoken by a local
  text-to-speech engine, with generated audio cached, prefetched in the
  background, and compressible for cold storage; voice and volume are
  adjustable live, and exams stay fully usable with no sound (transcripts are
  shown instead).
- **Progress tracking**: cross-attempt accuracy statistics and exportable
  Markdown study reports.
- **Workspace configuration**: an optional `topik.config.json` holds defaults
  such as voice, volume, and directories; command-line flags always win.
- **Self-diagnosis**: `doctor` checks Python, the shell extras, audio, the
  config file, and the content library, printing PASS/WARN/FAIL with a
  one-line remedy for each; `setup` prepares a fresh workspace in one command.
