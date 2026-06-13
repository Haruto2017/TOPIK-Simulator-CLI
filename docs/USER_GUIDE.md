# TOPIK Simulator — User Guide

## What this is

The TOPIK simulator is a study environment for the TOPIK I exam that runs on your own computer, in your terminal. You sit full-length timed mock exams — 듣기 (listening) with spoken Korean audio and 읽기 (reading) — answer question by question, and get instant grading with teaching feedback: the correct answer, why it is correct, and the vocabulary and grammar behind it.

Around the exams sits a complete study loop. Every question you miss is remembered: you can drill the misses from any exam, review them on a spaced-repetition schedule, and watch your accuracy trend over weeks. There are also focused practice tools — vocabulary flashcards, grammar pattern cards, type-the-Korean recall, listen-and-type dictation, and a Korean keyboard trainer. Everything works offline, and your progress saves itself after every single answer.

## Install & first launch

You need:

1. **Windows** with **Python 3.9 or newer**. Get it from python.org and tick "Add python.exe to PATH" in the installer.
2. **This folder** — the one containing `topik.cmd`.
3. Optional but recommended: run `pip install prompt_toolkit` once. It enables slash-command autocompletion, the countdown toolbar, and the pinned keyboard chart. Everything still works without it, just with plainer prompts.
4. Optional: Korean speech, so listening questions play real audio — run `.\setup-tts.ps1` once. Without it, exams remain fully usable — transcripts appear automatically (see the FAQ).

Open PowerShell in this folder and run:

```powershell
.\topik.cmd
```

On the very first launch, with no exams imported yet, the shell offers to import the bundled mock exams in one keystroke — accept it. (You can also run `.\topik.cmd setup` at any time; it is safe to repeat and never overwrites exams you already have.)

You land at a prompt. Two rules cover everything:

- **Press Enter on the empty prompt** to open the menu: six numbered areas (Take a test, Practice, Progress, Library & settings, While answering, Shell). Pick a number to see that area's commands, pick again to run one. Enter steps back out.
- **Anything starting with `/` is a command** — it is never treated as an answer. `/help` lists every command, `/help take` explains one in detail with examples, `/quit` exits.

If something misbehaves — no audio, strange characters, missing exams — run the self-check:

```powershell
.\topik.cmd doctor
```

It prints PASS, WARN, or FAIL for each requirement, each with a one-line fix.

## Your first mock exam

Launch `.\topik.cmd`, then either press Enter and pick **Take a test** → `/take`, or just type:

```
/take
```

A numbered picker lists your imported exams with their titles and sizes. Pick **TOPIK I Authentic Mock Exam 01 (실전 모의고사)**. It is shaped like the real TOPIK I: 70 questions — 듣기 (listening, 40 minutes) then 읽기 (reading, 60 minutes) — with 100 points per section.

The first listening question appears. The audio plays by itself and the transcript stays hidden, exactly like the real exam; while you think, the next question's audio is already being prepared in the background. You see the question prompt and four numbered options. To answer, type the option's number and press Enter:

```
2
```

Need to hear it again? `/replay` (or `/r`). Want a nudge? Each `/hint` reveals one vocabulary item from the question's teaching notes. Completely stuck? `/skip` records a blank answer and moves on — that question will be waiting for you in `/drill` and `/review` later.

After every answer you get immediate feedback: whether you were right, a short explanation of the correct option, the key vocabulary, and the grammar patterns involved. For listening questions, the transcript is revealed now, so you can re-read what you just heard.

A few things are quietly true the whole time:

- With prompt_toolkit installed, the toolbar at the bottom counts down the section time, like the clock on the exam-room wall.
- Your attempt is saved after every answer. `/pause` saves and leaves the exam; `/resume` continues it later, even after closing the window. A crash loses nothing.
- `/say 천천히 말해 주세요` pronounces any sentence aloud at any moment, without touching your answer.

When the last question is answered, the whole attempt is graded: score per section, total out of 200, and your pace against the time limits. Your misses are added to the review queue automatically.

Then write yourself a study sheet:

```
/report
```

