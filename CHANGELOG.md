# Changelog

All notable changes to the TOPIK exam simulator are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Stable reading style for Qwen3-TTS** (`--tts-style`, `--tts-temperature`, `/tts style|temperature`,
  a Settings field): the engine used to sample prosody afresh per sentence (temperature 0.9, no
  instruction, no seed), so pitch register and pace drifted between sentences. A default natural-
  conversational instruction, temperature 0.6, and a per-sentence text-derived seed cut the
  across-sentence median-pitch spread from sd 19.9 Hz to 13.6 Hz on a five-sentence probe and
  halved the pace spread, while keeping a human, expressive delivery (a flatter narrator style
  reaches 6.6 Hz but sounds monotone; it is one Settings edit away). Style and
  temperature join the audio-cache identity for engines that have them, so a changed style regenerates
  audio while Supertonic cache names stay valid.

- **Qwen3-TTS speech engine** (`--tts-provider qwen3`, `/tts provider qwen3`; `tools/qwen3_synth.py`,
  `setup-tts-qwen3.sh`): a second, optional engine running Alibaba's Qwen3-TTS-0.6B on Apple
  Silicon through mlx-audio in its own `.venv-qwen3`. Chosen by measurement: on this repo's
  three-sentence benchmark, its Korean transcribes back through Whisper at 0% / 5% character
  error — identical to Supertonic — with English at 0%, warm generation at RTF ≈ 0.36 and a
  5 GB peak footprint. Korean and the nine voices (`sohee` default) are declared by the model
  itself, not guessed. The helper trims the model's ~1 s of leading/trailing silence and
  implements slow replay with ffmpeg's pitch-preserving `atempo` (the model has no speed
  control yet), falling back to normal speed rather than failing. `doctor` reports the engine
  as optional: absent is a PASS, half-installed a WARN. Supertonic remains the default.
  (Tencent's AuK was evaluated first and rejected: its English is clean but it produces
  non-Korean audio for Korean input — 100–217% CER across three prompt strategies.)

- **Rounds for vocabulary drills** — `loop` on `/recall`, `/numbers`, `/colors` and a
  "Rounds" checkbox on the web (on by default for recall): whatever you miss comes
  straight back as the next round, shuffled, until every item is cleared (capped at 8).
  The first pass is what gets reported and logged, then "All clear in N rounds".
  Not offered for `/vocab`, whose spaced schedule already reschedules a miss.
- **Recall feeds spaced review** — a word you cannot produce on the first pass of a recall
  drill is recorded in the SRS deck as a lapse (due tomorrow), so it surfaces in your next
  `/vocab` session. Correct answers are not added; later rounds do not record again.
- **Stage vocabulary, textbook-style** — every study-path unit now carries the words it
  introduces (`resolve_units` attaches them from the unit-keyed wordlists). The web study
  path prints them as a footer band along the bottom of each stage card — Korean beside its
  gloss, one line, expandable to the full set — and `/path <n>` prints the same strip in the
  terminal. The sets are drillable, not just readable: 단어 Cards / 단어 Recall on each card,
  `/recall unit:<id>` and `/flashcards unit:<id>` in the shell, and a `unit` scope on
  `GET /api/deck/flashcards` plus the `recall` and `vocab` drill modes. The web pack
  picker for Vocab recall, Vocabulary review and Flashcards lists the stages in a
  "Study-path stages" group beneath the exam packs, so a stage set can be chosen from the
  practice screen rather than only from the study path.
- **Vocabulary mining without reading the text** (`mine-vocab`,
  `src/topik_sim/exam_vocab.py`): a pack's Korean text is reduced to lemmas by
  string surgery alone — particle and plural stripping, 하다-verb and copula
  normalization (공부합니다 → 공부하다, 학생입니다 → 학생), contracted-past
  undoing (갔습니다 → 가다), and ㄴ/ㄹ modifier resolution including the
  ㄹ-irregular (만든 → 만들다) — then resolved against every gloss the project
  owns, including ~12,000 forms generated from known dictionary forms by the
  conjugation engine. Stem and modifier lookups only *match* known verbs; an
  unknown stem is never invented into one. The unresolved remainder is a bare
  word list with no sentences, questions, or passages, so vocabulary can be
  built for copyrighted material without that material being read or
  reproduced. `--needs-gloss-only` emits exactly that list.
