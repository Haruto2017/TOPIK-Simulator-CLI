# CLI Contract

All commands are run from the repository root.

If the package is not installed, set `PYTHONPATH=src` first.

Running `python -m topik_sim` with no arguments opens the interactive shell (see `shell`).

`python -m topik_sim --version` prints the version (`topik-sim 1.0.0`, matching `topik_sim.__version__`) and exits 0.

## Configuration

Optional workspace defaults live in `topik.config.json` at the repo root (or a file pointed to by the `TOPIK_CONFIG` environment variable). CLI flags always override the config; the config overrides built-in defaults. Sections: `tts` (provider, voice, volume, speed, steps, onnx_provider, device, language, output_dir), `paths` (library, attempts), `shell` (audio, show_transcript), `web` (host, port). See `examples/topik.config.example.json`.

## `setup`

Imports every bundled exam pack under `content/source/` into the library, idempotently. The shell offers the same import on first run (see `shell`).

```powershell
python -m topik_sim setup [--library <dir>] [--source-dir <dir>]
```

Behavior:

- Each `*.json` under the source directory (sorted) is imported via the normal library import, never with replace semantics: an already-imported `pack_id@pack_version` is reported as skipped, not clobbered.
- Invalid packs are reported as failed with their validation errors; they do not abort the rest of the setup.
- Prints one line per pack (`Imported`/`Skipped`/`Failed`) and a final `Setup: N imported, N skipped, N failed` summary.
- Exit code is 1 only when every bundled pack failed; an empty source directory exits 0 with a notice.

## `doctor`

Diagnoses the environment in one command: each check prints one aligned `PASS`/`WARN`/`FAIL` line with a one-line detail or remedy, followed by a summary count.

```powershell
python -m topik_sim doctor [--library <dir>] [--data-dir <dir>]
```

Checks, in order:

- Python version (`PASS` on 3.9+, showing the running version).
- `prompt_toolkit` importable (`WARN` when missing: the plain prompt fallback is used).
- TTS runtime: the Supertonic Python runtime resolves and `tools/supertonic_synth.py` exists (`WARN` when not: exams run soundless with transcripts shown). No audio is synthesized.
- `ffmpeg` on `PATH` (`WARN` when absent: `audio compress`/restore unavailable).
- Config file parses (`PASS` when there is no config file; `FAIL` with the error when malformed).
- Library validity (`FAIL` listing the first errors; `WARN` when valid but empty, pointing at `topik-sim setup`; `PASS` with the pack count).
- Data directory writability (creates and deletes a probe file; `FAIL` when not writable).

Exit code is 1 only when at least one check is `FAIL`; warnings alone exit 0. Every check is safe on a machine with none of the optional pieces installed.

## `shell`

Interactive session styled after modern agent CLIs: a persistent prompt with history, slash-command autocompletion (when `prompt_toolkit` is installed), and a status toolbar. Plain input answers the current question; input starting with `/` is always a command and is never submitted as an answer.

```powershell
python -m topik_sim shell [--library <dir>] [--attempt-dir <dir>] [--show-transcript] [TTS options]
python -m topik_sim   # same as: shell
```

First-time navigation:

- Pressing Enter at an idle prompt (or `/menu`, alias `/m`) opens a numbered menu of functional areas — Take a test, Practice, Progress, Library & settings, While answering, Shell. Picking a number drills into that area's commands; picking again runs one. Enter goes back, then closes. Slash commands keep working at every level.
- `/help` lists commands grouped by the same categories.
- `/take`, `/flashcards`, and `/dictation` with no argument open a numbered pack picker instead of demanding a pack id. The picker shows one row per pack (latest version), grouped by TOPIK level, with the difficulty label, size, and your progress (`best 152/200 · 3 attempt(s)` or `untaken`). Typing text instead of a number narrows the list — `i`/`ii` filter by level, anything else matches ids, titles, and difficulty labels.
- `/packs [filter|all]` uses the same grouping, filters, and progress; `all` includes hidden packs.

Slash commands:

- `/take [pack] [section] [limit]`: start a test from a library ref or pack file; with no argument a pack picker opens. Pack ids autocomplete with the pack title and size shown alongside; a bare id always means the latest version, and pinned `id@version` entries appear in the menu only when several versions of that pack are imported. Typos get close-match suggestions.
- `/resume [n|path]`: resume an in-progress attempt. With no argument and several candidates, an interactive numbered picker opens (type the number, Enter cancels); a single candidate resumes directly. Tab after `/resume ` completes attempt numbers with status and progress.
- `/drill [n|path]`: build and run a drill over the questions missed in a completed attempt. Same picker and completion behavior as `/resume`, over completed attempts.
- `/path [unit]` (aliases `/study`, `/curriculum`): the staged study path — a textbook-style scope and sequence loaded from `content/curriculum/*.json` (a Hangul stage, then two levels of ten units modeled on the unit progression of a university beginner curriculum; all text original). Each unit names its communicative tasks, grammar scope, and vocabulary domains; at runtime it is resolved against installed content — course lessons by grammar overlap, compose structures by their match keys, dialogues and drills by name, conjugation forms via the ending matcher — and progress derives from course/homework/practice trackers (✓ done needs all linked lessons and homework; ◐ otherwise-started). `/path <n|id>` prints one stage with the exact commands that teach it. Web: a Study Path page backed by `GET /api/path`.
- `/course [pack]`: study a pack as a guided course. Bare `/course` lists the packs that have courses; `/course <pack>` lists that pack's courses (finished ones ticked, with each lesson's best homework score when one is saved). A course teaches a bounded set of new vocabulary (flashcards) then new grammar (cards), then runs the exam questions it covers — advancing on Enter between the three steps. Completion is saved; `/pause` leaves the course (finished steps kept); finishing suggests the lesson's homework. Courses live in `content/courses/<pack_id>.json`.
- `/homework [pack] [lesson]` (alias `/hw`): textbook-style homework validating exactly what a course lesson taught, auto-generated from the lesson itself (no authored content). Six exercise kinds: type the Korean for an English gloss (`recall`), pick the meaning of a Korean word from numbered options (`meaning`), pick the grammar pattern matching an explanation (`pattern`), conjugate the verb that fills a grammar example's blank (`cloze` — the conjugated verb is blanked out at every occurrence and the prompt gives its dictionary form plus the target ending, e.g. "conjugate 있다 (to have) to -아/어요: 우산이 ____?", so the answer is always a transformation the learner applies, never a word copied back; generated only when the example actually contains a conjugated lesson verb), write a full English sentence in Korean (`compose` — sentences come from the compose corpus for the lesson's own patterns, matched by despaced keys with the most specific structure winning, accepted variants honored, graded whitespace/trailing-punctuation tolerant), and conjugate the lesson's own verbs with the ending the lesson taught (`conjugation` — via the conjugation engine in `src/topik_sim/conjugation.py`, which classifies each verb and applies per-class rules, so it produces the right form for every irregular class rather than guessing; a verb it cannot resolve with certainty is skipped, never mis-conjugated). The last two kinds appear only when applicable — a matching corpus structure, or a supported ending plus conjugatable lesson verbs. Multiple-choice answers accept the option number or its full text; distractors are drawn from the lesson first, topped up from the pack. Each run re-rolls a fresh assignment — a different fair cut of the lesson's own vocabulary and grammar (which words become recall vs. multiple-choice, which distractors, which sentence per pattern, which verbs are conjugated) — so re-doing homework validates the lesson rather than one memorized set; `build_homework(..., seed=<n>)` makes it reproducible for tests. A completed run is saved to `data/attempts/homework_progress.json` (last and best score, run count); `/pause` stops without recording. Bare `/homework` opens a pack picker (packs with courses only); `/homework <pack>` lists lessons with their homework status; `/homework <pack> <n>` starts lesson n's assignment directly.
- `/review [pack]`: spaced-repetition session over due previously-missed questions (see `review`).
- `/flashcards <pack>` (alias `/cards`): vocabulary card drill built from the pack's teaching notes; Enter flips, y/n grades.
- `/dictation <pack> [limit]`: hear listening transcripts and type them; diff-based feedback with accuracy percentages.
- `/grammar [pack] [count]` (alias `/gram`): grammar pattern cards built from teaching explanations — front shows the pattern, the flip shows its explanation and an example sentence (`/say` speaks it). Scoped to one pack, or to every imported pack when bare (default 20 cards; `count` overrides).
- `/compose [structure]` (alias `/write`): grammar-grounded sentence writing. Bare `/compose` lists the grammar structures to pick from (type a number, or `r` for a random one); passing a number, id, substring, or `random`/`r` starts a structure directly. The chosen structure is taught up front — its meaning, an example, and how often it appears in your imported packs (with an authentic example pulled from them) — then you write several English→Korean sentences that all use it. An exact match (whitespace/trailing-punctuation tolerant, against any accepted answer) auto-passes; otherwise the model and variants are revealed and you self-rate `y`/`n`. `/say` reads the model aloud; `/pause` stops with a summary. Lessons come from the `content/compose/` directory.
- `/recall [pack] [count]` (alias `/translate`): active vocabulary production — the English gloss is shown and the Korean must be typed. Any Korean word taught with that gloss counts as correct; a miss reveals the answer with its 두벌식 keys. Pack-scoped or library-wide when bare (default 10 words).
- `/typing [advanced] [pack] [count]`: Korean keyboard trainer ramping jamo → syllables → real words. The word stage uses the given pack's vocabulary, or the union of every imported pack's vocabulary when no pack is named; random syllables are only the empty-library fallback. Words drawn from a real pack reveal their meaning (the vocabulary gloss) after you answer, whether right or wrong; invented jamo, syllables, and fallback words have no meaning to show. A miss reveals the 두벌식 keystrokes. The leading keyword `advanced` (aliases `adv`, `pro`) switches to advanced mode: it skips the jamo/syllable warm-up and drills only meaningful items — real vocabulary words plus full sentences drawn from the `/compose` lessons — shuffled together, each revealing its English meaning after you type it. Matching there is whitespace- and trailing-punctuation-tolerant, so a sentence is not failed by a missing period or an extra space. Naming a pack scopes the whole drill to that pack: the words to its vocabulary (as above) and the sentences to its TOPIK level band — a TOPIK I pack admits only level-1/2 compose lessons, dropping the level-3 TOPIK II expression patterns so difficulty tracks the pack. Without a pack, sentences span every level. With no words or sentences available, advanced mode reports and stays idle instead of falling back to random syllables.
- `/vocab [count]` (alias `/v`): spaced-repetition vocabulary review over every word the imported packs teach. A Leitner schedule (`data/attempts/vocab_review.json`) resurfaces due words first and introduces a few new ones per session; a correct answer promotes the word a box (boxes 1→5, intervals ~1/3/7/16/35 days), a miss resets it to box 1 (due tomorrow). Recall-style: the English gloss is shown, the Korean is typed. `count` sets session size (default 15). Distinct from `/review`, which schedules missed *exam questions*.
- `/sounds [drill] [rule] [count]` (aliases `/pronounce`, `/pronunciation`): Korean sound-change reference and drill. Bare `/sounds` lists the seven rules (연음, 경음화, 비음화, 유음화, 격음화, 구개음화, ㅎ-weakening) with curated spelled→spoken examples. `/sounds drill [rule_id] [count]` runs a drill: a word is shown and the learner types how it is actually pronounced (책상 → 책쌍), then `/say` speaks the sound; a rule id (e.g. `gyeongeum`) focuses it. Examples are curated, never computed.
- `/dialogue [id]` (aliases `/talk`, `/convo`): situational conversation practice from `content/dialogues/*.json`. The scene plays turn by turn — partner lines are shown and spoken; on the learner's turns they type the Korean for a stated English intent, exact-match auto-passes (whitespace/trailing-punctuation tolerant against accepted variants), otherwise the model line is revealed and the learner self-rates `y`/`n` (the `/compose` model, applied to a dialogue). Bare `/dialogue` lists scenarios; a completed run logs to the practice log as mode `dialogue`. Cannot auto-score spoken audio (no ASR) — it trains producing the correct line, with model audio to shadow.
- `/conjugate [pack] [form] [count]` (alias `/conj`): conjugation practice. Shows a dictionary-form verb and you type its conjugation. `form` defaults to `mix` — every ending interleaved, a different one per verb (the prompt names each verb's target ending, so a mixed session is unambiguous), which is more effective study than blocking on one form. Name a form to focus a session: `polite` (-아/어요), `formal` (-습니다/-ㅂ니다), `past`, `past-formal`, `future`, `negation`, `want`, `can`, `if`, `because`, `so`, `must`, `honorific` (`/conjugate list` prints them). The web offers the same, with "Mixed — random endings" the default in the form selector. Verbs come from a named pack or the whole library. Only verbs whose conjugation is certain are asked: the regular algorithm (vowel harmony, vowel contractions, safe consonant finals, 하다→해요) runs on provably-safe stems, and every ㄷ/ㅂ/ㅅ/ㅎ-final or ㅡ-vowel verb (the irregular classes) is resolved from a curated table in `src/topik_sim/conjugation.py` or skipped — the tool never guesses a form. Web: a "Conjugation" practice mode with a speech-level selector.
- `/hangul` (aliases `/read`, `/alphabet`): the from-zero reading on-ramp — every consonant and vowel with its name and sound, how jamo compose into syllable blocks, the 받침 (batchim) rule with carry-over, worked sound-outs (한 → han, 학생 → hak-saeng, 안녕하세요), and a consonant×vowel reading-practice grid built by the real composer. Romanization appears only here, labeled as training wheels. Static reference; no state change.
- `/misses [count]` (alias `/weak`): a typed drill rebuilt from your most-missed practice items (the same weak list the web's `misses` mode uses, via a shared builder). Vocabulary the library knows is asked from its English gloss; anything else is retyped correctly. Default 10 items; completing the run logs to the practice log like any drill, so cleared items age off the weak list.
- `/lookup <text>` (aliases `/dict`, `/search`): searches every imported pack's taught vocabulary (Korean, English, note) and grammar patterns (pattern, explanation, example) by case-insensitive substring, deduplicated, each hit attributed to its pack. Works in any state, including mid-question. Blank query prints usage; no match prints a clear miss message.
- `/numbers [category] [count]` (aliases `/num`, `/number`): Korean number practice. `learn` (also `guide`, `table`) prints the cheat sheet instead of drilling: both systems as tables generated by the same converters the grader uses, the counter short forms (한/두/세/네/스무), common counters, and a which-system-when guide. The prompt shows a value with Arabic digits and you write its Korean reading in Hangul — answers containing digits are rejected with a reminder and the item is re-asked (no miss recorded), enforcing letters-only. Grading is whitespace-insensitive. `category` defaults to `mix`, which rotates evenly through all of: `sino` (Sino-Korean cardinals), `native` (native cardinals 1–99), `count` (native number + a shown counter such as 개/명/살, in counter form 한/두/세/네/스무), `date` (Sino, with the irregular 유월/시월), `time` (native hour + Sino minute, accepting 반 for :30), `money` (Sino + 원), `math` (read the full equation with 더하기/빼기/곱하기/나누기 and the correct 은/는), `phone` (digit-by-digit, 0 → 공), and `ordinal` (첫 번째, 두 번째 …). `count` sets the number of items (default 10). `/say` reads the correct form aloud; `/pause` stops with a summary.
- Vocabulary practice resolves a pack's words from two places: what the pack teaches in its explanation notes, and any wordlist entry recorded as appearing in that pack (`packs: [...]`, written by `mine-vocab`). A pack that teaches no vocabulary of its own — an imported past paper, for instance — is therefore still fully practisable: `/recall <pack>`, `/flashcards <pack>`, and `/vocab <pack>` all fall back to its mined wordlist, and the library-wide deck (no pack named) now includes wordlist words alongside pack-taught ones. Pack-taught cards always win over a wordlist entry for the same word.
- `mine-vocab <pack.json> [pack.json ...] [--needs-gloss-only] [--output FILE]`: list the vocabulary a pack uses **without reading its text**. Korean tokens are reduced to lemmas by string surgery alone (particle and plural stripping, 하다-verb and copula normalization, contracted-past undoing, and ㄴ/ㄹ modifier resolution), then matched against every gloss the project already owns — pack teaching notes, curriculum wordlists, and every form the conjugation engine can generate from a known dictionary form. Output is one lemma per line (`word<TAB>count<TAB>NEEDS GLOSS`) with a coverage summary on stderr; `--needs-gloss-only` prints just the unglossed lemmas, which is a **bare word list carrying no sentences, questions, or passages** — safe to hand to a glosser when the source material is copyrighted. Modifier and stem lookups only ever *match* known dictionary forms; an unknown stem is never invented into a verb.
- **Rounds** (`loop`, also `rounds`/`until`/`clear`) on `/recall`, `/numbers`, and `/colors`, and the "Rounds" checkbox on the web setup for recall, typing, numbers, colors, and conjugation: whatever you miss comes straight back as the next round, shuffled, until every item is cleared (capped at 8 rounds; `/pause` ends it early). The session reports and logs the **first pass** — what you actually knew — and then "All clear in N rounds". Not offered for `/vocab`, whose spaced schedule already reschedules a miss.
- **Recall misses are scheduled.** A word you cannot produce on the first pass of a recall drill is recorded in the vocabulary SRS deck as a lapse (box 1, due tomorrow), so it surfaces in your next `/vocab` session; correct answers are not added, and later rounds of the same session do not record again.
- Study-path stages carry their own vocabulary. `/path <n>` prints the stage's words as a footer strip (Korean + gloss pairs, the way a textbook prints them under the page), and `/recall unit:<id>` and `/flashcards unit:<id>` drill exactly that stage's set. The same sets are served to the web UI on each study-path card as a vocabulary band with 단어 Cards / 단어 Recall buttons (`GET /api/deck/flashcards?unit=<id>`, and `unit` on `POST /api/drill/start` for the `recall` and `vocab` modes).
- **Speech engines.** `--tts-provider` (and `/tts provider <p>`) selects `supertonic` (default; Windows/macOS/Linux,
  set up by `setup-tts.ps1`) or `qwen3` (Apple Silicon only, set up by `setup-tts-qwen3.sh`, which builds
  `.venv-qwen3` with mlx-audio on Python ≥ 3.11). Both run as subprocess helpers in their own venv
  (`tools/supertonic_synth.py`, `tools/qwen3_synth.py`) so the core stays stdlib-only. `--tts-voice` /
  `/tts voice` takes `F1`/`F2`/`M1` for supertonic and `sohee` (default), `serena`, `vivian`, `ryan`,
  `aiden`, `eric`, `dylan`, `ono_anna`, `uncle_fu` for qwen3; a voice unknown to qwen3 falls back to `sohee`
  with a note. The audio cache key includes the provider, so switching engines never serves the other
  engine's waveform. Qwen3 output is 24 kHz mono with leading/trailing silence trimmed; slow replay is
  rendered by ffmpeg `atempo` (normal speed if ffmpeg is absent). Runtime resolution order for qwen3:
  `--tts-python`, `TOPIK_QWEN3_PYTHON`, `.venv-qwen3/bin/python`; the model id can be overridden with
  `TOPIK_QWEN3_MODEL`. `doctor` lists "Qwen3-TTS (optional)": not installed is a PASS.
- **Reading style (prosody).** Engines that take a style instruction (qwen3) read every sentence in a fixed
  tone; without one the model samples a fresh pitch register and pace per sentence, which learners hear as
  the narrator's mood changing mid-exam. `--tts-style <text>` / `tts.style` / `/tts style <text>` sets the
  instruction (the web Settings page has a field; `default`/empty restores the built-in natural conversational
  style), `--tts-temperature <x>` / `/tts temperature <x>` sets sampling temperature (default 0.6; lower =
  steadier, valid 0–2), and each sentence is rendered with a seed derived from its text, so a sentence always
  sounds the same. Style and temperature are part of the audio cache identity for such engines only, so a
  changed style regenerates audio while Supertonic's cache names are untouched. Measured on a five-sentence
  spread: median-pitch spread fell from sd 19.9 Hz (unconstrained) to 13.6 Hz with the default natural style,
  with pace spread halved; a flat "calm narrator, no emotional emphasis" style reaches 6.6 Hz at the cost of
  a monotone delivery. Pace is better adjusted with `--tts-speed` (a pitch-preserving tempo shift) than with wording.
- `/colors [category] [count]` (aliases `/color`, `/colour`, `/colours`): Korean color practice. `learn` (also `guide`, `table`, `chart`) prints the reference table instead of drilling: every color as a terminal swatch with its 색 noun, alternate native noun (빨강/파랑/노랑/초록/검정/하양), the modifier form used before a noun, and the Sino-Korean synonym, followed by the five ㅎ-irregular adjectives (빨갛다 → 빨간) and a how-to-use guide. The drill shows a true-color swatch and you type the Korean name; answers containing Latin letters are rejected with a Hangul reminder and the item is re-asked (no miss recorded). Grading is whitespace-insensitive and accepts every listed form (빨강 or 빨간색). `category` defaults to `mix`, which rotates through: `swatch` (name the color shown), `word` (English gloss → Korean), `modifier` (빨간 사과 — the ㅎ-irregular form before a noun), `shade` (연한/진한 + color), `object` (당근은 무슨 색이에요?, with the topic particle chosen by final consonant), and `sino` (녹색·백색·흑색). `count` sets the number of items (default 10). On terminals without color support the swatch item names the color in English instead, so the drill stays answerable. `/say` reads the correct form aloud; `/pause` stops with a summary.
- `/facts [category|list]` (aliases `/fact`, `/culture`): show an interesting fact about Korea — history, geography, food, music, film, pop culture, and more — with a Korean phrase, its translation, vocabulary, and a short language note. No argument picks a random fact (not repeating until the pool is exhausted); a category or any text filters (`/facts movie` finds film cards); `list` shows the categories. After a fact, a bare `/say` reads its Korean aloud. Facts come from the `content/facts/` directory (one file per genre).
- `/keyboard [on|off|pin|unpin]` (alias `/kb`): print the 두벌식 layout chart. `on` enables keyboard mode: a compact chart is pinned to the bottom toolbar — hovering above the input line, never scrolled away — and keystroke hints (`Keys: skf·Tl`, uppercase = Shift) render consistently in dictation feedback, flashcard backs, and `/typing` misses. `pin`/`unpin` control just the docked chart. The hovering chart needs the prompt_toolkit frontend; the plain fallback prints the chart inline only. Defaults from `shell.keyboard_hints` / `shell.keyboard_pinned` in the config.
- `/attempts`, `/packs`: list saved attempts / imported packs.
- `/say <text>` (alias `/speak`): pronounce any sentence aloud without affecting the current answer. With no text during flashcards, speaks the current card.
- `/hint`: reveal one vocabulary item for the current question per call.
- `/replay [slow]` (alias `/r`): replay the current question audio. `slow` re-synthesizes it at three-quarter speed (cached separately by speed) — works on the active listening question and the current dictation sentence.
- `/transcript` (alias `/t`): reveal the active listening transcript.
- `/skip`: submit a blank answer for the current question.
- `/pause`: save and leave the current test (or stop flashcards/dictation early).
- `/status`: progress, running score, and TTS settings.
- `/stats`: per-skill accuracy and trends across completed attempts, followed by a Practice block — run count, overall practice accuracy, and the current weak items (the most-missed items across recent practice runs).
- Practice runs from the typed drills (typing, numbers, recall, homework) and dictation — in both the shell and the web UI — are logged to `data/attempts/practice_log.json`: mode, label, score, missed items, and timestamp, capped at the 200 most recent runs. Aggregating the misses across recent runs yields the learner's weak list; an item drops off once runs stop missing it. Stopping a drill early still logs the items that were completed.
- `/report [n|path]`: write a Markdown study report for a completed attempt (interactive picker like `/resume`).
- `/tts [on|off|volume <x>|speed <x>|provider <p>|voice <v>]`: change speech settings mid-session.
- `/help`, `/quit`.

Behavior:

- First run: when the library has zero packs and bundled sources exist under `content/source/`, the shell asks once — `No exams are imported yet. Import N bundled exam pack(s) now? [Y/n]`. Enter or `y` imports them (same as `setup`) and points at the Enter-menu; `n` skips with a pointer to `topik-sim setup`. The prompt never appears once packs are imported.
- Attempts are saved after every answer, exactly like `take`; quitting or crashing never loses progress.
- Listening questions auto-play audio and hide transcripts until after the answer.
- When a listening question produces no playable audio (`/tts off`, TTS runtime unavailable, or synthesis failure), the shell prints `(audio unavailable — transcript shown)` and reveals the transcript before the answer, so listening sections stay fully answerable soundless. The post-answer transcript reveal still happens whenever the transcript was not already shown.
- The next question's audio is prefetched on a background thread while the learner answers (see `docs/AUDIO_DESIGN.md`).
- Full-pack attempts are timed against the sections' `time_limit_minutes`: the toolbar counts down and summaries report pace.
- Completed attempts feed the spaced-repetition queue; the shell reports how many items are due.
- Falls back to a plain `input()` prompt when `prompt_toolkit` is unavailable.

## `web`

```
python -m topik_sim web [--host HOST] [--port PORT] [--no-browser] [--library DIR] [--attempt-dir DIR] [--show-transcript] [tts flags]
```

Serves a local web UI over the same core the shell uses and opens the browser (suppress with `--no-browser`). Binds `127.0.0.1:8765` by default; `web.host` / `web.port` in `topik.config.json` change the default. The server is stdlib-only (`http.server`), fully offline, and single-user: no accounts, no external requests.

Feature parity: taking/resuming/drilling/reviewing attempts (same attempt files — a test paused in the browser resumes in the shell and vice versa), guided courses with per-lesson homework, the practice suite (flashcards, grammar cards, vocab recall, typing, numbers, conjugation, dictation, sentence writing, facts), progress stats with attempt history and Markdown study reports, and TTS settings applied live.

Contract details, mirroring the shell:

- Question payloads sent to the browser never contain the answer or the explanation; both arrive only in the response to a submitted answer. Listening questions withhold the transcript while audio is available; a transcript endpoint reveals it on request (the `/transcript` command equivalent), and when TTS is off or synthesis fails the transcript is shown up front so listening stays answerable.
- Exam answers run through the same `ExamSession` state machine: attempts save after every answer, finalizing records the spaced-review queue, and course-scoped runs mark the course done.
- Typed practice grades server-side with the shell's rules (NFC normalization, whitespace-insensitive comparison, digit rejection for number items re-asks without recording a miss, option numbers accepted for choice items, dictation by diff accuracy). Completed homework runs record to `homework_progress.json`; stopping early records nothing.
- Listening audio is synthesized on demand through the same content-addressed cache; the browser fetches WAV bytes per part. Audio endpoints return 503 when TTS is unavailable and the UI falls back to transcripts.
- The home page is a study loop in teacher order — 복습 review due → continue an open attempt → the next unfinished lesson (or its missing homework) → short practice — with mock exams presented as the weekly checkpoint below. Choice questions answer from the keyboard (1–9 or the option letter) and, after answering, the options stay on screen with the picked and correct rows marked (the graded response includes `correct_option_id`).
- The Progress page aggregates the whole local ledger: exam stats, course/homework completion per pack, the practice-run history, and the weak-items list with a one-click `misses` drill (weak vocabulary is asked from its gloss; anything else is retyped correctly).
- Full learner-surface parity with the shell: every practice mode including advanced typing (an `advanced` flag on the typing drill) and the weak-items `misses` drill exists on both surfaces via shared builders, and an empty library offers one-click bundled-exam import (`POST /api/setup`, the `setup` command's equivalent). Pre-answer item audio is offered whenever it cannot spoil: suppressed when the speech is the hidden expected answer, allowed when the answer is already visible in the prompt (copy-typing) or hearing it is the task (dictation). CLI-only by design: content ops and authoring (`import-pack`, `validate-*`, `inspect-content`, `hide-pack`, `audio` cache management, `review-writing`, `grade`).
- Student on-ramp and digestion aids, mirroring the shell: a Read-Hangul page (`GET /api/hangul`, with a click-to-hear syllable grid) surfaced first in Practice and as a banner for brand-new learners on Home; a lookup search on the Practice page (`GET /api/lookup?q=`); the numbers cheat sheet on the numbers config page (`GET /api/numbers/guide`); the color reference table on the colors config page (`GET /api/colors/guide`); 🐢 slow replay on exam listening and dictation (`&slow=1` on audio endpoints, three-quarter speed, cached separately); and the grammar-pattern shorthand legend on grammar decks and homework pattern items.

## `drill`

Non-interactive-shell variant of `/drill`: re-practice the questions missed in a completed attempt.

```powershell
python -m topik_sim drill data/attempts/<attempt_id>.json [--library <dir>] [--attempt-dir <dir>] [TTS options]
```

Behavior:

- Requires a completed attempt; fails with guidance otherwise.
- Creates a new attempt with `"activity": "drill"` restricted to the missed question ids.
- Grades and saves like `take`.

## `review`

Spaced-repetition review across attempts. Misses enter a Leitner queue (box 1, due immediately); correct reviews promote with growing intervals (1/2/4/7/15 days); a top-box success retires the item. The queue lives at `<attempt_dir>/review_queue.json`.

```powershell
python -m topik_sim review                # list due counts per pack
python -m topik_sim review <pack_id> [--limit <n>] [--attempt-dir <dir>] [--library <dir>] [TTS options]
```

## `review-writing`

Scores essay answers in a completed attempt against their rubric (see the essay answer type in `docs/CONTENT_CONTRACT.md`). Prompts for each criterion, recomputes the attempt score, and saves in place. Half marks or better counts as correct.

```powershell
python -m topik_sim review-writing data/attempts/<attempt_id>.json [--library <dir>]
```

## `stats`

Per-skill accuracy, average pace, recent attempt trend, and per-pack best/last scores across completed attempts.

```powershell
python -m topik_sim stats [--attempt-dir <dir>] [--library <dir>]
```

## `facts`

Print an interesting fact about Korea with a Korean phrase, translation, vocabulary, and a learning note. Content lives in the `content/facts/` directory, one file per genre (extend it freely — see `docs/CONTENT_CONTRACT.md`).

```powershell
python -m topik_sim facts [category] [--list] [--facts-path <dir-or-file>]
```

- No category: a random fact. `category`: filter by category or any text. `--list`: show categories with counts. `--facts-path`: a facts directory or a single JSON file (defaults to `content/facts`).

## `report`

Markdown study report for a completed attempt: misses with correct answers, vocabulary, grammar, and common mistakes to review.

```powershell
python -m topik_sim report data/attempts/<attempt_id>.json [--output report.md] [--library <dir>]
```

## `audio`

Audio cache management. See `docs/AUDIO_DESIGN.md` for the design.

```powershell
python -m topik_sim audio stats [--audio-dir <dir>]
python -m topik_sim audio prune [--max-mb <n>] [--older-than-days <n>] [--dry-run] [--audio-dir <dir>]
python -m topik_sim audio warm <pack_ref> [--all-questions] [--teaching] [--voices F1,M1] [--library <dir>] [TTS options]
python -m topik_sim audio compress [--older-than-days <n>] [--bitrate 24k] [--audio-dir <dir>]
python -m topik_sim audio bundle <pack_ref> [--output <zip>] [--all-questions] [--teaching] [TTS options]
```

Behavior:

- `stats`: file count (wav/opus split), total size, least-recently-used timestamp.
- `prune`: deletes least-recently-used entries (wav and opus) until the cache satisfies the constraints; requires at least one of `--max-mb` / `--older-than-days`.
- `warm`: pre-generates listening audio for a pack (all passages with `--all-questions`, teaching audio with `--teaching`, several voice presets with `--voices`).
- `compress`: transcodes cold WAVs to Opus via ffmpeg; playback restores entries transparently on use.
- `bundle`: warms a pack and exports its audio plus a text→file manifest as one zip (default under `exports/`).
- Volume is applied at playback time and does not multiply cached files.

## `validate-content`

Validates a content pack.

```powershell
python -m topik_sim validate-content <pack.json>
```

Exit behavior:

- `0`: pack is valid.
- Non-zero: pack is invalid; errors are printed.

## `inspect-content`

Prints pack metadata and section/question counts.

```powershell
python -m topik_sim inspect-content <pack.json>
```

## `simulate`

Runs an interactive exam simulation in the terminal.

```powershell
python -m topik_sim simulate <pack.json> [--section <section_id>] [--limit <n>] [--show-teaching]
```

Behavior:

- Presents questions in pack order.
- Prompts for an answer.
- Grades each answer.
- Prints a final score.
- Prints teaching feedback after every answer.
- Pauses after feedback; press Enter to move on.
- `--show-teaching` is kept for compatibility; feedback is always shown.

## `take`

Runs an interactive test and saves the attempt after each answer.

```powershell
python -m topik_sim take <pack.json-or-pack_ref> [--library <library_dir>] [--attempt-dir <attempt_dir>] [--section <section_id>] [--limit <n>] [--speak-question] [--speak-teaching]
```

Pack references:

- A direct JSON path, such as `examples/content/topik_i_mini_pack.json`.
- A library pack ID, such as `topik-i-mini-pack`.
- A pinned library pack ID and version, such as `topik-i-mini-pack@0.1.0`.

Default runtime locations:

- Library: `content/library`
- Attempts: `data/attempts`

TTS behavior:

- Listening questions automatically generate and play Korean audio from transcript-backed `passage` text during `take`.
- Listening transcripts are hidden by default during `take`.
- Listening transcripts are printed after the learner answers.
- At the answer prompt, enter `/replay`, `/r`, or `replay` to play the current question audio again.
- After feedback, press Enter for the next question or enter `/replay`, `/r`, or `replay` to hear the just-answered question audio again.
- `--show-transcript`: show listening transcripts for content debugging.
- `--no-listening-audio`: disable automatic listening audio.
- `--speak-question`: generate Korean audio for non-listening question passages too.
- `--speak-teaching`: generate Korean audio for vocabulary and grammar examples in feedback.
- `--tts-play`: play generated audio immediately.
- `--tts-provider supertonic`: default provider; uses the `.venv-tts` environment created by `setup-tts.ps1` (see `docs/TTS_SETUP.md` for the full runtime search order).
- `--tts-provider melo --tts-device cuda:0`: run MeloTTS on the first CUDA GPU.
- `--tts-volume <gain>`: set generated WAV volume, where `1.0` is unchanged.
- `--tts-speaker-id <id-or-name>`: choose a provider speaker or voice preset when supported.
- `--tts-onnx-provider dml`: use Supertonic with DirectML on Windows.
- `--tts-steps <n>`: set Supertonic synthesis steps.
- `--tts-python <python.exe>`: choose the Python runtime used for subprocess-based TTS.
- Generated audio is cached under `data/audio_cache` by default.

With speech set up via `setup-tts.ps1`, the default provider works with no extra flags:

```powershell
$env:PYTHONPATH = "src"
python -m topik_sim take topik-i-authentic-mock-01 --tts-provider supertonic
```

To hear teaching notes read aloud after answers:

```powershell
python -m topik_sim take topik-i-level-1-full-sample@0.1.0 --speak-teaching --tts-play
```

To keep using older scripts that pass `--show-teaching`:

```powershell
python -m topik_sim take topik-i-level-1-full-sample@0.1.0 --show-teaching --speak-teaching --tts-play
```

To make listening audio quieter or louder:

```powershell
python -m topik_sim take topik-i-level-1-full-sample@0.1.0 --tts-volume 0.8
```

## `resume-attempt`

Loads a saved in-progress attempt and continues from the first unanswered question. If no attempt path is provided, it lists recent attempts and asks which one to load.

```powershell
python -m topik_sim resume-attempt data/attempts/<attempt_id>.json [--library <library_dir>] [--speak-question] [--speak-teaching]
python -m topik_sim resume-attempt [--attempt-dir <attempt_dir>] [--recent <n>]
```

Behavior:

- When no path is passed, scans recent attempt JSON files from `data/attempts`.
- Loads the pack from the attempt's saved `pack_id@pack_version`.
- Prints progress as `<answered>/<total> answered`.
- Skips already answered questions.
- Saves back to the same attempt JSON file after each new answer.
- Prints teaching feedback after every answer.
- Prints listening transcripts after the learner answers.
- Pauses after feedback; press Enter for the next question or enter `/replay`, `/r`, or `replay` to hear the just-answered question audio again.
- Completes and grades the attempt after the last unanswered question.

## `list-attempts`

Lists recent saved attempts without resuming them.

```powershell
python -m topik_sim list-attempts [--attempt-dir <attempt_dir>] [--limit <n>]
```

Each row includes status, answered count, pack reference, update time, attempt ID, and file path.

## `review-attempt`

Prints progress, score, and item-level feedback from a saved attempt.

```powershell
python -m topik_sim review-attempt data/attempts/<attempt_id>.json
```

## `grade`

Grades an answer file without interaction.

```powershell
python -m topik_sim grade <pack.json> <answers.json>
```

Accepted answer file shapes:

```json
{
  "answers": [
    { "question_id": "r-001", "response": "B" }
  ]
}
```

## `import-pack`

Validates and imports a content pack into the versioned library.

```powershell
python -m topik_sim import-pack <pack.json> [--library <library_dir>] [--replace]
```

Behavior:

- Copies the source pack to `packs/<pack_id>/<pack_version>.json`.
- Records metadata in `manifest.json`.
- Records a SHA-256 checksum for integrity checks.
- Rejects duplicate `pack_id@pack_version` imports unless `--replace` is used.

## `list-packs`

Lists packs currently imported into the content library, grouped by TOPIK level, one line per imported version, with the difficulty label when the pack carries one.

```powershell
python -m topik_sim list-packs [--library <library_dir>] [--all]
```

Hidden packs are omitted unless `--all` is passed (then marked `[hidden]`); a footer reports how many are hidden.

## `hide-pack` / `show-pack`

Retire a pack from pickers, completion, library-wide practice pools, and default listings without deleting it. Every imported version of the pack id is affected. Hidden packs still resolve by bare or pinned ref, so old attempts keep working. The hidden flag lives in the local library manifest (runtime state, not tracked content).

```powershell
python -m topik_sim hide-pack <pack_id> [--library <dir>]
python -m topik_sim show-pack <pack_id> [--library <dir>]
```

## `validate-library`

Validates the library manifest, imported pack files, and recorded checksums.

```powershell
python -m topik_sim validate-library [--library <library_dir>]
```

## `speak`

Generates Korean TTS audio for direct text. This command remains available under `topik-sim`, but TTS-only workflows should prefer the dedicated `topik-tts` CLI.

```powershell
python -m topik_sim speak "안녕하세요. 오늘은 날씨가 좋습니다." [--tts-play]
python -m topik_sim.tts_cli speak "안녕하세요. 오늘은 날씨가 좋습니다."
```

`topik-sim speak` writes to the audio cache and prints the path. `topik-tts speak` plays directly by default and cleans up its temporary WAV. Use `--save` with `topik-tts speak` to keep the generated WAV and print its path.

Default provider:

- `supertonic`, running in the `.venv-tts` environment created by `setup-tts.ps1` (overridable via `TOPIK_SUPERTONIC_PYTHON` or `--tts-python`).

CUDA provider:

- `melo`, using MeloTTS with `--tts-language KR` and `--tts-device cuda:0`.

Alternate provider:

- `xtts-v2`, using Coqui XTTS-v2. Requires `--tts-speaker-wav`.

## `list-tts-speakers`

Lists provider voices that can be passed to `--tts-speaker-id`. TTS-only workflows should prefer `topik-tts list-speakers`.

```powershell
python -m topik_sim list-tts-speakers [--tts-provider supertonic]
python -m topik_sim.tts_cli list-speakers [--tts-provider supertonic]
```

For Supertonic, use a printed voice preset such as `F1`. For MeloTTS Korean, use either the printed speaker name or numeric ID. XTTS-v2 uses `--tts-speaker-wav` instead of a built-in speaker list.

## Dedicated TTS CLI

Use this when you only want speech generation, voice listing, or WAV playback without the exam simulator commands.

```powershell
python -m topik_sim.tts_cli speak "안녕하세요."
python -m topik_sim.tts_cli speak "안녕하세요." --save
python -m topik_sim.tts_cli list-speakers
python -m topik_sim.tts_cli play data/audio_cache/<file>.wav
```

When installed as a package, the same commands are exposed as:

```powershell
topik-tts speak "안녕하세요."
topik-tts speak "안녕하세요." --save
topik-tts list-speakers
topik-tts play data/audio_cache/<file>.wav
```

See `docs/TTS_SETUP.md` for installation and GPU verification.

or:

```json
{
  "r-001": "B"
}
```

Output shape:

```json
{
  "pack_id": "topik-i-mini",
  "score": 1,
  "max_score": 2,
  "results": [
    {
      "question_id": "r-001",
      "correct": true,
      "points_awarded": 1,
      "max_points": 1,
      "response": "B",
      "feedback": {
        "summary": "...",
        "teaching_points": []
      }
    }
  ]
}
```