It saves a Markdown report of the attempt — every miss with its correct answer, plus the vocabulary and grammar to review — under your data folder. Reading yesterday's report is a study session by itself.

## Study routines

**Daily 20 minutes.** On launch, the shell tells you how many review items are due. Clear them first, then push a little further:

1. `/review` — answer today's due items; spaced repetition decides what those are.
2. `/drill` — re-take the misses from your most recent completed exam.
3. `/recall` — ten English words appear one by one; you type the Korean (10 is the default).
4. `/grammar 10` — ten grammar pattern cards drawn from across your exams.

To finish on something lighter, run `/facts` for a bite of Korean culture, history, or daily life — each comes with a Korean phrase you can hear with `/say`.

**Exam week.** Every other day, sit a full timed mock with `/take` — no `/transcript`, no `/hint`, treat the countdown as real. Finish, then `/report`, and read it the same evening. On the off days, `/drill` the misses and clear `/review`. Run `/stats` after each mock and watch the listening/reading split: the trend matters more than any single score.

**Listening focus.** `/dictation topik-i-authentic-mock-01 10` speaks a transcript sentence and you type what you hear; the feedback diff shows exactly which syllable you lost, and `/replay` repeats it. Then re-run a mock's listening section on its own: `/take topik-i-authentic-mock-01 listening`. Generous use of `/replay` while practicing is not cheating.

**Absolute beginner.** Before attempting a mock: `/keyboard on` pins the 두벌식 layout chart above the input line and turns on keystroke hints everywhere you type. Then `/typing` daily — it ramps from single jamo to syllables to real exam vocabulary, and every miss shows the exact keys. Add `/flashcards` for the pack you plan to take. When typing Korean stops being the hard part, ease in with a short untimed slice: `/take topik-i-authentic-mock-01 listening 10`.

## Command cheatsheet

**Take a test**

| Command | What it does |
| --- | --- |
| `/take [pack] [section] [limit]` | Start a test; bare `/take` opens a pack picker. A `limit` run is untimed. |
| `/resume [n]` | Continue an in-progress attempt; picker when there are several. |
| `/drill [n]` | Re-practice the misses from a completed attempt. |
| `/review [pack]` | Spaced-repetition session over questions you have missed before. |

**Practice**

| Command | What it does |
| --- | --- |
| `/flashcards [pack]` (`/cards`) | Vocabulary cards from a pack; Enter flips, y/n grades. |
| `/dictation [pack] [limit]` | Hear a sentence, type what you heard, see the diff. |
| `/grammar [pack] [count]` (`/gram`) | Grammar pattern cards; bare uses every pack, 20 cards. |
| `/recall [pack] [count]` (`/translate`) | English gloss shown, you type the Korean; default 10 words. |
| `/typing [pack] [count]` | Keyboard trainer: jamo → syllables → exam words. |
| `/facts [category\|list]` (`/fact`, `/culture`) | An interesting fact about Korea with a Korean phrase and notes; `/say` reads it aloud. |

**Progress**

| Command | What it does |
| --- | --- |
| `/attempts` | List attempts; the numbers feed `/resume`, `/drill`, `/report`. |
| `/status` | Current progress, running score, and speech settings. |
| `/stats` | Accuracy per skill and trends across completed attempts. |
| `/report [n]` | Write a Markdown study report for a completed attempt. |

**Library & settings**

| Command | What it does |
| --- | --- |
| `/packs` | List imported exams and their ids. |
| `/tts [on/off/volume x/speed x/voice v]` | Show or change speech settings live. |
| `/keyboard [on/off/pin/unpin]` (`/kb`) | 두벌식 chart; `on` pins it and adds typing hints. |

**While answering**

| Command | What it does |
| --- | --- |
| `/say [text]` (`/speak`) | Pronounce any sentence aloud; never counts as an answer. |
| `/hint` | Reveal one vocabulary item per call. |
| `/replay` (`/r`) | Play the current question audio again. |
| `/transcript` (`/t`) | Reveal the listening transcript — for studying, not testing. |
| `/skip` | Submit a blank answer and move on. |
| `/pause` | Save and leave the test; also stops practice modes early. |

**Shell**