- **Private wordlist directory**: `wordlist_dirs_for()` now also reads
  `content/private/vocabulary/`, after the bundled lists so a personal list
  fills gaps without overriding a curated gloss. Personal vocabulary flows into
  meaning reveals, `/vocab` spaced review, recall, misses, and `/lookup` with no
  further wiring.

- **Color practice** (`/colors`, web "Colors · 색깔", `src/topik_sim/colors.py`):
  see a real color and name it in Korean. Sixteen colors carry their 색 noun,
  native alternates (빨강/파랑/노랑/초록/검정/하양), the modifier form used before
  a noun, and the Sino-Korean synonym. Six rotating categories — `swatch`
  (name the color shown), `word`, `modifier` (빨간 사과, from the ㅎ-irregular
  adjectives 빨갛다 → 빨간), `shade` (연한/진한), `object` (당근은 무슨 색이에요?,
  topic particle chosen by final consonant), and `sino` (녹색·백색·흑색).
  Swatches render as 24-bit color blocks in the terminal (new `ansi.swatch`)
  and as CSS swatches in the browser; terminals without color name the color in
  English so the drill stays answerable. Answers must be Hangul — Latin input is
  re-asked with a hint rather than counted wrong (new `no_latin` item flag,
  mirroring `no_digits`). `/colors learn` and `GET /api/colors/guide` show the
  full table first; results feed the practice log like every other drill.

- **Local media in packs** (`src/topik_sim/media.py`): `audio_ref`/`image_ref`
  can carry `file:` paths to real recordings and pictures. Every surface
  prefers the file over TTS — the shell and CLI play it (and print picture
  paths), the web exam room streams it via `GET /api/activity/<id>/audio` and
  renders images via the new `GET /api/activity/<id>/image` — and file audio
  stays playable with TTS disabled. Missing files fall back to transcript/TTS
  so packs stay portable. Built for officially released TOPIK past papers
  imported as personal, local-only packs under the gitignored
  `content/private/` (see docs/CONTENT_CONTRACT.md, "Local media references");
  `play_audio` now applies volume shaping only to WAVs so MP3s play unmodified.

### Fixed
- **Mined vocabulary was unreachable from the practice modes.** Wordlist words
  fed meaning reveals and `/lookup`, but the recall deck and flashcards read
  imported packs only — so choosing a pack that teaches no vocabulary in its
  notes (an imported past paper) produced an empty session, and the
  library-wide deck never saw a wordlist word at all. `library_deck` now folds
  in the wordlists (pack-taught cards still win for the same word), and
  `/recall <pack>`, `/flashcards <pack>` and the web equivalents fall back to
  the pack's mined words. `/vocab <pack>` and the web Vocabulary-review pack
  selector scope a spaced-repetition session to one exam's vocabulary, which
  also fixes mined words being unreachable in practice because they sorted to
  the tail of the gloss map behind thousands of pack-taught entries.

## [1.2.0] - 2026-07-12

### Added

- **Full book-scope coverage** (four parallel authoring/engineering passes):
  the audit against the licensed Yonsei 1-2 scope now closes at **100%
  grammar coverage on both levels** (was 89%/56%) — 34 new compose structures
  (corpus 65 → 99) give every staged pattern notes and five practice
  sentences; **25 new dialogues** (5 → 30) put a unit-aligned conversation in
  every study-path stage, from 반말 birthday invitations to reported-speech
  message relays and hospital visits; a **vocabulary wordlist layer**
  (content/vocabulary/, ~900 original words keyed to unit domains, new
  src/topik_sim/wordlists.py) lifts the taught lexicon 916 → **1,819**
  glosses, feeding /vocab spaced review, recall, misses, and lookup
  (wordlist hits attributed as wordlist:<unit>), with pack-taught glosses
  winning on conflict; and the **conjugation engine grows 16 → 35 endings**
  (22 in the drill menu) — 반말, all five quotation forms (-다고/-냐고/-라고/
  -자고/-달라고 하다), -(으)려면, -(으)ㄹ까 하다, -았/었다가, -았/었던/-던,
  -아/어 보이다/가지고, -지 말고, -더군요, -나요?, -는지/-는 대로 — all
  rule-derived, with action/descriptive gating (gloss-informed, passive-
  participle-safe) so a form the engine cannot prove is never produced.
  All content is original; nothing is reproduced from the books.

