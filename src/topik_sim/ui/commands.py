from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    """One slash command. Slash input is always intercepted by the shell;
    it is never submitted as an answer."""

    name: str
    handler_name: str
    usage: str
    description: str
    aliases: tuple[str, ...] = ()
    details: str = ""
    category: str = "Shell"

    def tokens(self) -> list[str]:
        return [f"/{self.name}"] + [f"/{alias}" for alias in self.aliases]


# Menu and grouped-help order: most useful for a first-time user on top.
CATEGORY_ORDER = [
    "Take a test",
    "Practice",
    "Progress",
    "Library & settings",
    "While answering",
    "Shell",
]


def commands_by_category(commands: list[Command]) -> list[tuple[str, list[Command]]]:
    groups: dict[str, list[Command]] = {}
    for command in commands:
        groups.setdefault(command.category, []).append(command)
    ordered = [(name, groups.pop(name)) for name in CATEGORY_ORDER if name in groups]
    ordered.extend(sorted(groups.items()))
    return ordered


COMMANDS: list[Command] = [
    Command(
        "path", "cmd_path", "/path [unit]", "The staged study path: what to learn at which stage.", ("study", "curriculum"),
        category="Take a test",
        details="A textbook-style scope and sequence for TOPIK I: a Hangul stage, then two levels\n"
        "of ten units, each naming its communicative goals, grammar scope, and vocabulary.\n"
        "Units link to the tool's own courses, homework, writing structures, dialogues, and\n"
        "drills, with your progress marked (✓ done · ◐ in progress). /path <n> (or an id like\n"
        "'food') shows one stage with the exact commands that teach it.\n"
        "Examples: /path · /path 4 · /path shopping",
    ),
    Command(
        "take", "cmd_take", "/take [pack] [section] [limit]", "Start a test from the library or a pack file.",
        category="Take a test",
        details="pack: a library id (Tab completes), a pinned id@version, or a JSON file path.\n"
        "Without a pack, a numbered picker of imported packs opens.\n"
        "section: run a single section id such as listening or reading.\n"
        "limit: cap the number of questions (untimed when limited).\n"
        "Examples: /take · /take topik-i-authentic-mock-01 · /take topik-i-mini-pack reading 5",
    ),
    Command(
        "resume", "cmd_resume", "/resume [n|path]", "Resume a recent in-progress attempt.",
        category="Take a test",
        details="No argument: resumes the only in-progress attempt, or opens a numbered picker.\n"
        "n: an index from /attempts (Tab completes with status). path: an attempt JSON file.\n"
        "Examples: /resume · /resume 2",
    ),
    Command(
        "drill", "cmd_drill", "/drill [n|path]", "Re-practice the questions missed in a completed attempt.",
        category="Take a test",
        details="No argument: drills the most recent completed attempt, or opens a picker when several exist.\n"
        "n: an index from /attempts. path: an attempt JSON file.\n"
        "Examples: /drill · /drill 3",
    ),
    Command(
        "course", "cmd_course", "/course [pack]", "Study a pack as a guided course: vocab, grammar, then its questions.",
        category="Take a test",
        details="Turns an exam pack into a sequence of short lessons. Each course teaches a\n"
        "bounded set of new vocabulary (flashcards) and grammar (cards), then has you answer\n"
        "the exam questions it covers. Bare /course picks a pack; finished courses are ticked.\n"
        "Examples: /course · /course topik-i-authentic-mock-01",
    ),
    Command(
        "homework", "cmd_homework", "/homework [pack] [lesson]", "Do the homework for a course lesson: validate its vocab and grammar.", ("hw",),
        category="Take a test",
        details="Each course lesson gets an auto-generated assignment from exactly what it taught:\n"
        "type the Korean for a gloss, pick meanings and grammar patterns from options (answer\n"
        "with the number), conjugate the verb that fills a sentence's blank, write full\n"
        "sentences with the lesson's patterns, and conjugate the lesson's verbs with the\n"
        "ending it taught. Scores are saved per lesson (best kept); /course\n"
        "shows them next to each lesson. Bare /homework picks a pack; with a pack it lists\n"
        "lessons. Examples: /homework · /homework topik-i-mini-pack · /homework topik-i-mini-pack 1",
    ),
    Command(
        "review", "cmd_review", "/review [pack]", "Spaced-repetition review of questions you have missed before.",
        category="Take a test",
        details="No argument: starts the one pack with items due, or lists due counts per pack.\n"
        "pack: review that pack's due items (misses re-enter the queue, successes wait longer).\n"
        "Examples: /review · /review topik-i-authentic-mock-01",
    ),
    Command(
        "flashcards", "cmd_flashcards", "/flashcards [pack]", "Drill vocabulary cards built from a pack's teaching notes.", ("cards",),
        category="Practice",
        details="pack: the deck is that pack's explanation vocabulary, shuffled. Without a pack,\n"
        "a numbered picker opens. Enter flips the card · y/n grades yourself · /say speaks it ·\n"
        "/pause stops with a summary. Example: /flashcards topik-i-authentic-mock-01",
    ),
    Command(
        "dictation", "cmd_dictation", "/dictation [pack] [limit]", "Hear listening transcripts and type what you hear.",
        category="Practice",
        details="pack: sentences are that pack's listening transcripts in order; without a pack,\n"
        "a numbered picker opens. limit: practice only the first n sentences.\n"
        "/replay repeats the audio · /pause stops.\n"
        "Examples: /dictation topik-i-authentic-mock-01 · /dictation topik-i-authentic-mock-01 5",
    ),
    Command(
        "grammar", "cmd_grammar", "/grammar [pack] [count]", "Drill grammar patterns with their explanations and examples.", ("gram",),
        category="Practice",
        details="Cards built from the grammar notes in teaching explanations: front shows the\n"
        "pattern (e.g. -(으)러 가다), the flip shows what it does plus an example sentence.\n"
        "pack: drill one pack; without it, patterns come from every imported pack (default 20 cards).\n"
        "count: deck size. /say speaks the example. Examples: /grammar · /grammar topik-i-authentic-mock-01 · /grammar 40",
    ),
    Command(
        "recall", "cmd_recall", "/recall [pack] [count]", "See an English word, type its Korean translation.", ("translate",),
        category="Practice",
        details="Active production practice: the English gloss is shown and you type the Korean.\n"
        "Synonyms are fair — any Korean word taught with that gloss counts. A miss shows the\n"
        "answer with its 두벌식 keys. pack: scope to one pack; bare uses every imported pack.\n"
        "count: number of words (default 10). Examples: /recall · /recall topik-i-authentic-mock-02 15",
    ),
    Command(
        "dialogue", "cmd_dialogue", "/dialogue [id]", "Play a real-life conversation and produce your own lines.", ("talk", "convo"),
        category="Practice",
        details="Communicative practice: a situation runs turn by turn — the partner's lines are\n"
        "shown (and spoken), and on your turns you type the Korean for a stated intent. An exact\n"
        "match passes; otherwise the model line is revealed and you self-rate. Scenarios cover\n"
        "self-introduction, restaurant, shopping, directions, and phone calls. /say hears the\n"
        "model line. Bare /dialogue lists scenarios. Examples: /dialogue · /dialogue restaurant",
    ),
    Command(
        "compose", "cmd_compose", "/compose [structure]", "Learn a grammar structure, then write sentences with it.", ("write",),
        category="Practice",
        details="Sentence-writing grounded in grammar. Pick a structure (e.g. -고 싶다); it is taught\n"
        "up front — meaning, an example, and how it appears in your imported packs — then you\n"
        "write several English-to-Korean sentences that all use it. An exact match auto-passes;\n"
        "otherwise the model is revealed and you self-rate y/n. /say reads the model aloud.\n"
        "Examples: /compose · /compose random · /compose 싶 · /compose past-tense",
    ),
    Command(
        "typing", "cmd_typing", "/typing [advanced] [pack] [count]", "Practice the Korean keyboard: jamo, syllables, then words.",
        category="Practice",
        details="pack: scope the word items to that pack's vocabulary; without it, words are drawn\n"
        "from every imported pack. count: number of items (default 12). Real pack words reveal their\n"
        "meaning after you answer; a miss also reveals the 두벌식 keystrokes.\n"
        "advanced: skip the jamo/syllable warm-up — drill meaningful words AND full sentences, each with\n"
        "its English meaning shown after. Naming a pack also bounds the sentences to its TOPIK level.\n"
        "Examples: /typing · /typing 20 · /typing advanced · /typing advanced topik-i-mini-pack 15",
    ),
    Command(
        "conjugate", "cmd_conjugate", "/conjugate [pack] [form] [count]", "Practice conjugating verbs across tenses, connectives, and modals.", ("conj",),
        category="Practice",
        details="Shows a dictionary-form verb (읽다) and you type its conjugation. form defaults to\n"
        "mix — every ending interleaved, a different one per verb (the prompt names each target).\n"
        "Name a form to focus: polite (-아/어요), formal (-습니다), past, past-formal, future,\n"
        "negation, want, can, if, because, so, must, honorific — /conjugate list shows them all.\n"
        "Verbs come from a named pack or every imported pack; irregular classes (ㅂ, ㄷ, ㅅ, 르,\n"
        "으, ㅎ) are conjugated by rule, never guessed.\n"
        "Examples: /conjugate · /conjugate past · /conjugate future topik-i-mini-pack 15 · /conjugate list",
    ),
    Command(
        "sounds", "cmd_sounds", "/sounds [drill] [rule] [count]", "Korean sound-change rules: why speech differs from spelling.", ("pronounce", "pronunciation"),
        category="Practice",
        details="Bare /sounds is the reference — the seven rules (연음, 경음화, 비음화, 유음화,\n"
        "격음화, 구개음화, ㅎ-weakening) with spelled→spoken examples. /sounds drill practices\n"
        "them: a word is shown and you type how it is actually pronounced (책상 → 책쌍), then\n"
        "/say reads the sound. Add a rule id to focus (e.g. /sounds drill gyeongeum).\n"
        "Examples: /sounds · /sounds drill · /sounds drill yeoneum 8",
    ),
    Command(
        "hangul", "cmd_hangul", "/hangul", "Learn to read Hangul from zero: letters, sounds, and blocks.", ("read", "alphabet"),
        category="Practice",
        details="The from-scratch on-ramp: every consonant and vowel with its sound, how jamo\n"
        "stack into syllable blocks, the 받침 rule, and worked examples (한 → han, 학생 →\n"
        "hak-saeng) plus a reading-practice grid. Romanization appears only here, as training\n"
        "wheels. Follow with /typing to practice and /say <text> to hear anything aloud.",
    ),
    Command(
        "numbers", "cmd_numbers", "/numbers [category] [count]", "Practice Korean numbers: write them in Hangul, no digits.", ("num", "number"),
        category="Practice",
        details="Drills both number systems and the contexts that pick between them. Answers must\n"
        "be Korean letters — digits are rejected. category (default mix): sino, native, count\n"
        "(objects + counter), date, time, money, math, phone, ordinal. count: items (default 10).\n"
        "/numbers learn shows both systems as tables (with counters and which-system-when)\n"
        "before you drill. /say reads the correct form aloud.\n"
        "Examples: /numbers learn · /numbers · /numbers date · /numbers money 15",
    ),
    Command(
        "colors", "cmd_colors", "/colors [category] [count]", "Practice Korean colors: see a color, name it in Hangul.", ("color", "colour", "colours"),
        category="Practice",
        details="Shows a real color swatch and asks for its Korean name; answers must be Korean\n"
        "letters. category (default mix): swatch (name the color shown), word (English → Korean),\n"
        "modifier (빨간 사과 — the ㅎ-irregular form before a noun), shade (연한/진한), object\n"
        "(바나나는 무슨 색이에요?), sino (녹색·백색·흑색). count: items (default 10).\n"
        "/colors learn shows every color with its modifier and Sino-Korean form first.\n"
        "Terminals without color fall back to naming the color in English.\n"
        "Examples: /colors learn · /colors · /colors swatch · /colors modifier 15",
    ),
    Command(
        "vocab", "cmd_vocab", "/vocab [pack] [count]", "Spaced vocabulary review: see the meaning, type the Korean.", ("v",),
        category="Practice",
        details="A true spaced-repetition schedule over every word your packs teach and every wordlist\n"
        "entry: due words come back first, then a few new ones are introduced each session. A correct\n"
        "answer pushes the word further out (box 1→5, up to ~35 days); a miss brings it back tomorrow.\n"
        "Progress is saved in data/attempts/vocab_review.json. Naming a pack scopes the session to that\n"
        "exam's vocabulary — what it teaches plus what was mined from it — which is how to drill one\n"
        "past paper's words. count: session size (default 15).\n"
        "Examples: /vocab · /vocab 25 · /vocab topik1-past-102 · /vocab topik1-past-102 30",
    ),
    Command(
        "misses", "cmd_misses", "/misses [count]", "Drill your weak items: the things you keep getting wrong.", ("weak",),
        category="Practice",
        details="Rebuilds a typed drill from your most-missed practice items (recorded in the\n"
        "practice log by every drill and homework run). Vocabulary is asked from its English\n"
        "gloss; anything else is retyped correctly. Items drop off the weak list once you stop\n"
        "missing them. count: items (default 10). Examples: /misses · /misses 5",
    ),
    Command(
        "lookup", "cmd_lookup", "/lookup <text>", "Search everything your packs teach: vocabulary and grammar.", ("dict", "search"),
        category="Practice",
        details="The 'what was that word again?' command. Searches every imported pack's taught\n"
        "vocabulary (Korean, English, notes) and grammar patterns by substring, and names the\n"
        "pack each hit comes from. Works any time, even mid-question.\n"
        "Examples: /lookup 학생 · /lookup weather · /lookup 에서",
    ),
    Command(
        "facts", "cmd_facts", "/facts [category|list]", "Discover a fact about Korea — culture, history, food, and more.", ("fact", "culture"),
        category="Practice",
        details="A random interesting fact each time, with a Korean phrase, its translation,\n"
        "useful vocabulary, and a short language note. Pass a category to focus it, or\n"
        "'list' to see them. After a fact, a bare /say reads the Korean aloud.\n"
        "Examples: /facts · /facts history · /facts food · /facts list",
    ),
    Command(
        "attempts", "cmd_attempts", "/attempts", "List recent attempts.",
        category="Progress",
        details="The numbers shown are what /resume <n>, /drill <n>, and /report <n> accept.",
    ),
    Command(
        "status", "cmd_status", "/status", "Show session progress and speech settings.",
        category="Progress",
        details="Pack, activity, progress, running score, and the TTS provider/voice/speed/volume.",
    ),
    Command(
        "stats", "cmd_stats", "/stats", "Per-skill accuracy and trends across completed attempts.",
        category="Progress",
        details="Aggregates every completed attempt: listening vs reading accuracy, average pace,\n"
        "recent results, and per-pack best/last scores.",
    ),
    Command(
        "report", "cmd_report", "/report [n|path]", "Write a Markdown study report for a completed attempt.",
        category="Progress",
        details="Saves misses with correct answers, vocabulary, and grammar to review under the\n"
        "attempts directory. n/path pick the attempt like /resume; a picker opens when ambiguous.\n"
        "Examples: /report · /report 2",
    ),
    Command(
        "packs", "cmd_packs", "/packs [filter|all]", "List imported packs grouped by level, with your progress.",
        category="Library & settings",
        details="Grouped by TOPIK level; each row shows version, difficulty label, size, and your\n"
        "best score. filter narrows by level (i, ii) or any text (e.g. authentic); all includes\n"
        "hidden packs. Hide retired packs with: topik-sim hide-pack <pack_id>.\n"
        "Examples: /packs · /packs i · /packs authentic · /packs all",
    ),
    Command(
        "tts", "cmd_tts", "/tts [on|off|volume <x>|speed <x>|provider <p>|voice <v>]", "Show or change speech settings.",
        category="Library & settings",
        details="Bare /tts shows current settings. on/off toggles speech · volume and speed take a\n"
        "number (1.0 = unchanged) · provider: supertonic, melo, xtts-v2 · voice: a preset like F1 or M1.\n"
        "Examples: /tts volume 0.8 · /tts voice M1 · /tts off",
    ),
    Command(
        "keyboard", "cmd_keyboard", "/keyboard [on|off|pin|unpin]", "Show the 두벌식 layout; on pins it to the toolbar and adds typing hints.", ("kb",),
        category="Library & settings",
        details="Bare /keyboard prints the full chart once. on: pin a compact chart to the toolbar\n"
        "(it hovers above the input line) AND show keystroke hints in dictation, flashcards, and /typing.\n"
        "off: disable both. pin/unpin: dock or free the chart without touching hints.\n"
        "Examples: /keyboard · /keyboard on · /keyboard unpin",
    ),
    Command(
        "say", "cmd_say", "/say [text]", "Pronounce any sentence aloud; does not touch your answer.", ("speak",),
        category="While answering",
        details="Speaks the text with the current TTS settings, mid-question or idle.\n"
        "During /flashcards or /typing, bare /say speaks the current card or item.\n"
        "Examples: /say 안녕하세요 · /say",
    ),
    Command(
        "hint", "cmd_hint", "/hint", "Reveal one vocabulary hint for the current question.",
        category="While answering",
        details="Each call reveals the next vocabulary item from the open question's teaching notes\n"
        "without giving the answer away. Stops when all items are shown.",
    ),
    Command(
        "replay", "cmd_replay", "/replay [slow]", "Play the current question audio again; 'slow' at 3/4 speed.", ("r",),
        category="While answering",
        details="Replays the active question or dictation audio at the current /tts volume.\n"
        "/replay slow re-speaks it at three-quarter speed — the 'could you say that again,\n"
        "slowly?' every listening student needs. Examples: /replay · /replay slow",
    ),
    Command(
        "transcript", "cmd_transcript", "/transcript", "Reveal the transcript of the current listening question.", ("t",),
        category="While answering",
        details="Shows what the audio says, before or after answering. Useful when studying rather than testing.",
    ),
    Command(
        "skip", "cmd_skip", "/skip", "Submit a blank answer for the current question.",
        category="While answering",
        details="Recorded as unanswered (wrong); the question lands in /drill and /review afterwards.",
    ),
    Command(
        "pause", "cmd_pause", "/pause", "Save the current test and return to idle; resume later.",
        category="While answering",
        details="Attempts save after every answer, so nothing is lost. Also stops flashcards,\n"
        "dictation, or typing practice early with a summary.",
    ),
    Command(
        "menu", "cmd_menu", "/menu", "Browse everything by category; Enter at an idle prompt opens it too.", ("m",),
        category="Shell",
        details="Level 1 lists functional areas; pick a number to see that area's commands;\n"
        "pick again to run one. Enter goes back, then closes.",
    ),
    Command(
        "help", "cmd_help", "/help [command]", "Show all commands, or one command's arguments and examples.", ("h", "?"),
        category="Shell",
        details="With a command name, shows what its arguments mean and example calls.\n"
        "Examples: /help typing · /help tts",
    ),
    Command(
        "quit", "cmd_quit", "/quit", "Exit the shell. Progress is already saved.", ("exit", "q"),
        category="Shell",
        details="Attempts save after every answer; /resume continues where you left off next time.",
    ),
]


class CommandRegistry:
    def __init__(self, commands: list[Command]) -> None:
        self._commands = list(commands)
        self._lookup: dict[str, Command] = {}
        for command in commands:
            for token in [command.name, *command.aliases]:
                if token in self._lookup:
                    raise ValueError(f"Command token {token!r} is registered twice.")
                self._lookup[token] = command

    def find(self, token: str) -> Command | None:
        return self._lookup.get(token.lower())

    def all(self) -> list[Command]:
        return list(self._commands)