| Command | What it does |
| --- | --- |
| Enter on empty prompt, or `/menu` (`/m`) | Open the category menu. |
| `/help [command]` (`/h`) | All commands, or one explained with examples. |
| `/quit` (`/q`) | Exit; everything is already saved. |

The same launcher also runs one-off commands without opening the shell: `.\topik.cmd doctor` (self-check), `.\topik.cmd setup` (import the bundled exams), `.\topik.cmd import-pack <file.json>` (add an exam), `.\topik.cmd audio warm <pack-id>` (pre-generate a pack's listening audio).

To make settings stick between sessions — voice, volume, speed, always-visible transcripts, keyboard hints on at startup — copy `examples\topik.config.example.json` to `topik.config.json` in this folder and edit it.

## FAQ

**No sound, or no speech runtime installed?**
To get audio, run `.\setup-tts.ps1` once — it installs the speech engine into a private environment that the simulator finds by itself (the voice model downloads the first time audio plays). Until then exams stay fully usable: when a listening question has no playable audio, the simulator says so and shows the transcript before you answer, so nothing blocks you. If you have audio but want silence, `/tts off`. To find out what the speech system is missing, run `.\topik.cmd doctor`.

**How do I type Korean on Windows?**
Settings → Time & language → Language & region → Add a language → 한국어. That installs the Microsoft Korean IME. Switch between English and Korean with the 한/영 key — on most non-Korean keyboards that is the **right Alt** key (Win+Space also cycles input methods). Inside the simulator, `/keyboard on` pins the 두벌식 layout chart so you can see where every letter lives, and `/typing` trains you from single letters up to full words.

**Korean looks garbled — boxes or question marks?**
Use Windows Terminal rather than the legacy console window, and pick a UTF-8-capable font with Hangul coverage such as D2Coding or Cascadia Code. Fix the display before continuing; do not answer from garbled text.

**Where is my data?**
Everything you produce lives in the `data` folder: attempts and study reports under `data\attempts` (your spaced-repetition review queue is kept there too), and generated audio under `data\audio_cache`. Imported exams live separately in `content\library`. Deleting `data` resets your progress and audio cache but keeps your exams; if you ever delete `content\library`, run `.\topik.cmd setup` to restore the bundled ones.

**Can I add more exams?**
Yes. Exams are JSON "packs": import one with `.\topik.cmd import-pack my_pack.json` and it appears in `/packs` and the `/take` picker. The pack format is documented in `docs/CONTENT_CONTRACT.md` — advanced reading. Use only material you have the right to use: original, licensed, public-domain, or your own.

**How is my score calculated?**
Every question carries a point value (3 or 4 points in the bundled mocks), and each section totals 100 points, like the real exam. Multiple-choice answers are graded instantly. Essay-style answers, in packs that contain them, are scored manually against a rubric after the attempt; half marks or better counts the question as correct.

**The exam pauses to generate audio?**
The first time a sentence is spoken it is synthesized and cached; after that it plays instantly. To do all of that ahead of time, warm the pack before sitting it: `.\topik.cmd audio warm topik-i-authentic-mock-01`.

**Which exam should I take?** Run `/packs` (or just `/take` and read the picker): exams are grouped by TOPIK level, and each row shows its difficulty label — `starter (English options)` packs are gentle warm-ups with English answer choices, `authentic` packs match the real exam (everything in Korean) — plus your best score so far or `untaken`. Start on a starter pack if you are brand new; move to the authentic mocks as soon as you can. Typing text in the picker (for example `authentic` or `ii`) narrows the list, and you can hide packs you have outgrown with `.\topik.cmd hide-pack <pack-id>`.

## Glossary

- **Pack** — one importable exam or practice set: a JSON file of sections, questions, answers, and teaching notes.
- **Attempt** — one saved run of a test or drill, written to disk after every answer; resumable until completed.
- **Drill** — a new attempt built from only the questions you missed in a completed attempt.
- **Review queue** — the spaced-repetition list of your past misses; items come due at growing intervals (1, 2, 4, 7, then 15 days) and retire after enough correct reviews.
- **Warm audio** — pre-generating a pack's listening audio into the cache so every question plays instantly during the exam.