- **Staged study path**: `/path` (aliases `/study`, `/curriculum`) and a web
  "Study path" page give the whole journey a textbook's shape — a Hangul
  stage, then two levels of ten units (greetings → school & home → family →
  food → daily life → shopping → transport → phone → weather → holidays, and a
  second level from formal introductions through casual speech, reported
  speech, hospital, travel, and housing), staged after the unit progression of
  the learner-licensed Yonsei Korean 1-2 volumes in this repo. Only the
  scope-and-sequence was used; every description is original and no book text
  is reproduced. Units are data (`content/curriculum/topik1.json`) naming
  tasks, grammar scope, and vocabulary domains; `src/topik_sim/curriculum.py`
  resolves each unit at runtime to the tool's own content (course lessons by
  grammar overlap, compose structures by match keys, dialogues, drills,
  conjugation forms) and derives progress from the existing trackers, so the
  path shows ✓/◐ per stage and links straight into study.

- **Vocabulary spaced repetition**: `/vocab` (alias `/v`) and a web "Vocabulary
  review (SRS)" mode run a real Leitner schedule over every word the packs
  teach — due words resurface first, a few new ones are introduced each
  session, a correct answer pushes a word out (boxes 1→5, ~1 to ~35 days), a
  miss brings it back tomorrow. State lives in `data/attempts/vocab_review.json`
  and the Home "review" step shows the due count. This is the spacing the SLA
  research calls for, and complements the existing question-only review queue.
  New module `src/topik_sim/vocab_srs.py`.

- **Pronunciation & sound-change lessons**: `/sounds` (aliases `/pronounce`,
  `/pronunciation`) and a web "Sound changes" page teach the seven rules that
  make spoken Korean differ from its spelling — 연음, 경음화, 비음화, 유음화,
  격음화, 구개음화, ㅎ-weakening — each with worked spelled→spoken examples.
  `/sounds drill` (and the web drill) show a word and ask how it is actually
  pronounced (책상 → 책쌍), then speak the sound. Examples are curated (never
  algorithmically guessed). New module `src/topik_sim/pronunciation.py`.

- **Situational conversations**: `/dialogue` (aliases `/talk`, `/convo`) and a
  web "Conversation" mode play a real-life scene turn by turn — the partner's
  lines are shown and spoken, and on your turns you produce the Korean for a
  stated intent (exact match passes; otherwise the model is revealed and you
  self-rate, like `/compose`). Five TOPIK I scenarios ship — self-introduction,
  restaurant, shopping, directions, phone call — in the editable
  `content/dialogues/` directory. This is the communicative, production-in-
  context practice the textbook research centers; note it cannot auto-score
  *spoken* output (that needs speech recognition, out of scope for an offline
  tool) — it trains producing the right line, with model audio to shadow. New
  module `src/topik_sim/dialogues.py`.

