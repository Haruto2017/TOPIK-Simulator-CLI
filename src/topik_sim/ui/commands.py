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
        "compose", "cmd_compose", "/compose [structure]", "Learn a grammar structure, then write sentences with it.", ("write",),
        category="Practice",
        details="Sentence-writing grounded in grammar. Pick a structure (e.g. -고 싶다); it is taught\n"
        "up front — meaning, an example, and how it appears in your imported packs — then you\n"
        "write several English-to-Korean sentences that all use it. An exact match auto-passes;\n"
        "otherwise the model is revealed and you self-rate y/n. /say reads the model aloud.\n"
        "Examples: /compose · /compose random · /compose 싶 · /compose past-tense",
    ),
    Command(
        "typing", "cmd_typing", "/typing [pack] [count]", "Practice the Korean keyboard: jamo, syllables, then words.",
        category="Practice",
        details="pack: scope the word items to that pack's vocabulary; without it, words are drawn\n"
        "from every imported pack. count: number of items (default 12).\n"
        "A miss reveals the 두벌식 keystrokes. Examples: /typing · /typing 20 · /typing topik-i-mini-pack 15",
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
        "replay", "cmd_replay", "/replay", "Play the current question audio again.", ("r",),
        category="While answering",
        details="Replays the active question or dictation audio at the current /tts volume.",
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
