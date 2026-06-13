# Changelog

All notable changes to the TOPIK exam simulator are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-06-13

### Added

- **Korea facts**: `/facts` (and the `topik-sim facts` command) shows an
  interesting fact about Korea — each with a Korean phrase, its translation,
  useful vocabulary, and a short language note. Filter by category, and after
  a fact a bare `/say` reads its Korean aloud. The bundled library has 50
  facts across 14 areas — history, geography, politics, literature, food,
  shopping, sightseeing, language, holidays, science, etiquette, and
  **music, film, and pop culture** (`/facts movie` also finds film cards).

### Changed

- Facts content is organized as one file per genre under `content/facts/`,
  so a genre can be edited or expanded on its own. The command reads the
  whole directory.

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
- **Pack management at scale**: pack lists and pickers group by TOPIK level
  and show each pack's difficulty label, size, and your best score; typing
  text in a picker filters it (`ii`, `authentic`, any title fragment). Packs
  can carry a `difficulty` label, and `hide-pack`/`show-pack` retire packs
  from view without breaking old attempts.
- **Workspace configuration**: an optional `topik.config.json` holds defaults
  such as voice, volume, and directories; command-line flags always win.
- **Self-diagnosis**: `doctor` checks Python, the shell extras, audio, the
  config file, and the content library, printing PASS/WARN/FAIL with a
  one-line remedy for each; `setup` prepares a fresh workspace in one command.
- **License and hardening**: MIT licensed, with a documented threat model
  (`SECURITY.md`). Pack ids/versions are validated as filesystem-safe slugs
  and imports refuse to write outside the library; audio playback paths are
  escaped against command injection.