- **Conjugation practice — textbook-broad, rule-based**: `/conjugate [pack]
  [form] [count]` (alias `/conj`) and a web "Conjugation" practice mode drill
  turning dictionary forms into **16 endings** across tense, politeness,
  connectives, and modality: present `-아/어요` and `-습니다`, past `-았/었어요`
  and `-았/었습니다`, future `-(으)ㄹ 거예요`, `-지 않아요`, `-고 싶어요`,
  `-(으)ㄹ 수 있어요`, `-(으)면`, `-(으)니까`, `-아서/어서`, `-아야/어야 해요`,
  `-(으)세요`, `-고`, `-고 있어요`, `-지만`. `src/topik_sim/conjugation.py` is
  now a class engine the way a textbook teaches: it classifies each verb
  (하다/vowel/ㄹ/regular + the ㅂ/ㄷ/ㅅ/ㅎ/르/으 irregular classes) and derives
  the 아/어 and 으 stems by rule, so it conjugates irregulars *correctly*
  (듣다→들어요/들을 거예요/들으면, 춥다→추워요/추울 거예요, 살다→살아요/사세요/삽니다,
  모르다→몰라요) rather than guessing. Ambiguous finals it cannot resolve with
  certainty are skipped, never mis-conjugated. Verified against 120+
  hand-checked forms spanning every class × ending. `/conjugate list` shows the
  menu; the web offers a form selector (`GET /api/conjugation/forms`). Course
  homework's `conjugation` and `cloze` items ride the same engine.

- **Full CLI↔web learner parity**: a surface audit closed the last gaps in
  both directions. New shell `/misses [count]` (alias `/weak`) drills the
  weak-items list exactly like the web's misses mode — both now share one
  builder in `practice_log.py`. Advanced typing reaches the web (an
  "Advanced" toggle on the typing drill). An empty library in the web offers
  one-click bundled-exam import (`POST /api/setup`, idempotent like the CLI
  `setup`). Pre-answer item audio is now offered whenever it cannot spoil:
  suppressed only when the speech is the *hidden* expected answer, allowed
  for copy-typing (the answer is on screen) and dictation. The parity map —
  including what stays CLI-only by design (content ops, authoring,
  `review-writing`) — is documented in `CLAUDE.md` for agent-driven
  debugging.

- **From-scratch student on-ramp**: walking the learner journey exposed that
  the first flashcard assumes you can already read Korean. New `/hangul`
  (aliases `/read`, `/alphabet`) teaches reading from zero — every jamo with
  its sound, block composition, the 받침 rule, worked sound-outs, and a
  reading-practice grid — mirrored in the web as a Read-Hangul page (first
  practice tile, click-a-block-to-hear-it, plus a "start here" banner for
  brand-new learners). `/lookup <text>` (aliases `/dict`, `/search`) answers
  "what was that word again?" across every pack's vocabulary and grammar, with
  sources; the web Practice page gets the same as a live search. `/numbers
  learn` prints both number systems as tables generated by the drill's own
  converters (counter short forms, common counters, which-system-when),
  available on the web numbers page. `/replay slow` (and 🐢 buttons on web
  listening and dictation) re-speaks the current audio at three-quarter speed.
  Grammar decks and homework pattern items now show the pattern-shorthand
  legend (N = noun, V = verb stem, …) so meta-notation is never unexplained.
  New modules `src/topik_sim/hangul_guide.py`, `src/topik_sim/lookup.py`.

- **Web exam hints and keyboard chart**: the exam room gains the shell's
  `/hint` — one vocabulary hint per click, resetting with each question — and
  Settings shows the 두벌식 keyboard chart (with an input-source tip), closing
  the last shell/web parity gaps.

- **Practice log and weak-items tracking**: every typed drill and dictation run
  (shell and web alike) now records to `data/attempts/practice_log.json` —
  mode, score, and which items were missed. `/stats` gains a Practice block;
  the web Progress page shows course/homework completion, practice history,
  and the weak-items list (most-missed across recent runs, dropping off once
  you stop missing them) with a one-click drill that asks weak vocabulary from
  its gloss. The web home nudges toward weak items in the daily practice step.
  New module `src/topik_sim/practice_log.py`.

- **Web UI**: `python -m topik_sim web` serves a local, offline single-page app
  (stdlib `http.server`, vanilla JS, no external assets) and opens the browser.
  Everything the shell offers is there: timed exams with listening audio, answer
  feedback with full teaching notes, resume/drill/spaced review, guided courses
  with per-lesson homework, the practice suite (flashcards, grammar cards,
  recall, typing, numbers, dictation, sentence writing, Korea facts), progress
  stats with accuracy meters and attempt history, Markdown study reports, and
  live TTS settings. Attempt files, review queue, course progress, and homework
  scores are shared with the CLI — pause in one, resume in the other. Questions
  are sent to the browser without answers or explanations (they arrive with the
  graded response), and listening transcripts stay hidden while audio plays,
  falling back to visible transcripts when TTS is off or fails. New package
  `src/topik_sim/web/`; config keys `web.host` / `web.port`.

- **Course homework**: `/homework <pack> [lesson]` (alias `/hw`) gives every
  course lesson a textbook-style assignment that validates exactly the
  vocabulary and grammar it introduced — generated from the lesson itself, no
  authored content needed. Six exercise kinds: type the Korean for a gloss,
  pick a word's meaning from options, match a grammar pattern to its
  explanation, **conjugate the verb that fills a grammar example's blank** (the
  conjugated verb is blanked at every occurrence; the prompt gives its
  dictionary form and the target ending, so the answer is a transformation the
  learner applies — never a random word copied back),
  **write a full sentence** using the lesson's pattern (pulled from the
  compose corpus, most-specific structure wins, accepted variants honored,
  punctuation-tolerant grading), and **conjugate the lesson's own verbs** with
  the ending the lesson taught — generated only for endings whose rules are
  exception-free (-습니다/-ㅂ니다 with the ㄹ-drop; the concatenatives -고
  싶어요, -지 않아요, -지만) so the tool can never teach a wrong form.
  Multiple-choice answers accept the option number or the full text. Completed
  runs are saved per lesson (best score kept); `/course` shows each lesson's
  homework score, and finishing a course lesson points at its homework. New
  modules `src/topik_sim/homework.py`, `src/topik_sim/conjugation.py`.

- **Advanced typing mode**: `/typing advanced` (aliases `adv`, `pro`) skips the
  jamo/syllable warm-up and drills only meaningful items — real vocabulary words
  plus full sentences pulled from the `/compose` lessons — shuffled together,
  each revealing its English meaning after you type it. Matching is whitespace-
  and trailing-punctuation-tolerant, so a sentence is not failed by a missing
  period or an extra space. Naming a pack scopes the whole drill to it: the
  words to the pack's vocabulary and the sentences to the pack's TOPIK level
  band (a TOPIK I pack drops the level-3 TOPIK II expression patterns), so
  choosing a pack sets both the range and the difficulty. `count` sets the
  length.

- **Korean number practice**: `/numbers` (aliases `/num`, `/number`) drills both
  number systems and the contexts that choose between them. A value is shown with
  Arabic digits and you write its Korean reading in Hangul — answers containing
  digits are rejected and the item is re-asked, so practice is letters-only;
  grading ignores spacing. The default `mix` rotates evenly through nine
  categories: `sino` and `native` cardinals, `count` (native number + counter, in
  the 한/두/세/네/스무 counter forms), `date` (with the irregular 유월/시월),
  `time` (native hour + Sino minute, accepting 반 for :30), `money`, `math` (the
  full equation with 더하기/빼기/곱하기/나누기 and the right 은/는), `phone`
  (digit-by-digit, 0 → 공), and `ordinal`. Pass one category to focus, and a
  count to set length. `/say` reads the correct form aloud. New module
  `src/topik_sim/numbers.py`.

- **Guided courses**: `/course <pack>` turns an exam pack into a textbook-style
  curriculum — a sequence of short lessons, each teaching a bounded set of new
  vocabulary (flashcards) and grammar (cards) before running the exam questions
  it covers. Courses cover the whole pack, introduce at most 12 new words and 3
  grammar points each, and track completion. The four authentic mock exams ship
  with 8-9 courses apiece, grounded in the packs' own vocabulary and grammar.
  Course definitions live in the editable `content/courses/` directory.

- **Sentence writing practice**: `/compose` (alias `/write`) teaches one
  grammar structure up front — its meaning, an example, and how it appears in
  your imported exam packs (with an authentic example pulled from them) — then
  has you write several English→Korean sentences that all use it. Exact matches
  auto-pass; otherwise the model and natural variants are revealed and you
  self-rate. `/say` reads the model aloud. Lessons live in the editable
  `content/compose/` directory, covering ~65 grammar structures across the
  core TOPIK inventory (particles, connectors, tense/negation, ability and
  obligation, requests, time relations, comparison) plus common exam
  expression patterns (-기 시작하다, -게 되다, -(으)ㄴ/는 것 같다, reported
  speech, -자마자, -기 위해서, and more). `/compose random` picks one at random.

### Changed

- **Conjugation practice defaults to mixed, interleaved endings**: `/conjugate`
  and the web Conjugation mode now give each verb a *random* ending by default
  (`mix`) — the prompt names each verb's target, so the session stays
  unambiguous — instead of drilling one fixed form. Interleaved practice beats
  blocked practice for retention, and it exercises all 16 endings in one
  session. Naming a form (`/conjugate past`, or the web selector) still focuses
  a single ending. With no seed the mix re-rolls each run.
- **Homework re-rolls each session**: a lesson's homework used to be pinned to
  one fixed set of questions (the RNG was seeded on the lesson id). It now draws
  a fresh, fair cut of the lesson's own vocabulary and grammar every run — a
  different selection of recall vs. multiple-choice words, distractors, sentence
  per pattern, and verbs to conjugate — so re-doing homework (best score kept)
  validates the lesson instead of rewarding memorization of one assignment.
  Passing an explicit seed to `build_homework` keeps it reproducible for tests.
  The composing budget also rotates across the lesson's matchable patterns
  (previously a fixed allocation order meant a third matching pattern could
  never appear — true for 14 of the 35 bundled lessons).
- **Web home is now a study loop, not a pack list**: 오늘의 학습 orders the day
  the way a teacher would — spaced review due, continue an open attempt, the
  next unfinished lesson (or its missing homework), then short practice — with
  course progress bars beneath and mock exams reframed as the weekly
  checkpoint.
- **Web exam room teaches from mistakes**: after answering, the options stay
  visible with your pick and the correct row marked (✗/✓), choice questions
  answer from the keyboard (1–9 or the option letter), and Korean passages
  render larger for comfortable reading practice.
- The `web` config section (`host`, `port`) is documented in
  `examples/topik.config.example.json`; the README quickstart covers
  macOS/Linux; `/api/state` and `/api/doctor` report the app version (shown in
  web Settings).
- **Web visual redesign**: a proper visual system — warm hanji-paper neutrals
  with a taegeuk-blue accent (red stays reserved for incorrect/status, never
  decoration), a myeongjo serif voice for Korean display moments (page-title
  Korean, flashcard fronts, the brand mark), a page-title seal dot, layered
  elevation with hover lift, gradient primary buttons and progress fills,
  sidebar icons with an active indicator, a real 3D flashcard flip, quiet
  staggered view transitions (disabled under `prefers-reduced-motion`), and a
  designed 한 favicon. Chart colors are untouched — they remain the validated
  data-viz palette.

### Fixed

- Homework "meaning" questions record the missed **Korean word** — not its
  English gloss — in the practice log and end-of-run review, so the weak-items
  list and the misses drill stay in Korean.
- Practice drills no longer offer to speak an item whose audio would give the
  answer away (recall, numbers, homework choice items); the answer's audio
  moves into the post-answer feedback ("Hear it") where it teaches. Dictation
  keeps pre-answer audio — hearing it is the task.
- The web server serializes state-changing requests, so a double-click can
  never submit the same exam answer twice.
- Conditional view fragments no longer render as literal "null" text in the
  web UI.

## [1.1.0] - 2026-06-13

### Added

- **Korea facts**: `/facts` (and the `topik-sim facts` command) shows an
  interesting fact about Korea — each with a Korean phrase, its translation,
  useful vocabulary, and a short language note. Filter by category, and after
  a fact a bare `/say` reads its Korean aloud. The bundled library has more
  than 250 facts across 14 areas — history, geography, politics, literature,
  food, shopping, sightseeing, language, holidays, science, etiquette, and
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
