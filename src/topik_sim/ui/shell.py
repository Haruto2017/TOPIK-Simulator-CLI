from __future__ import annotations

import random
import shlex
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from ..activities import create_drill_attempt, missed_question_ids
from ..attempts import load_attempt, save_attempt_to_dir
from ..content import ContentValidationError, ExamPack, load_pack
from ..library import DEFAULT_LIBRARY_DIR, latest_packs, list_packs, load_pack_ref
from ..media import question_audio_file
from ..prefetch import AudioPrefetcher
from ..session import ExamSession
from ..tts import (
    TTSConfig,
    collect_question_speech_texts,
    is_listening_question,
    play_audio,
    synthesize_many,
)
from . import ansi, render
from .commands import COMMANDS, CommandRegistry


IDLE = "idle"
ANSWERING = "answering"
CONTINUE = "continue"
FLASH_FRONT = "flash_front"
FLASH_BACK = "flash_back"
DICTATION = "dictation"
TYPING = "typing"
COMPOSE_PICK = "compose_pick"
COMPOSE_TYPE = "compose_type"
COMPOSE_GRADE = "compose_grade"
DIALOGUE_PICK = "dialogue_pick"
DIALOGUE_TYPE = "dialogue_type"
DIALOGUE_GRADE = "dialogue_grade"
COURSE_PICK = "course_pick"
COURSE_STEP = "course_step"
HOMEWORK_PICK = "homework_pick"
PICK = "pick"
PICK_PACK = "pick_pack"
MENU = "menu"
MENU_CATEGORY = "menu_category"

TTS_PROVIDERS = ("supertonic", "melo", "xtts-v2")
DEFAULT_ATTEMPT_DIR = "data/attempts"
RECENT_LIMIT = 10

# Shorthand used across grammar patterns; shown wherever patterns appear so a
# first-time student can decode "N이에요/예요?".
GRAMMAR_LEGEND = "Pattern shorthand: N = noun · V = verb stem · A = descriptive-verb stem · (으) = added after a final consonant"

# Typed-drill labels → practice-log modes (see practice_log.py).
TYPING_LABEL_MODES = {
    "Typing practice": "typing",
    "Advanced typing": "typing",
    "Number practice": "numbers",
    "Color practice": "colors",
    "Vocab recall": "recall",
    "Homework": "homework",
    "Weak items": "misses",
    "Conjugation": "conjugate",
    "Vocabulary review": "vocab",
    "Pronunciation": "sounds",
}


class Shell:
    """Interactive session: slash input is a command, anything else is an answer.

    All state transitions go through handle_line, so the shell is fully
    drivable from tests without a terminal.
    """

    def __init__(
        self,
        library_dir: str | Path = DEFAULT_LIBRARY_DIR,
        attempt_dir: str | Path = DEFAULT_ATTEMPT_DIR,
        tts_config: TTSConfig | None = None,
        output: Callable[[str], None] = print,
        audio_enabled: bool = True,
        show_transcript: bool = False,
        prefetcher: AudioPrefetcher | None = None,
        flashcard_seed: int | None = None,
        keyboard_hints: bool = False,
        keyboard_pinned: bool = False,
        facts_path: str | Path | None = None,
        compose_path: str | Path | None = None,
        dialogues_path: str | Path | None = None,
    ) -> None:
        self.library_dir = Path(library_dir)
        self.attempt_dir = Path(attempt_dir)
        self.tts_config = tts_config or TTSConfig()
        self.audio_enabled = audio_enabled
        self.show_transcript = show_transcript
        self.registry = CommandRegistry(COMMANDS)
        self.session: ExamSession | None = None
        self.state = IDLE
        self.current_audio: list[Path] = []
        self.prefetcher = prefetcher or AudioPrefetcher()
        self._output = output
        self._active_question: dict[str, Any] | None = None
        self._transcript_pre_shown = False
        self._recent_attempts: list[tuple[Path, dict[str, Any]]] = []
        self._hint_index = 0
        self._quit = False
        self._tts_warned = False
        # Completion runs on every keystroke; cache its disk reads briefly.
        self._completion_cache: dict[str, tuple[float, list]] = {}
        self._flashcard_seed = flashcard_seed
        self._flash_deck: list[dict[str, str]] = []
        self._flash_index = 0
        self._flash_known = 0
        self._flash_missed: list[str] = []
        self._flash_label = "Flashcards"
        self._dictation_texts: list[str] = []
        self._dictation_index = 0
        self._dictation_total_accuracy = 0.0
        self._dictation_perfect = 0
        self._pick_entries: list[tuple[Path, dict[str, Any]]] = []
        self._pick_action: str | None = None
        self._pack_pick_refs: list[str] = []
        self._pack_pick_action: str | None = None
        self._menu_categories: list[tuple[str, list[Any]]] = []
        self._menu_group: list[Any] = []
        self.keyboard_hints = keyboard_hints
        self.keyboard_pinned = keyboard_pinned
        self._typing_items: list[dict[str, Any]] = []
        self._typing_index = 0
        self._typing_hits = 0
        self._typing_missed: list[str] = []
        self._typing_label = "Typing practice"
        self._typing_verb = "Typed"
        from ..facts import DEFAULT_FACTS_PATH

        self.facts_path = Path(facts_path) if facts_path is not None else DEFAULT_FACTS_PATH
        self._facts: list[dict[str, Any]] | None = None
        self._facts_seen: set[str] = set()
        self._facts_rng = random.Random(flashcard_seed)
        self._fact_speech = ""
        from ..compose import DEFAULT_COMPOSE_PATH
        from ..courses import DEFAULT_COURSES_PATH

        self.courses_path = DEFAULT_COURSES_PATH
        self._course: dict[str, Any] | None = None
        self._course_pack: Any = None
        self._course_list: list[dict[str, Any]] = []
        self._homework_pack: Any = None
        self._homework_courses: list[dict[str, Any]] = []
        self._typing_homework: tuple[str, str] | None = None
        self._typing_srs: bool = False
        self._vocab_deck: dict[str, Any] | None = None
        self.compose_path = Path(compose_path) if compose_path is not None else DEFAULT_COMPOSE_PATH
        self._compose_rng = random.Random(flashcard_seed)
        self._lessons: list[dict[str, Any]] | None = None
        self._pack_grammar: list[dict[str, str]] | None = None
        self._lesson_pick: list[dict[str, Any]] = []
        self._compose_items: list[dict[str, Any]] = []
        self._compose_index = 0
        self._compose_hits = 0
        self._compose_missed: list[dict[str, Any]] = []
        from ..dialogues import DEFAULT_DIALOGUES_PATH

        self.dialogues_path = Path(dialogues_path) if dialogues_path is not None else DEFAULT_DIALOGUES_PATH
        self._dialogue: dict[str, Any] | None = None
        self._dialogue_index = 0
        self._dialogue_hits = 0
        self._dialogue_total = 0
        self._dialogue_pick: list[dict[str, Any]] = []

    # ------------------------------------------------------------- plumbing

    def emit(self, text: str = "") -> None:
        self._output(text)

    def close(self) -> None:
        self.prefetcher.close()

    def status_line(self) -> str:
        """Bottom-toolbar content. With the keyboard pinned, the compact
        layout hovers above the status line and never scrolls away."""
        status = self._status_text()
        if self.keyboard_pinned:
            return render.keyboard_toolbar() + "\n" + status
        return status

    def _status_text(self) -> str:
        tts_state = self.tts_config.provider if self.audio_enabled else "off"
        if self.session is None:
            return f" idle · Enter = menu · /take starts a test · TTS {tts_state} · /help "
        answered, total = self.session.progress()
        earned, available = self.session.running_score()
        timer = ""
        remaining = self.session.remaining_seconds()
        if remaining is not None:
            if remaining >= 0:
                timer = f" · {render.format_clock(remaining)} left"
            else:
                timer = f" · over by {render.format_clock(-remaining)}"
        return (
            f" {self.session.pack.pack_id} · Q{min(answered + 1, total)}/{total}"
            f" · score {earned}/{available}{timer} · TTS {tts_state} · /help "
        )

    def handle_line(self, line: str) -> bool:
        """Process one line of input. Returns False when the shell should exit."""
        # Piped input on Windows can carry a UTF-8 BOM; drop it before parsing.
        text = line.lstrip("﻿").strip()
        if text.startswith("/"):
            self._dispatch(text)
        elif self.state == ANSWERING:
            if text:
                self._submit(text)
            else:
                self.emit("Type an answer, or /help for commands.")
        elif self.state == CONTINUE:
            if text:
                self.emit("Press Enter for the next question, or /replay to hear it again.")
            else:
                self._advance()
        elif self.state == FLASH_FRONT:
            if text:
                self.emit("Press Enter to flip the card, or /pause to stop.")
            else:
                self._flip_card()
        elif self.state == FLASH_BACK:
            if text.lower() in {"y", "yes"}:
                self._grade_card(True)
            elif text.lower() in {"n", "no"}:
                self._grade_card(False)
            else:
                self.emit("y if you knew it, n if not.")
        elif self.state == DICTATION:
            if text:
                self._grade_dictation(text)
            else:
                self.emit("Type what you heard, or /replay to hear it again.")
        elif self.state == TYPING:
            if text:
                self._grade_typing(text)
            else:
                self.emit("Type the shown text, or /pause to stop.")
        elif self.state == COURSE_PICK:
            self._handle_course_pick(text)
        elif self.state == COURSE_STEP:
            self._handle_course_step(text)
        elif self.state == HOMEWORK_PICK:
            self._handle_homework_pick(text)
        elif self.state == COMPOSE_PICK:
            self._handle_lesson_pick(text)
        elif self.state == COMPOSE_TYPE:
            if text:
                self._grade_compose(text)
            else:
                self.emit("Type the Korean translation, or /pause to stop.")
        elif self.state == COMPOSE_GRADE:
            if text.lower() in {"y", "yes"}:
                self._selfgrade_compose(True)
            elif text.lower() in {"n", "no"}:
                self._selfgrade_compose(False)
            else:
                self.emit("y if your sentence was right, n if not.")
        elif self.state == DIALOGUE_PICK:
            self._handle_dialogue_pick(text)
        elif self.state == DIALOGUE_TYPE:
            if text:
                self._grade_dialogue(text)
            else:
                self.emit("Type your Korean line, or /pause to leave the conversation.")
        elif self.state == DIALOGUE_GRADE:
            if text.lower() in {"y", "yes"}:
                self._selfgrade_dialogue(True)
            elif text.lower() in {"n", "no"}:
                self._selfgrade_dialogue(False)
            else:
                self.emit("y if your line was right, n if not.")
        elif self.state == PICK:
            self._handle_pick(text)
        elif self.state == PICK_PACK:
            self._handle_pack_pick(text)
        elif self.state == MENU:
            self._handle_menu(text)
        elif self.state == MENU_CATEGORY:
            self._handle_menu_category(text)
        elif text:
            self.emit("No test is running. Press Enter for the menu, or /help for commands.")
        else:
            self.cmd_menu("")
        return not self._quit

    def _dispatch(self, text: str) -> None:
        token, _, argument = text.partition(" ")
        name = token[1:]
        if not name:
            self.cmd_help("")
            return
        command = self.registry.find(name)
        if command is None:
            self.emit(f"Unknown command: {token}. Type /help for the list.")
            return
        getattr(self, command.handler_name)(argument.strip())

    # ------------------------------------------------------------- commands

    def cmd_menu(self, argument: str) -> None:
        from .commands import commands_by_category

        if self.state not in {IDLE, MENU, MENU_CATEGORY}:
            self.emit("Finish the current activity first — /pause leaves it safely.")
            return
        self._menu_categories = commands_by_category(self.registry.all())
        self._menu_group = []
        self.emit(render.menu_panel(self._menu_categories))
        self.state = MENU

    def _handle_menu(self, text: str) -> None:
        if not text:
            self.emit("Menu closed.")
            self.state = IDLE
            return
        if text.isdigit() and 1 <= int(text) <= len(self._menu_categories):
            category, group = self._menu_categories[int(text) - 1]
            self._menu_group = group
            self.emit(render.menu_category_panel(category, group))
            self.state = MENU_CATEGORY
            return
        self.emit(f"Type a number from 1 to {len(self._menu_categories)}, or press Enter to close.")

    def _handle_menu_category(self, text: str) -> None:
        if not text:
            self.cmd_menu("")
            return
        if text.isdigit() and 1 <= int(text) <= len(self._menu_group):
            command = self._menu_group[int(text) - 1]
            self.state = IDLE
            self._menu_group = []
            self.emit(ansi.style(f"→ /{command.name}", ansi.GREY))
            getattr(self, command.handler_name)("")
            return
        self.emit(f"Type a number from 1 to {len(self._menu_group)}, or press Enter to go back.")

    def cmd_help(self, argument: str) -> None:
        if argument:
            token = argument.split()[0].lstrip("/").lower()
            command = self.registry.find(token)
            if command is None:
                self.emit(f"Unknown command: /{token}. Bare /help lists everything.")
                return
            self.emit(render.command_help(command))
            return
        self.emit(render.help_table(self.registry.all()))

    def cmd_quit(self, argument: str) -> None:
        if self.session is not None and not self.session.is_completed:
            self.emit("Attempt progress is saved. /resume continues it next time.")
        self._quit = True

    def cmd_packs(self, argument: str) -> None:
        from ..stats import pack_progress

        argument = argument.strip()
        include_hidden = argument.lower() == "all"
        filter_text = "" if include_hidden else argument
        entries = latest_packs(self.library_dir, include_hidden=include_hidden)
        if not entries:
            self.emit("No packs imported. Run: topik-sim setup (or import-pack <pack.json>)")
            return
        matched = self._filter_pack_entries(entries, filter_text)
        if filter_text and not matched:
            self.emit(f"No pack matches {filter_text!r} — showing everything.")
            matched = entries
        progress = pack_progress(self.attempt_dir)

        self.emit(render.rule("Packs" + (f" · filter: {filter_text}" if filter_text and matched is not entries else "")))
        by_level: dict[str, list[dict[str, Any]]] = {}
        for entry in matched:
            by_level.setdefault(str(entry.get("topik_level", "OTHER")), []).append(entry)
        for level in sorted(by_level):
            self.emit(ansi.style(level.replace("_", " "), ansi.BOLD))
            for entry in by_level[level]:
                pack_id = str(entry.get("pack_id", ""))
                meta_parts = [f"v{entry.get('pack_version', '?')}"]
                if entry.get("difficulty"):
                    meta_parts.append(str(entry["difficulty"]))
                meta_parts.append(f"{entry.get('question_count', '?')} q")
                meta_parts.append(self._pack_progress_note(progress, pack_id))
                if entry.get("hidden"):
                    meta_parts.append("[hidden]")
                self.emit(
                    f"  {ansi.style(pack_id, ansi.CYAN)}  {entry.get('title', '')}"
                    f"  {ansi.style(' · '.join(meta_parts), ansi.GREY)}"
                )
        if not include_hidden:
            hidden_count = len(latest_packs(self.library_dir, include_hidden=True)) - len(entries)
            if hidden_count:
                self.emit(ansi.style(f"({hidden_count} hidden — /packs all shows them)", ansi.GREY))
        self.emit("Start one with /take <pack_id> · filter like /packs ii or /packs authentic")

    def cmd_attempts(self, argument: str) -> None:
        entries = self._refresh_recent()
        if not entries:
            self.emit(f"No saved attempts in {self.attempt_dir}.")
            return
        self.emit(render.rule("Recent attempts"))
        for index, (path, attempt) in enumerate(entries, start=1):
            self.emit(self._attempt_line(index, path, attempt))
        self.emit("Use /resume <n>, /drill <n>, or /report <n>.")

    def cmd_take(self, argument: str) -> None:
        self._end_minigames()
        if not argument:
            if not self._open_pack_picker("take"):
                self.emit("Usage: /take <pack_id[@version]|path> [section] [limit]")
                self.emit("No packs are imported yet: python -m topik_sim import-pack <pack.json>")
            return
        try:
            # posix=False keeps Windows path backslashes intact; quotes still group.
            parts = [part.strip('"') for part in shlex.split(argument, posix=False)]
        except ValueError as exc:
            self.emit(f"Could not parse arguments: {exc}")
            return
        ref = parts[0]
        section = None
        limit = None
        for extra in parts[1:]:
            if extra.isdigit():
                limit = int(extra)
            else:
                section = extra
        try:
            pack = self._resolve_pack(ref)
            self.session = ExamSession.start(pack, self.attempt_dir, section_id=section, limit=limit)
        except (ValueError, ContentValidationError, OSError) as exc:
            self.emit(str(exc))
            suggestions = self._suggest_packs(ref)
            if suggestions:
                self.emit(f"Did you mean: {', '.join(suggestions)}?")
            return
        _, total = self.session.progress()
        self.emit(ansi.style(pack.title, ansi.BOLD))
        self.emit(f"{total} question(s) · attempt {self.session.attempt['attempt_id']}")
        self._present()

    def cmd_resume(self, argument: str) -> None:
        located = self._locate_attempt(argument, action="resume")
        if located is None:
            return
        self._do_resume(*located)

    def _do_resume(self, path: Path, attempt: dict[str, Any]) -> None:
        if attempt.get("status") == "completed":
            self.emit("That attempt is already completed. /drill re-practices its missed questions.")
            return
        try:
            pack = self._resolve_pack_for_attempt(attempt)
            self.session = ExamSession.resume(path, pack)
        except (KeyError, ValueError, ContentValidationError, OSError) as exc:
            self.emit(str(exc))
            return
        answered, total = self.session.progress()
        self.emit(ansi.style(pack.title, ansi.BOLD))
        self.emit(f"Resuming: {answered}/{total} answered")
        self._present()

    def cmd_drill(self, argument: str) -> None:
        located = self._locate_attempt(argument, want_completed=True, action="drill")
        if located is None:
            return
        self._do_drill(*located)

    def _do_drill(self, path: Path, source: dict[str, Any]) -> None:
        try:
            pack = self._resolve_pack_for_attempt(source)
            attempt = create_drill_attempt(pack, source)
        except (KeyError, ValueError, ContentValidationError, OSError) as exc:
            self.emit(str(exc))
            return
        attempt_path = save_attempt_to_dir(attempt, self.attempt_dir)
        self.session = ExamSession(pack, attempt, attempt_path)
        self.emit(ansi.style(f"Drill: {pack.title}", ansi.BOLD))
        self.emit(f"{len(attempt['question_ids'])} missed question(s) from attempt {source.get('attempt_id', '?')}")
        self._present()

    def cmd_review(self, argument: str) -> None:
        from .. import srs

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
        queue = srs.load_queue(srs.queue_path_for(self.attempt_dir))
        if argument:
            pack_id = argument.split("@", 1)[0]
        else:
            counts = srs.due_counts_by_pack(queue)
            if not counts:
                self.emit("Nothing is due for review. 잘했어요!")
                return
            if len(counts) > 1:
                self.emit("Items are due in several packs — pick one:")
                for pack_id, count in sorted(counts.items()):
                    self.emit(f"  /review {pack_id} ({count} due)")
                return
            pack_id = next(iter(counts))
        try:
            pack = self._resolve_pack(pack_id)
            attempt = srs.create_review_attempt(pack, queue)
        except (ValueError, ContentValidationError, OSError) as exc:
            self.emit(str(exc))
            return
        attempt_path = save_attempt_to_dir(attempt, self.attempt_dir)
        self.session = ExamSession(pack, attempt, attempt_path)
        self.emit(ansi.style(f"Review: {pack.title}", ansi.BOLD))
        self.emit(f"{len(attempt['question_ids'])} item(s) due")
        self._present()

    def cmd_say(self, argument: str) -> None:
        if not argument and self.state in {FLASH_FRONT, FLASH_BACK} and self._flash_deck:
            speech = self._flash_deck[self._flash_index].get("speech", "")
            if speech:
                self._speak([speech], playback=True)
            else:
                self.emit("This card has nothing to speak.")
            return
        if not argument and self.state == TYPING and self._typing_items:
            self._speak([self._typing_items[self._typing_index]["speech"]], playback=True)
            return
        if not argument and self.state in {COMPOSE_TYPE, COMPOSE_GRADE} and self._compose_items:
            self._speak([self._compose_items[self._compose_index]["korean"]], playback=True)
            return
        if not argument and self.state in {DIALOGUE_TYPE, DIALOGUE_GRADE} and self._dialogue:
            self._speak([self._dialogue["turns"][self._dialogue_index].get("ko", "")], playback=True)
            return
        if not argument and self.state == IDLE and self._fact_speech:
            self._speak([self._fact_speech], playback=True)
            return
        if not argument:
            self.emit("Usage: /say <text> — pronounces the sentence without touching your answer.")
            return
        self._speak([argument], playback=True)

    def cmd_path(self, argument: str) -> None:
        """The staged study path: what to learn at which stage, with links."""
        from ..compose import DEFAULT_COMPOSE_PATH
        from ..curriculum import (
            DEFAULT_CURRICULUM_PATH, load_curriculum, resolve_units, unit_status,
        )
        from ..dialogues import DEFAULT_DIALOGUES_PATH

        units = load_curriculum(DEFAULT_CURRICULUM_PATH)
        if not units:
            self.emit("No study path found (content/curriculum).")
            return
        resolved = resolve_units(units, self.library_dir, self.courses_path,
                                 self.compose_path, DEFAULT_DIALOGUES_PATH)
        arg = argument.strip().lower()
        if arg:
            unit = next((u for u in resolved
                         if str(u.get("order")) == arg or str(u.get("id")).lower() == arg), None)
            if unit is None:
                self.emit(f"No unit {arg!r}. Bare /path lists all stages.")
                return
            self._show_path_unit(unit)
            return
        marks = {"done": ansi.style("✓", ansi.GREEN), "started": ansi.style("◐", ansi.CYAN),
                 "practiced": ansi.style("◐", ansi.CYAN), "new": "·"}
        self.emit(render.rule("Study path — TOPIK I"))
        current_level = None
        for unit in resolved:
            if unit.get("level") != current_level:
                current_level = unit.get("level")
                label = {0: "Start here", 1: "Level 1 · 1급", 2: "Level 2 · 2급"}.get(current_level, f"Level {current_level}")
                self.emit("")
                self.emit(ansi.style(label, ansi.BOLD))
            status = unit_status(unit, self.attempt_dir)
            mark = marks.get(status["state"], "·")
            progress = f"{status['lessons_done']}/{status['lessons_total']} lessons" if status["lessons_total"] else ""
            self.emit(f"  {mark} {ansi.style(str(unit.get('order')), ansi.BOLD, ansi.CYAN)}. "
                      f"{unit['title']}  {ansi.style(unit.get('title_ko', ''), ansi.DIM)}  "
                      f"{ansi.style(progress, ansi.GREY)}")
            self.emit(ansi.style(f"      {unit.get('scope', '')}", ansi.GREY))
        self.emit("")
        self.emit("/path <n> shows a stage's full scope and the commands that teach it.")

    def _show_path_unit(self, unit: dict[str, Any]) -> None:
        from ..curriculum import unit_status

        status = unit_status(unit, self.attempt_dir)
        self.emit(render.rule(f"Stage {unit.get('order')} · {unit['title']}"))
        self.emit(unit.get("scope", ""))
        for task in unit.get("tasks", []):
            self.emit(f"  • {task}")
        if unit.get("grammar"):
            self.emit(ansi.style("Grammar in scope: ", ansi.BOLD) + " · ".join(unit["grammar"]))
        if unit.get("vocab_domains"):
            self.emit(ansi.style("Vocabulary: ", ansi.BOLD) + ", ".join(unit["vocab_domains"]))
        self.emit("")
        self.emit(ansi.style("Learn and validate it:", ansi.BOLD))
        for course in unit.get("courses", []):
            self.emit(f"  /course {course['pack_id']}  → lesson {course['order']} ({course['title']})"
                      f"   · then /homework {course['pack_id']} {course['order']}")
        for structure in unit.get("compose_structures", []):
            self.emit(f"  /compose {structure['id']}   — write with {structure['pattern']}")
        for dialogue in unit.get("dialogues", []):
            self.emit(f"  /dialogue {dialogue}")
        for form in unit.get("conjugation", []):
            self.emit(f"  /conjugate {form['form']}   — {form['display']}")
        for drill in unit.get("drills", []):
            command = {"hangul": "/hangul", "sounds": "/sounds", "typing": "/typing"}.get(drill.get("mode"))
            if command is None:
                command = f"/{drill.get('mode')}" + (f" {drill.get('category')}" if drill.get("category") else "") \
                          + (f" {drill.get('form')}" if drill.get("form") else "")
            self.emit(f"  {command}   — {drill.get('label', '')}")
        words = unit.get("vocabulary", [])
        if words:
            unit_id = unit.get("id", "")
            self.emit(f"  /recall unit:{unit_id}   — type the Korean for this stage's {len(words)} words")
            self.emit(f"  /flashcards unit:{unit_id}   — flip through them")
        self.emit("  /vocab   — keep the stage's words on the spaced schedule")
        if words:
            self.emit("")
            self.emit(ansi.style(f"단어 · this stage's words ({len(words)})", ansi.BOLD))
            # The textbook's footer strip: pairs across the line, wrapped.
            line, width = [], 0
            for word in words:
                pair = f"{word['ko']} {ansi.style(word['en'], ansi.GREY)}"
                plain = len(word["ko"]) + len(word["en"]) + 1
                if width + plain > 74 and line:
                    self.emit("  " + "   ".join(line))
                    line, width = [], 0
                line.append(pair)
                width += plain + 3
            if line:
                self.emit("  " + "   ".join(line))
        progress = (f"{status['lessons_done']}/{status['lessons_total']} lessons · "
                    f"{status['homework_done']}/{status['lessons_total']} homework"
                    if status["lessons_total"] else ("practiced" if status["practiced"] else "not started"))
        self.emit("")
        self.emit(ansi.style(f"Progress: {progress}", ansi.GREY))

    def cmd_hangul(self, argument: str) -> None:
        """Read Hangul from zero: jamo sounds, block composition, batchim."""
        from ..hangul_guide import guide

        data = guide()
        self.emit(render.rule("Read Hangul — 한글 읽기"))
        self.emit(data["how_blocks_work"])
        self.emit("")
        self.emit(ansi.style("Consonants", ansi.BOLD))
        for row in data["consonants"]:
            self.emit(f"  {row['jamo']}  {row['name']:<16} {row['sound']}")
        self.emit(ansi.style("Tense consonants", ansi.BOLD))
        for row in data["tense_consonants"]:
            self.emit(f"  {row['jamo']}  {row['name']:<16} {row['sound']}")
        self.emit(ansi.style("Vowels", ansi.BOLD))
        for row in data["vowels"]:
            self.emit(f"  {row['jamo']}  {row['sound']}")
        self.emit(ansi.style("Compound vowels", ansi.BOLD))
        self.emit("  " + " · ".join(f"{row['jamo']} {row['sound']}" for row in data["compound_vowels"]))
        self.emit("")
        self.emit(ansi.style("Sounding out blocks", ansi.BOLD))
        for example in data["walkthroughs"]:
            self.emit(f"  {example['word']}  =  {example['parts']}  →  {example['reading']}")
            self.emit(ansi.style(f"     {example['note']}", ansi.GREY))
        self.emit("")
        self.emit(data["batchim"])
        self.emit(ansi.style(data["romanization"], ansi.DIM))
        self.emit("")
        grid = data["syllable_grid"]
        self.emit(ansi.style("Reading practice — say each block aloud:", ansi.BOLD))
        self.emit("     " + "  ".join(grid["vowels"]))
        for lead, row in zip([r["jamo"] for r in data["consonants"]], grid["rows"]):
            self.emit(f"  {lead}  " + "  ".join(row))
        self.emit("")
        self.emit("Next: /say 안녕하세요 hears any text · /typing drills the keyboard · /keyboard shows where keys are.")

    def cmd_sounds(self, argument: str) -> None:
        """Korean sound-change rules — reference, or a spelled→spoken drill."""
        from ..pronunciation import RULES, build_pronunciation_items, guide

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        arg = argument.strip().lower()
        rule_ids = {r["id"] for r in RULES}
        # Bare or "list": show the reference. "drill [rule] [count]": practice.
        if arg in {"", "list", "rules"}:
            data = guide()
            self.emit(render.rule("Korean sound changes — 발음 규칙"))
            self.emit(data["intro"])
            for r in data["rules"]:
                self.emit("")
                self.emit(ansi.style(r["name"], ansi.BOLD, ansi.CYAN))
                self.emit(f"  {r['explain']}")
                for ex in r["examples"]:
                    self.emit(f"    {ex['written']} → {ansi.style('[' + ex['spoken'] + ']', ansi.GREY)}  {ex['gloss']}")
            self.emit("")
            self.emit("Practice: /sounds drill · /sounds drill gyeongeum · /say reads any word aloud.")
            return
        self._end_minigames()
        parts = arg.split()
        rule_id = next((p for p in parts if p in rule_ids), None)
        count = next((int(p) for p in parts if p.isdigit()), 10)
        items = build_pronunciation_items(seed=self._flashcard_seed, count=count, rule_id=rule_id)
        self._start_typing(
            items, label="Pronunciation", verb="Read", title="Type how each word is pronounced:",
            hint="write the spoken form in Hangul · /say hears it after grading · /pause stops",
        )

    def cmd_lookup(self, argument: str) -> None:
        """Search everything the packs teach — the 'what was that word?' command."""
        from ..lookup import search_library

        query = argument.strip()
        if not query:
            self.emit("Usage: /lookup <Korean or English> — searches every imported pack's vocabulary and grammar.")
            return
        results = search_library(query, self.library_dir)
        vocabulary = results["vocabulary"]
        grammar = results["grammar"]
        if not vocabulary and not grammar:
            self.emit(f"Nothing taught in your packs matches {query!r}.")
            return
        self.emit(render.rule(f"Lookup · {query}"))
        for card in vocabulary:
            note = f" — {card['note']}" if card.get("note") else ""
            source = ansi.style(f"({card['pack_id']})", ansi.GREY)
            self.emit(f"  {ansi.style(card['ko'], ansi.BOLD)}  {card['en']}{note}  {source}")
        for point in grammar:
            source = ansi.style(f"({point['pack_id']})", ansi.GREY)
            self.emit(f"  {ansi.style(point['pattern'], ansi.BOLD, ansi.CYAN)}  {point['explanation']}  {source}")
            if point.get("example"):
                self.emit(ansi.style(f"     예: {point['example']}", ansi.GREY))
        self.emit("Bare /say speaks nothing here — use /say <text> to hear any of these aloud.")

    def cmd_keyboard(self, argument: str) -> None:
        key = argument.strip().lower()
        if key == "on":
            self.keyboard_hints = True
            self.keyboard_pinned = True
            self.emit(
                "Keyboard mode on: the layout is pinned to the toolbar and typing keys"
                " are shown in dictation, flashcards, and /typing. /keyboard unpin frees the space."
            )
            return
        if key == "off":
            self.keyboard_hints = False
            self.keyboard_pinned = False
            self.emit("Keyboard mode off.")
            return
        if key == "pin":
            self.keyboard_pinned = True
            self.emit("Keyboard layout pinned to the toolbar.")
            return
        if key == "unpin":
            self.keyboard_pinned = False
            self.emit("Keyboard layout unpinned.")
            return
        if key:
            self.emit("Usage: /keyboard [on|off|pin|unpin]")
            return
        self.emit(render.keyboard_chart())

    def cmd_typing(self, argument: str) -> None:
        from ..typing_drill import build_advanced_typing_items, build_typing_items

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
        advanced = False
        pack = None
        count = 12
        for part in argument.split():
            if part.lower() in {"advanced", "adv", "pro"}:
                advanced = True
            elif part.isdigit():
                count = int(part)
            else:
                try:
                    pack = self._resolve_pack(part)
                except (ValueError, ContentValidationError, OSError) as exc:
                    self.emit(str(exc))
                    suggestions = self._suggest_packs(part)
                    if suggestions:
                        self.emit(f"Did you mean: {', '.join(suggestions)}?")
                    return
        if advanced:
            items = build_advanced_typing_items(
                pack=pack,
                library_dir=None if pack else self.library_dir,
                compose_path=self.compose_path,
                count=count,
                seed=self._flashcard_seed,
            )
            if not items:
                self.emit("No words or sentences available for advanced typing. Import a pack, or check content/compose.")
                return
            title = f"Advanced typing: {pack.title}" if pack else "Advanced typing"
            self._start_typing(items, label="Advanced typing", verb="Typed", title=title,
                               hint="type the Korean word or sentence · the meaning follows · /pause stops")
            return
        targets = build_typing_items(
            seed=self._flashcard_seed,
            pack=pack,
            count=count,
            library_dir=None if pack else self.library_dir,
        )
        meanings = self._typing_meanings(pack)
        items = []
        for target in targets:
            item = {"show": target, "accept": [target], "answer": target, "speech": target}
            if target in meanings:
                item["meaning"] = meanings[target]
            items.append(item)
        title = f"Typing practice: {pack.title}" if pack else "Typing practice"
        self._start_typing(items, label="Typing practice", verb="Typed", title=title,
                           hint="type what you see · /keyboard shows the layout · /pause stops")

    def cmd_numbers(self, argument: str) -> None:
        from ..numbers import NUMBER_CATEGORIES, build_number_items

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
        category = None
        count = 10
        for part in argument.split():
            if part.lower() in {"learn", "guide", "table", "tables"}:
                self._show_numbers_guide()
                return
            if part.isdigit():
                count = int(part)
            elif part.lower() in {"mix", "mixed", "all"}:
                category = "mix"
            elif part.lower() in NUMBER_CATEGORIES:
                category = part.lower()
            else:
                self.emit(
                    f"Unknown category: {part}. Choose from {', '.join(NUMBER_CATEGORIES)}, mix, or learn."
                )
                return
        items = build_number_items(seed=self._flashcard_seed, count=count, category=category)
        scope = "mixed" if category in (None, "mix") else category
        self._start_typing(
            items, label="Number practice", verb="Read", title=f"Number practice: {scope}",
            hint="write the number in Korean letters — no digits · new to the systems? /pause then"
                 " /numbers learn · /say reads it",
        )

    def cmd_colors(self, argument: str) -> None:
        from ..colors import COLOR_CATEGORIES, build_color_items

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
        category = None
        count = 10
        for part in argument.split():
            if part.lower() in {"learn", "guide", "table", "tables", "chart"}:
                self._show_colors_guide()
                return
            if part.isdigit():
                count = int(part)
            elif part.lower() in {"mix", "mixed", "all"}:
                category = "mix"
            elif part.lower() in COLOR_CATEGORIES:
                category = part.lower()
            else:
                self.emit(
                    f"Unknown category: {part}. Choose from {', '.join(COLOR_CATEGORIES)}, mix, or learn."
                )
                return
        items = build_color_items(seed=self._flashcard_seed, count=count, category=category)
        scope = "mixed" if category in (None, "mix") else category
        self._start_typing(
            items, label="Color practice", verb="Named", title=f"Color practice: {scope}",
            hint="name the color in Korean (한글) · new to color words? /pause then"
                 " /colors learn · /say reads it",
        )

    def _show_colors_guide(self) -> None:
        """Color words as a table — the 색 noun, the modifier, the Sino form."""
        from ..colors import cheat_sheet

        sheet = cheat_sheet()
        self.emit(render.rule("Korean colors"))
        for row in sheet["colors"]:
            block = ansi.swatch(row["hex"], width=4)
            swatch_cell = f"{block} " if block else ""
            extras = []
            if row["modifier"]:
                extras.append(f"before a noun: {row['modifier']}")
            if row["sino"]:
                extras.append(f"한자어 {row['sino']}")
            if row["also"]:
                extras.append("also " + ", ".join(row["also"]))
            tail = ansi.style(f"  ({' · '.join(extras)})", ansi.GREY) if extras else ""
            self.emit(f"  {swatch_cell}{row['ko']:<8} {row['en']:<14}{tail}")
        self.emit("")
        self.emit(ansi.style("ㅎ-irregular adjectives — the ㅎ drops before -ㄴ", ansi.BOLD))
        self.emit("  " + " · ".join(f"{row['adjective']} → {row['modifier']}" for row in sheet["irregulars"]))
        self.emit("")
        self.emit(ansi.style("How to use them", ansi.BOLD))
        for row in sheet["usage"]:
            self.emit(f"  {row['context']:<28} {ansi.style(row['example'], ansi.CYAN)}  {ansi.style(row['note'], ansi.GREY)}")
        self.emit("")
        self.emit("Practice it: /colors · /colors swatch · /colors modifier · /conjugate irregular drills 빨갛다.")

    def _show_numbers_guide(self) -> None:
        """The two number systems as tables — learn before being drilled."""
        from ..numbers import cheat_sheet

        sheet = cheat_sheet()
        self.emit(render.rule("Korean numbers — the two systems"))
        self.emit(ansi.style("Sino-Korean (일 이 삼 …) — dates, money, minutes, phone, floors, math", ansi.BOLD))
        self.emit("  " + " · ".join(f"{row['n']} {row['reading']}" for row in sheet["sino"][:10]))
        self.emit("  " + " · ".join(f"{row['n']:,} {row['reading']}" for row in sheet["sino"][10:]))
        self.emit("")
        self.emit(ansi.style("Native Korean (하나 둘 셋 …) — counting things, age, the hour (1–99 only)", ansi.BOLD))
        self.emit("  " + " · ".join(f"{row['n']} {row['reading']}" for row in sheet["native"]))
        counter_forms = [f"{row['reading']} → {row['counter_form']}" for row in sheet["native"] if row.get("counter_form")]
        self.emit(f"  Before a counter, short forms: {' · '.join(counter_forms)}")
        self.emit("")
        self.emit(ansi.style("Common counters", ansi.BOLD))
        self.emit("  " + " · ".join(f"{row['counter']} {row['meaning']}" for row in sheet["counters"]))
        self.emit("")
        self.emit(ansi.style("Which system?", ansi.BOLD))
        for row in sheet["usage"]:
            self.emit(f"  {row['context']:<32} {ansi.style(row['system'], ansi.CYAN)}  {ansi.style(row['example'], ansi.GREY)}")
        self.emit("")
        self.emit("Practice it: /numbers · /numbers count · /numbers date · /say 삼백사십칠 hears any reading.")

    # Friendly words the learner can type → conjugation form keys.
    _CONJUGATE_ALIASES = {
        "mix": "mix", "mixed": "mix", "random": "mix", "all": "mix",
        "polite": "aeo", "informal": "aeo", "해요": "aeo", "aeo": "aeo",
        "formal": "seumnida", "습니다": "seumnida", "seumnida": "seumnida", "seum": "seumnida",
        "past": "past", "past-formal": "past_formal", "pastformal": "past_formal",
        "future": "future", "will": "future", "can": "can", "if": "if", "because": "because",
        "so": "so", "must": "must", "honorific": "honorific", "please": "honorific",
        "want": "want", "not": "not", "negation": "not",
    }

    def cmd_conjugate(self, argument: str) -> None:
        """Conjugate dictionary-form verbs into a chosen ending."""
        from ..conjugation import DRILL_FORMS, build_conjugation_items

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
        pack = None
        count = 12
        form_key = "mix"  # interleaved endings by default; name a form to focus
        valid = {spec["key"] for spec in DRILL_FORMS}
        for part in argument.split():
            low = part.lower()
            if part.isdigit():
                count = int(part)
            elif low == "list":
                self.emit("Forms: mix = every ending, interleaved · "
                          + " · ".join(f"{s['key']} = {s['display']}" for s in DRILL_FORMS))
                return
            elif low in self._CONJUGATE_ALIASES:
                form_key = self._CONJUGATE_ALIASES[low]
            elif low in valid:
                form_key = low
            else:
                try:
                    pack = self._resolve_pack(part)
                except (ValueError, ContentValidationError, OSError) as exc:
                    self.emit(str(exc))
                    return
        items = build_conjugation_items(
            pack=pack, library_dir=None if pack else self.library_dir,
            seed=self._flashcard_seed, count=count, form_key=form_key,
        )
        if not items:
            self.emit("No conjugatable verbs found. Import a pack, or name one: /conjugate <pack>")
            return
        display = ("mixed endings (each verb a different one)" if form_key == "mix"
                   else next(s["display"] for s in DRILL_FORMS if s["key"] == form_key))
        self._start_typing(
            items, label="Conjugation", verb="Conjugated",
            title=f"Conjugate to {display}:",
            hint="type the conjugated form · /conjugate list shows all forms · /pause stops",
        )

    def _pack_glosses(self, pack) -> dict[str, str]:
        """One pack's vocabulary: what it teaches, plus what was mined from it."""
        from ..flashcards import gloss_map, wordlist_deck

        glosses = dict(gloss_map(pack=pack))
        for card in wordlist_deck(self.library_dir, pack.pack_id):
            glosses.setdefault(card["ko"], card["en"])
        return glosses

    def cmd_vocab(self, argument: str) -> None:
        """Spaced vocabulary review — due words plus a few new ones each session."""
        from .. import vocab_srs
        from ..flashcards import gloss_map

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
        count, scope = 15, ""
        for part in argument.split():
            if part.isdigit():
                count = int(part)
            else:
                scope = part
        if scope:  # /vocab <pack> — review just that exam's words
            try:
                pack = self._resolve_pack(scope)
            except (ValueError, ContentValidationError, OSError) as exc:
                self.emit(str(exc))
                suggestions = self._suggest_packs(scope)
                if suggestions:
                    self.emit(f"Did you mean: {', '.join(suggestions)}?")
                return
            glosses = self._pack_glosses(pack)
            if not glosses:
                self.emit(f"No vocabulary recorded for {pack.pack_id}.")
                return
        else:
            glosses = gloss_map(library_dir=self.library_dir)
        if not glosses:
            self.emit("No vocabulary found. Import a pack first (topik-sim setup).")
            return
        deck = vocab_srs.load_deck(self.attempt_dir)
        session = vocab_srs.build_session(deck, glosses, count=count)
        if not session:
            summary = vocab_srs.summary(deck)
            self.emit(f"Nothing due right now — {summary['learning']} words in review, "
                      f"{summary['mastered']} mastered. Come back later, or study a pack's flashcards.")
            return
        items = [{
            "show": f"Type the Korean:  {c['en']}",
            "accept": [c["ko"]], "answer": c["ko"], "speech": c["ko"],
            "meaning": f"{c['ko']} — {c['en']}", "srs_key": c["ko"], "srs_en": c["en"],
        } for c in session]
        self._vocab_deck = deck
        self._typing_srs = True
        new_count = sum(1 for c in session if c.get("new"))
        self.emit(ansi.style(f"Spaced vocabulary review · {len(session) - new_count} due, {new_count} new", ansi.BOLD))
        self._start_typing(
            items, label="Vocabulary review", verb="Reviewed", title="See the meaning, type the Korean:",
            hint="each answer reschedules the word · /say hears it after grading · /pause stops",
        )

    def cmd_misses(self, argument: str) -> None:
        """Drill the weak list — the same items the web's misses mode uses."""
        from ..practice_log import build_misses_items

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
        count = int(argument) if argument.strip().isdigit() else 10
        items = build_misses_items(self.attempt_dir, self.library_dir, limit=count)
        if not items:
            self.emit("No missed items recorded yet — practice first (/recall, /typing, /numbers, /homework).")
            return
        self._start_typing(
            items, label="Weak items", verb="Cleared", title="Drill your weak items:",
            hint="type the answer · /say hears it after grading · /pause stops",
        )

    def cmd_recall(self, argument: str) -> None:
        from ..flashcards import build_recall_items

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
        pack = None
        unit = ""
        count = 10
        for part in argument.split():
            if part.isdigit():
                count = int(part)
            elif part.lower().startswith("unit:"):
                unit = part.split(":", 1)[1]
            else:
                try:
                    pack = self._resolve_pack(part)
                except (ValueError, ContentValidationError, OSError) as exc:
                    self.emit(str(exc))
                    suggestions = self._suggest_packs(part)
                    if suggestions:
                        self.emit(f"Did you mean: {', '.join(suggestions)}?")
                    return
        if unit:  # a study-path stage's own words
            from ..flashcards import recall_items_from_cards, wordlist_deck

            cards = wordlist_deck(self.library_dir, unit=unit)
            if not cards:
                self.emit(f"No vocabulary for unit {unit!r}. /path lists the stages.")
                return
            items = recall_items_from_cards(cards, seed=self._flashcard_seed, count=count)
            self._start_typing(items, label="Vocab recall", verb="Recalled",
                               title=f"Vocab recall: {unit}",
                               hint="type the Korean for each English word · /pause stops")
            return
        items = build_recall_items(
            pack=pack,
            library_dir=self.library_dir,
            seed=self._flashcard_seed,
            count=count,
        )
        if not items:
            self.emit("No vocabulary found. Import a pack first, or name one: /recall <pack>")
            return
        title = f"Vocab recall: {pack.title}" if pack else "Vocab recall: every imported pack"
        self._start_typing(items, label="Vocab recall", verb="Recalled", title=title,
                           hint="type the Korean for each English word · /pause stops")

    def _typing_meanings(self, pack: ExamPack | None) -> dict[str, str]:
        """Map each pack vocabulary word to its gloss, for reveal after typing.

        Words the typing drill invents (jamo, syllables, random fallback pairs)
        are not in this map, so only real pack vocabulary shows a meaning.
        """
        from ..flashcards import gloss_map

        return gloss_map(pack=pack, library_dir=None if pack else self.library_dir)

    def _start_typing(self, items: list[dict[str, Any]], label: str, verb: str, title: str, hint: str) -> None:
        self._typing_items = items
        self._typing_index = 0
        self._typing_hits = 0
        self._typing_missed = []
        self._typing_label = label
        self._typing_verb = verb
        self.emit(ansi.style(title, ansi.BOLD))
        self.emit(f"{len(items)} item(s) · {hint}")
        self._present_typing()

    def _present_typing(self) -> None:
        item = self._typing_items[self._typing_index]
        self.emit("")
        self.emit(render.rule(f"{self._typing_label} {self._typing_index + 1}/{len(self._typing_items)}"))
        self.emit(ansi.style(item["show"], ansi.BOLD, ansi.CYAN))
        if item.get("swatch"):
            block = ansi.swatch(item["swatch"])
            if block:
                self.emit(f"  {block}  {ansi.style(item['swatch'], ansi.GREY)}")
            elif item.get("swatch_only") and item.get("meaning"):
                # No terminal color: name the color, or the item is unanswerable.
                self.emit(f"  ({item['meaning']})")
        self.state = TYPING

    def _grade_typing(self, typed: str) -> None:
        from ..hangul import keystroke_hint
        from ..typing_drill import normalize_typed

        item = self._typing_items[self._typing_index]
        if item.get("no_digits") and any(ch.isdigit() for ch in typed):
            self.emit("Write the number in Korean letters (한글), not digits. Try again.")
            return
        if item.get("no_latin") and any("a" <= ch.lower() <= "z" for ch in typed):
            self.emit("Write the answer in Korean letters (한글), not English. Try again.")
            return
        # Number phrases are spaced (세 시 십오 분); grade them space-insensitively.
        def _key(text: str) -> str:
            return normalize_typed(text).replace(" ", "")
        accepted = {_key(answer) for answer in item["accept"]}
        correct = _key(typed) in accepted
        if correct:
            self._typing_hits += 1
            self.emit(ansi.style("✓", ansi.BOLD, ansi.GREEN))
        else:
            self._typing_missed.append(item.get("miss_key") or item["answer"])
            expected = item.get("reveal") or " / ".join(item["accept"])
            line = ansi.style(f"✗ {expected}", ansi.BOLD, ansi.RED)
            if not item.get("options"):
                line += f" — {keystroke_hint(item['answer'])}"
            self.emit(line)
        if self._typing_srs and item.get("srs_key") and self._vocab_deck is not None:
            from .. import vocab_srs

            vocab_srs.record(self._vocab_deck, item["srs_key"], item.get("srs_en", ""), correct)
            vocab_srs.save_deck(self._vocab_deck, self.attempt_dir)
        meaning = item.get("meaning")
        if meaning:
            self.emit(ansi.style(f"  {meaning}", ansi.GREY))
        self._typing_index += 1
        if self._typing_index >= len(self._typing_items):
            self._end_typing()
        else:
            self._present_typing()

    def _end_typing(self, early: bool = False) -> None:
        from ..hangul import keystrokes

        done = self._typing_index
        if early:
            self.emit(f"{self._typing_label} stopped after {done}/{len(self._typing_items)} item(s).")
        if done:
            self.emit(f"{self._typing_verb} {self._typing_hits}/{done} correctly.")
        if self._typing_missed:
            review = " · ".join(f"{item} ({keystrokes(item)})" for item in dict.fromkeys(self._typing_missed))
            self.emit(f"Practice again: {review}")
        homework = self._typing_homework
        self._typing_homework = None
        if homework is not None and done and not early:
            from ..homework import record_homework

            pack_id, course_id = homework
            entry = record_homework(self.attempt_dir, pack_id, course_id, self._typing_hits, done)
            self.emit(
                f"Homework saved: {self._typing_hits}/{done}"
                f" · best {entry.get('best_correct', 0)}/{entry.get('best_total', 0)}"
                f" · run {entry.get('runs', 1)}"
            )
        if done:
            from ..practice_log import record_practice

            record_practice(
                self.attempt_dir,
                mode=TYPING_LABEL_MODES.get(self._typing_label, self._typing_label.lower()),
                label=self._typing_label,
                hits=self._typing_hits,
                total=done,
                missed=list(self._typing_missed),
                pack_id=homework[0] if homework else None,
            )
        if self._typing_srs and self._vocab_deck is not None:
            from .. import vocab_srs

            self.emit(f"Scheduled · {vocab_srs.due_count(self._vocab_deck)} still due · "
                      f"{vocab_srs.summary(self._vocab_deck)['learning']} words in review.")
        self._typing_srs = False
        self._vocab_deck = None
        self._typing_items = []
        self._typing_index = 0
        self._typing_hits = 0
        self._typing_missed = []
        self.state = IDLE

    def cmd_compose(self, argument: str) -> None:
        from ..compose import filter_lessons, load_lessons

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
        if self._lessons is None:
            self._lessons = load_lessons(self.compose_path)
        if not self._lessons:
            self.emit(f"No writing lessons are available (looked in {self.compose_path}).")
            return

        argument = argument.strip()
        if argument.lower() in {"random", "r"}:
            self._start_lesson(self._compose_rng.choice(self._lessons))
            return
        if not argument:
            self._open_lesson_picker(self._lessons)
            return
        if argument.isdigit() and 1 <= int(argument) <= len(self._lessons):
            self._start_lesson(self._lessons[int(argument) - 1])
            return
        matches = filter_lessons(self._lessons, argument)
        if len(matches) == 1:
            self._start_lesson(matches[0])
        elif matches:
            self._open_lesson_picker(matches)
        else:
            self.emit(f"No structure matches {argument!r}.")
            self._open_lesson_picker(self._lessons)

    def _open_lesson_picker(self, lessons: list[dict[str, Any]]) -> None:
        self._lesson_pick = lessons
        self.emit(render.rule("Compose — pick a structure to practice"))
        for index, lesson in enumerate(lessons, start=1):
            meaning = str(lesson.get("meaning", ""))
            n = len(lesson.get("sentences", []))
            self.emit(
                f"  {ansi.style(str(index), ansi.BOLD, ansi.CYAN)}. {ansi.style(str(lesson.get('pattern', '')), ansi.CYAN)}"
                f"  {ansi.style(f'{meaning} · {n} sentences', ansi.GREY)}"
            )
        self.emit("Type a number, r for a random one, or press Enter to cancel.")
        self.state = COMPOSE_PICK

    def _handle_lesson_pick(self, text: str) -> None:
        if not text:
            self.emit("Cancelled.")
            self._lesson_pick = []
            self.state = IDLE
            return
        if text.lower() in {"r", "random"}:
            lesson = self._compose_rng.choice(self._lesson_pick)
            self._lesson_pick = []
            self._start_lesson(lesson)
            return
        if text.isdigit() and 1 <= int(text) <= len(self._lesson_pick):
            lesson = self._lesson_pick[int(text) - 1]
            self._lesson_pick = []
            self._start_lesson(lesson)
            return
        self.emit(f"Type a number from 1 to {len(self._lesson_pick)}, r for random, or press Enter to cancel.")

    def _start_lesson(self, lesson: dict[str, Any]) -> None:
        from ..compose import collect_pack_grammar, drill_order, lesson_pack_evidence

        if self._pack_grammar is None:
            self._pack_grammar = collect_pack_grammar(self.library_dir)
        evidence = lesson_pack_evidence(lesson, self._pack_grammar)
        self.emit("")
        self.emit(render.compose_lesson_card(lesson, evidence))
        self.emit(ansi.style("Type the Korean · /say reveals it aloud · /pause stops", ansi.GREY))
        self._compose_items = drill_order(lesson, seed=self._flashcard_seed)
        self._compose_index = 0
        self._compose_hits = 0
        self._compose_missed = []
        self._present_compose()

    def _present_compose(self) -> None:
        item = self._compose_items[self._compose_index]
        self.emit("")
        self.emit(render.rule(f"Translate {self._compose_index + 1}/{len(self._compose_items)}"))
        self.emit(ansi.style(item["english"], ansi.BOLD, ansi.CYAN))
        self.state = COMPOSE_TYPE

    def _grade_compose(self, typed: str) -> None:
        from ..compose import accepted_answers, is_correct

        item = self._compose_items[self._compose_index]
        model = str(item.get("korean", ""))
        if is_correct(item, typed):
            self._compose_hits += 1
            self.emit(ansi.style(f"✓ {model}", ansi.BOLD, ansi.GREEN))
            self._compose_feedback(item)
            self._advance_compose()
            return
        # Free Korean can't be auto-graded — reveal the model and let the
        # learner self-judge whether their sentence was right.
        self.emit(ansi.style(f"Model: {model}", ansi.CYAN))
        others = [a for a in accepted_answers(item) if a != model]
        if others:
            self.emit(ansi.style("Also fine: " + " / ".join(others), ansi.DIM))
        self._compose_feedback(item)
        self.emit(ansi.style("Was your sentence right? y / n", ansi.GREY))
        self.state = COMPOSE_GRADE

    def _compose_feedback(self, item: dict[str, Any]) -> None:
        note = str(item.get("note", "")).strip()
        if note:
            self.emit(render.inline_markdown(note))

    def _selfgrade_compose(self, correct: bool) -> None:
        if correct:
            self._compose_hits += 1
        else:
            self._compose_missed.append(self._compose_items[self._compose_index])
        self._advance_compose()

    def _advance_compose(self) -> None:
        self._compose_index += 1
        if self._compose_index >= len(self._compose_items):
            self._end_compose()
        else:
            self._present_compose()

    def _end_compose(self, early: bool = False) -> None:
        done = self._compose_index
        if early:
            self.emit(f"Translation practice stopped after {done}/{len(self._compose_items)} sentence(s).")
        if done:
            self.emit(f"Correct {self._compose_hits}/{done}.")
        if self._compose_missed:
            review = " · ".join(
                f"{item['english']} → {item.get('korean', '')}"
                for item in self._compose_missed
            )
            self.emit(f"Review again: {review}")
        self._compose_items = []
        self._compose_index = 0
        self._compose_hits = 0
        self._compose_missed = []
        self.state = IDLE

    # ------------------------------------------------------------- dialogues

    def cmd_dialogue(self, argument: str) -> None:
        """Situational conversation: partner lines play, you produce yours."""
        from ..dialogues import find_dialogue, load_dialogues

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
        dialogues = load_dialogues(self.dialogues_path)
        if not dialogues:
            self.emit(f"No conversations found (looked in {self.dialogues_path}).")
            return
        arg = argument.strip()
        if arg:
            dialogue = find_dialogue(arg, self.dialogues_path)
            if dialogue is None:
                self.emit(f"No conversation '{arg}'. Bare /dialogue lists them.")
                return
            self._start_dialogue(dialogue)
            return
        self._dialogue_pick = dialogues
        self.emit(render.rule("Pick a conversation"))
        for index, dialogue in enumerate(dialogues, start=1):
            level = f"TOPIK {dialogue.get('level')}" if dialogue.get("level") else ""
            ko = dialogue.get("title_ko", "")
            self.emit(f"  {ansi.style(str(index), ansi.BOLD, ansi.CYAN)}. {dialogue['title']}"
                      f"  {ansi.style(ko, ansi.DIM)}  {ansi.style(level, ansi.GREY)}")
            self.emit(ansi.style(f"     {dialogue.get('situation', '')}", ansi.GREY))
        self.emit("Type a number, or press Enter to cancel.")
        self.state = DIALOGUE_PICK

    def _handle_dialogue_pick(self, text: str) -> None:
        if not text:
            self.emit("Cancelled.")
            self._dialogue_pick = []
            self.state = IDLE
            return
        if text.isdigit() and 1 <= int(text) <= len(self._dialogue_pick):
            dialogue = self._dialogue_pick[int(text) - 1]
            self._dialogue_pick = []
            self._start_dialogue(dialogue)
            return
        self.emit(f"Type a number from 1 to {len(self._dialogue_pick)}, or press Enter to cancel.")

    def _start_dialogue(self, dialogue: dict[str, Any]) -> None:
        from ..dialogues import is_learner_turn

        self._dialogue = dialogue
        self._dialogue_index = 0
        self._dialogue_hits = 0
        self._dialogue_total = sum(1 for turn in dialogue["turns"] if is_learner_turn(turn))
        self.emit("")
        self.emit(render.rule(dialogue.get("title", "Conversation")))
        self.emit(dialogue.get("situation", ""))
        self.emit(ansi.style("On your turns, type the Korean for the intent shown. "
                             "/say hears the model line · /pause stops.", ansi.GREY))
        self._present_dialogue()

    def _present_dialogue(self) -> None:
        from ..dialogues import is_learner_turn

        turns = self._dialogue["turns"]
        while self._dialogue_index < len(turns):
            turn = turns[self._dialogue_index]
            if is_learner_turn(turn):
                self.emit("")
                self.emit(ansi.style(f"{turn.get('speaker', '나')} — your line:", ansi.BOLD))
                self.emit(ansi.style(f"  → {turn['en']}", ansi.CYAN))
                self.state = DIALOGUE_TYPE
                return
            self.emit("")
            self.emit(f"{ansi.style(turn.get('speaker', ''), ansi.BOLD)}:  {turn.get('ko', '')}")
            self.emit(ansi.style(f"   {turn.get('en', '')}", ansi.GREY))
            if self.audio_enabled and turn.get("ko"):
                self._speak([turn["ko"]], playback=True)
            self._dialogue_index += 1
        self._end_dialogue()

    def _grade_dialogue(self, typed: str) -> None:
        from ..dialogues import accepted_answers, is_correct

        turn = self._dialogue["turns"][self._dialogue_index]
        model = str(turn.get("ko", ""))
        if is_correct(turn, typed):
            self._dialogue_hits += 1
            self.emit(ansi.style(f"✓ {model}", ansi.BOLD, ansi.GREEN))
            self._dialogue_index += 1
            self._present_dialogue()
            return
        self.emit(ansi.style(f"Model: {model}", ansi.CYAN))
        others = [a for a in accepted_answers(turn) if a != model]
        if others:
            self.emit(ansi.style("Also fine: " + " / ".join(others), ansi.DIM))
        self.emit(ansi.style("Was your line right? y / n", ansi.GREY))
        self.state = DIALOGUE_GRADE

    def _selfgrade_dialogue(self, correct: bool) -> None:
        if correct:
            self._dialogue_hits += 1
        self._dialogue_index += 1
        self._present_dialogue()

    def _end_dialogue(self, early: bool = False) -> None:
        if early:
            self.emit("Left the conversation.")
        elif self._dialogue_total:
            self.emit("")
            self.emit(f"Conversation complete · you produced {self._dialogue_hits}/{self._dialogue_total} lines correctly.")
            from ..practice_log import record_practice

            record_practice(self.attempt_dir, mode="dialogue", label="Conversation",
                            hits=self._dialogue_hits, total=self._dialogue_total)
        self._dialogue = None
        self._dialogue_index = 0
        self._dialogue_hits = 0
        self._dialogue_total = 0
        self.state = IDLE

    def _end_minigames(self) -> None:
        if self._course is not None:
            self._leave_course()
            return
        if self.state == COURSE_PICK:
            self._course_list = []
            self.state = IDLE
        elif self.state == HOMEWORK_PICK:
            self._homework_courses = []
            self._homework_pack = None
            self.state = IDLE
        elif self.state in {FLASH_FRONT, FLASH_BACK}:
            self._end_flashcards(early=True)
        elif self.state == DICTATION:
            self._end_dictation(early=True)
        elif self.state == TYPING:
            self._end_typing(early=True)
        elif self.state in {COMPOSE_TYPE, COMPOSE_GRADE}:
            self._end_compose(early=True)
        elif self.state == COMPOSE_PICK:
            self._lesson_pick = []
            self.state = IDLE
        elif self.state in {DIALOGUE_TYPE, DIALOGUE_GRADE}:
            self._end_dialogue(early=True)
        elif self.state == DIALOGUE_PICK:
            self._dialogue_pick = []
            self.state = IDLE

    def cmd_flashcards(self, argument: str) -> None:
        from ..flashcards import build_deck

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
        if argument.strip().lower().startswith("unit:"):
            from ..flashcards import wordlist_deck

            unit = argument.strip().split(":", 1)[1]
            cards = wordlist_deck(self.library_dir, unit=unit)
            if not cards:
                self.emit(f"No vocabulary for unit {unit!r}. /path lists the stages.")
                return
            self._start_cards([{
                "front": card["ko"],
                "back": f"{card['en']} ({card['note']})" if card.get("note") else card["en"],
                "example": "", "speech": card["ko"], "keys": card["ko"],
            } for card in cards], "Flashcards", f"Flashcards: {unit}")
            return
        if not argument:
            if not self._open_pack_picker("flashcards"):
                self.emit("Usage: /flashcards <pack_id[@version]|path> (no packs imported yet)")
            return
        try:
            pack = self._resolve_pack(argument)
        except (ValueError, ContentValidationError, OSError) as exc:
            self.emit(str(exc))
            suggestions = self._suggest_packs(argument)
            if suggestions:
                self.emit(f"Did you mean: {', '.join(suggestions)}?")
            return
        from ..flashcards import wordlist_deck

        cards = build_deck(pack, seed=self._flashcard_seed)
        if not cards:  # a pack with no taught notes still has mined words
            cards = wordlist_deck(self.library_dir, pack.pack_id)
        deck = [
            {
                "front": card["ko"],
                "back": f"{card['en']} ({card['note']})" if card.get("note") else card["en"],
                "example": "",
                "speech": card["ko"],
                "keys": card["ko"],
            }
            for card in cards
        ]
        if not deck:
            self.emit("This pack has no vocabulary entries to drill.")
            return
        self._start_cards(deck, "Flashcards", f"Flashcards: {pack.title}")

    def cmd_grammar(self, argument: str) -> None:
        from ..grammar import build_grammar_cards

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
        pack = None
        limit = None
        for part in argument.split():
            if part.isdigit():
                limit = int(part)
            else:
                try:
                    pack = self._resolve_pack(part)
                except (ValueError, ContentValidationError, OSError) as exc:
                    self.emit(str(exc))
                    suggestions = self._suggest_packs(part)
                    if suggestions:
                        self.emit(f"Did you mean: {', '.join(suggestions)}?")
                    return
        if pack is None and limit is None:
            limit = 20  # a library-wide deck can be large; cap the default session
        deck = build_grammar_cards(
            pack=pack,
            library_dir=None if pack else self.library_dir,
            seed=self._flashcard_seed,
            limit=limit,
        )
        if not deck:
            self.emit("No grammar notes found. Import a pack first, or name one: /grammar <pack>")
            return
        title = f"Grammar practice: {pack.title}" if pack else "Grammar practice: every imported pack"
        self._start_cards(deck, "Grammar practice", title)

    def _start_cards(self, deck: list[dict[str, str]], label: str, title: str) -> None:
        self._flash_deck = deck
        self._flash_index = 0
        self._flash_known = 0
        self._flash_missed = []
        self._flash_label = label
        self.emit(ansi.style(title, ansi.BOLD))
        self.emit(f"{len(deck)} card(s) · Enter flips · y/n grades · /say hears it · /pause stops")
        if "grammar" in label.lower():
            self.emit(ansi.style(GRAMMAR_LEGEND, ansi.DIM))
        self._present_card()

    def cmd_dictation(self, argument: str) -> None:
        from ..dictation import collect_dictation_texts

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
        if not argument:
            if not self._open_pack_picker("dictation"):
                self.emit("Usage: /dictation <pack_id[@version]|path> [limit] (no packs imported yet)")
            return
        parts = argument.split()
        ref = parts[0]
        limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        try:
            pack = self._resolve_pack(ref)
        except (ValueError, ContentValidationError, OSError) as exc:
            self.emit(str(exc))
            suggestions = self._suggest_packs(ref)
            if suggestions:
                self.emit(f"Did you mean: {', '.join(suggestions)}?")
            return
        texts = collect_dictation_texts(pack, limit=limit)
        if not texts:
            self.emit("This pack has no listening transcripts for dictation.")
            return
        self._dictation_texts = texts
        self._dictation_index = 0
        self._dictation_total_accuracy = 0.0
        self._dictation_perfect = 0
        self.emit(ansi.style(f"Dictation: {pack.title}", ansi.BOLD))
        self.emit(f"{len(texts)} sentence(s) · type what you hear · /replay repeats · /pause stops")
        self._present_dictation()

    def _present_dictation(self) -> None:
        text = self._dictation_texts[self._dictation_index]
        self.emit("")
        self.emit(render.rule(f"Dictation {self._dictation_index + 1}/{len(self._dictation_texts)}"))
        self.current_audio = self._speak([text], playback=True)
        if not self.current_audio:
            self.emit(ansi.style("(audio unavailable — the sentence stays hidden; type your best guess)", ansi.DIM))
        self.state = DICTATION

    def _grade_dictation(self, typed: str) -> None:
        from ..dictation import accuracy, feedback_lines

        expected = self._dictation_texts[self._dictation_index]
        score = accuracy(expected, typed)
        self._dictation_total_accuracy += score
        if score >= 0.999:
            self._dictation_perfect += 1
        for line in feedback_lines(expected, typed, keyboard_hints=self.keyboard_hints):
            self.emit(line)
        self._dictation_index += 1
        if self._dictation_index >= len(self._dictation_texts):
            self._end_dictation()
        else:
            self._present_dictation()

    def _end_dictation(self, early: bool = False) -> None:
        done = self._dictation_index
        if early:
            self.emit(f"Dictation stopped after {done}/{len(self._dictation_texts)} sentence(s).")
        if done:
            average = self._dictation_total_accuracy / done * 100
            self.emit(f"Average accuracy: {average:.0f}% · perfect {self._dictation_perfect}/{done}")
            from ..practice_log import record_practice

            record_practice(self.attempt_dir, mode="dictation", label="Dictation",
                            hits=self._dictation_perfect, total=done)
        self._dictation_texts = []
        self._dictation_index = 0
        self._dictation_total_accuracy = 0.0
        self._dictation_perfect = 0
        self.current_audio = []
        self.state = IDLE

    def _present_card(self) -> None:
        card = self._flash_deck[self._flash_index]
        self.emit("")
        self.emit(render.rule(f"Card {self._flash_index + 1}/{len(self._flash_deck)}"))
        self.emit(ansi.style(card["front"], ansi.BOLD, ansi.CYAN))
        self.state = FLASH_FRONT

    def _flip_card(self) -> None:
        card = self._flash_deck[self._flash_index]
        self.emit(card["back"])
        if card.get("example"):
            self.emit(ansi.style(f"예: {card['example']}", ansi.CYAN))
        if self.keyboard_hints and card.get("keys"):
            from ..hangul import keystroke_hint

            self.emit(ansi.style(keystroke_hint(card["keys"]), ansi.DIM))
        self.emit(ansi.style("Knew it? y / n", ansi.GREY))
        self.state = FLASH_BACK

    def _grade_card(self, known: bool) -> None:
        card = self._flash_deck[self._flash_index]
        if known:
            self._flash_known += 1
        else:
            self._flash_missed.append(card["front"])
        self._flash_index += 1
        if self._flash_index >= len(self._flash_deck):
            self._end_flashcards()
        else:
            self._present_card()

    def _end_flashcards(self, early: bool = False) -> None:
        seen = self._flash_index
        if early:
            self.emit(f"{self._flash_label} stopped after {seen}/{len(self._flash_deck)} card(s).")
        if seen:
            self.emit(f"Knew {self._flash_known}/{seen}.")
        if self._flash_missed:
            self.emit(f"Review again: {', '.join(self._flash_missed)}")
        self._flash_deck = []
        self._flash_index = 0
        self._flash_known = 0
        self._flash_missed = []
        if self._course is not None and self._course.get("in_sub"):
            self._course_after_subactivity()
            return
        self.state = IDLE

    def cmd_hint(self, argument: str) -> None:
        if self._active_question is None or self.state != ANSWERING:
            self.emit("Hints are available while a question is waiting for an answer.")
            return
        vocabulary = (self._active_question.get("explanation") or {}).get("vocabulary", [])
        if not vocabulary:
            self.emit("No hints are available for this question.")
            return
        if self._hint_index >= len(vocabulary):
            self.emit("No more hints — you have seen them all.")
            return
        item = vocabulary[self._hint_index]
        self._hint_index += 1
        note = f" ({item['note']})" if item.get("note") else ""
        self.emit(f"Hint {self._hint_index}/{len(vocabulary)}: {item.get('ko', '?')}: {item.get('en', '?')}{note}")

    def cmd_replay(self, argument: str) -> None:
        if argument.strip().lower() in {"slow", "slower", "s"}:
            self._replay_slow()
            return
        if not self.current_audio:
            self.emit("No question audio is available to replay.")
            return
        for path in self.current_audio:
            play_audio(path, volume=self.tts_config.volume)

    def _replay_slow(self) -> None:
        """Re-synthesize the current audio at 3/4 speed — the student's
        'could you say that more slowly?'."""
        texts: list[str] = []
        if self._active_question is not None and is_listening_question(self._active_question):
            texts = collect_question_speech_texts(self._active_question, include_prompt=False)
        elif self.state == DICTATION and self._dictation_texts:
            texts = [self._dictation_texts[self._dictation_index]]
        if not texts or not self.audio_enabled:
            self.emit("No question audio is available to replay.")
            return
        config = replace(self.tts_config, speed=max(0.4, self.tts_config.speed * 0.75), playback=True)
        try:
            synthesize_many(texts, config)
        except RuntimeError as exc:
            self.emit(f"TTS unavailable: {exc}")

    def cmd_transcript(self, argument: str) -> None:
        if self._active_question is None:
            self.emit("No question is active.")
            return
        self.emit(render.transcript_block(self._active_question))

    def cmd_skip(self, argument: str) -> None:
        if self.state != ANSWERING:
            self.emit("No question is awaiting an answer.")
            return
        self.emit("Skipped — recorded as unanswered.")
        self._submit("")

    def cmd_pause(self, argument: str) -> None:
        if self._course is not None:
            self._leave_course()
            return
        if self.state == COURSE_PICK:
            self.emit("Cancelled.")
            self._course_list = []
            self.state = IDLE
            return
        if self.state in {FLASH_FRONT, FLASH_BACK, DICTATION, TYPING, COMPOSE_PICK,
                          COMPOSE_TYPE, COMPOSE_GRADE, DIALOGUE_PICK, DIALOGUE_TYPE,
                          DIALOGUE_GRADE, HOMEWORK_PICK}:
            self._end_minigames()
            return
        if self.session is None:
            self.emit("No test is running.")
            return
        self.emit(f"Attempt saved to {self.session.attempt_path}. /resume continues it.")
        self._reset_session()

    def cmd_status(self, argument: str) -> None:
        self.emit(render.rule("Status"))
        if self.session is None:
            self.emit("No active test.")
        else:
            answered, total = self.session.progress()
            earned, available = self.session.running_score()
            self.emit(f"Pack: {self.session.pack.title} ({self.session.pack.pack_id})")
            self.emit(f"Activity: {self.session.activity}")
            self.emit(f"Progress: {answered}/{total} answered · running score {earned}/{available}")
            self.emit(f"Attempt: {self.session.attempt['attempt_id']}")
        config = self.tts_config
        state = "on" if self.audio_enabled else "off"
        self.emit(
            f"TTS: {state} · provider {config.provider} · voice {config.speaker_id or 'default'}"
            f" · speed {config.speed} · volume {config.volume}"
        )

    def cmd_report(self, argument: str) -> None:
        located = self._locate_attempt(argument, want_completed=True, action="report")
        if located is None:
            return
        self._do_report(*located)

    def _do_report(self, path: Path, attempt: dict[str, Any]) -> None:
        from ..report import build_report

        try:
            pack = self._resolve_pack_for_attempt(attempt)
        except (KeyError, ValueError, ContentValidationError, OSError) as exc:
            self.emit(str(exc))
            return
        report_dir = self.attempt_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{attempt.get('attempt_id', path.stem)}.md"
        report_path.write_text(build_report(attempt, pack), encoding="utf-8")
        self.emit(f"Report written to {report_path}")

    def cmd_course(self, argument: str) -> None:
        from ..courses import courses_for, load_progress

        if self.session is not None or self._course is not None:
            self.emit("Finish or /pause the current activity first.")
            return
        self._end_minigames()
        argument = argument.strip()
        if not argument:
            if not self._open_course_pack_picker():
                self.emit("No courses are available yet. Courses ship with the bundled exam packs.")
            return
        try:
            pack = self._resolve_pack(argument)
        except (ValueError, ContentValidationError, OSError) as exc:
            self.emit(str(exc))
            return
        courses = courses_for(pack.pack_id, self.courses_path)
        if not courses:
            self.emit(f"No course is defined for {pack.pack_id}. /packs shows what is available.")
            return
        self._course_pack = pack
        self._course_list = courses
        done = set((load_progress(self.attempt_dir).get(pack.pack_id) or {}).keys())
        from ..homework import homework_entry, load_homework_progress

        hw_progress = load_homework_progress(self.attempt_dir)
        homework = {}
        for course in courses:
            entry = homework_entry(hw_progress, pack.pack_id, str(course.get("id")))
            if entry:
                homework[str(course.get("id"))] = f"{entry.get('best_correct', 0)}/{entry.get('best_total', 0)}"
        self.emit(render.course_list(pack.title, courses, done, homework))
        self.state = COURSE_PICK

    def _open_course_pack_picker(self, action: str = "course") -> bool:
        from ..courses import packs_with_courses

        try:
            entries = latest_packs(self.library_dir)
        except (OSError, ValueError, KeyError):
            entries = []
        with_courses = packs_with_courses([e["pack_id"] for e in entries], self.courses_path)
        entries = [e for e in entries if e["pack_id"] in with_courses]
        if not entries:
            return False
        self._pack_pick_refs = [e["pack_id"] for e in entries]
        self._pack_pick_action = action
        label = "Pick a pack to study as a course" if action == "course" else "Pick a pack to do homework for"
        self.emit(render.rule(label))
        for index, entry in enumerate(entries, start=1):
            n = len(courses_for(entry["pack_id"], self.courses_path))
            self.emit(f"  {ansi.style(str(index), ansi.BOLD, ansi.CYAN)}. {entry.get('title', entry['pack_id'])}  {ansi.style(f'{n} courses', ansi.GREY)}")
        self.emit("Type the number, or press Enter to cancel.")
        self.state = PICK_PACK
        return True

    def _handle_course_pick(self, text: str) -> None:
        if not text:
            self.emit("Cancelled.")
            self._course_list = []
            self.state = IDLE
            return
        if text.isdigit() and 1 <= int(text) <= len(self._course_list):
            course = self._course_list[int(text) - 1]
            self._course_list = []
            self._start_course(self._course_pack, course)
            return
        self.emit(f"Type a number from 1 to {len(self._course_list)}, or press Enter to cancel.")

    def _start_course(self, pack: Any, course: dict[str, Any]) -> None:
        self._course = {"pack": pack, "course": course, "step": 0, "in_sub": False}
        self.emit("")
        self.emit(render.course_intro(course))
        self.emit(ansi.style("Press Enter to begin step 1 of 3: Vocabulary.", ansi.GREY))
        self.state = COURSE_STEP

    def _handle_course_step(self, text: str) -> None:
        if text:
            self.emit("Press Enter to continue, or /pause to leave the course.")
            return
        self._course_run_step()

    COURSE_STEPS = ("Vocabulary", "Grammar", "Exam questions")

    def _course_run_step(self) -> None:
        course = self._course["course"]
        step = self._course["step"]
        if step == 0:
            vocab = course.get("new_vocabulary", [])
            if not vocab:
                self._course_after_subactivity()
                return
            deck = [
                {"front": v.get("ko", ""), "back": v.get("en", ""), "example": "", "speech": v.get("ko", ""), "keys": v.get("ko", "")}
                for v in vocab
            ]
            self._course["in_sub"] = True
            self._start_cards(deck, "Course vocabulary", f"Vocabulary — {course.get('title', '')}")
        elif step == 1:
            grammar = course.get("new_grammar", [])
            if not grammar:
                self._course_after_subactivity()
                return
            deck = [
                {"front": g.get("pattern", ""), "back": g.get("explanation", ""), "example": g.get("example", ""),
                 "speech": g.get("example", ""), "keys": ""}
                for g in grammar
            ]
            self._course["in_sub"] = True
            self._start_cards(deck, "Course grammar", f"Grammar — {course.get('title', '')}")
        elif step == 2:
            try:
                self.session = ExamSession.start(
                    self._course["pack"], self.attempt_dir, question_ids=course["question_ids"], activity="course"
                )
            except (ValueError, ContentValidationError, OSError) as exc:
                self.emit(str(exc))
                self._course_after_subactivity()
                return
            self._course["in_sub"] = True
            self.emit(ansi.style(f"Exam practice — {len(course['question_ids'])} question(s) from this course.", ansi.BOLD))
            self._present()
        else:
            self._finish_course()

    def _course_after_subactivity(self) -> None:
        if self._course is None:
            return
        self._course["in_sub"] = False
        self._course["step"] += 1
        step = self._course["step"]
        if step >= len(self.COURSE_STEPS):
            self._finish_course()
            return
        self.emit(ansi.style(f"Step done. Press Enter for step {step + 1} of 3: {self.COURSE_STEPS[step]}.", ansi.GREY))
        self.state = COURSE_STEP

    def _finish_course(self) -> None:
        from ..courses import mark_done

        course = self._course["course"]
        pack_id = self._course["pack"].pack_id
        mark_done(self.attempt_dir, pack_id, course["id"])
        self.emit(render.rule("Course complete"))
        self.emit(ansi.style(f"✓ {course.get('title', '')}", ansi.BOLD, ansi.GREEN))
        review = str(course.get("review", "")).strip()
        if review:
            self.emit(review)
        self.emit(
            f"Solidify it: /homework {pack_id} {course.get('order', 1)} validates this lesson's"
            " vocabulary and grammar. /course continues with the next one."
        )
        self._course = None
        self.state = IDLE

    def _leave_course(self) -> None:
        # Clear the course first so the sub-activity end-hooks go idle instead
        # of advancing to the next step.
        self._course = None
        self._course_list = []
        if self.state in {FLASH_FRONT, FLASH_BACK}:
            self._end_flashcards(early=True)
        elif self.session is not None:
            self._reset_session()
        self.emit("Left the course. Finished steps are saved.")
        self.state = IDLE

    def cmd_homework(self, argument: str) -> None:
        from ..courses import courses_for
        from ..homework import homework_entry, load_homework_progress

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
        pack_ref: str | None = None
        lesson_num: int | None = None
        for part in argument.split():
            if part.isdigit():
                lesson_num = int(part)
            elif pack_ref is None:
                pack_ref = part
        if pack_ref is None:
            if lesson_num is not None:
                self.emit("Name the pack first: /homework <pack> [lesson]")
                return
            if not self._open_course_pack_picker("homework"):
                self.emit("No courses are available yet. Courses ship with the bundled exam packs.")
            return
        try:
            pack = self._resolve_pack(pack_ref)
        except (ValueError, ContentValidationError, OSError) as exc:
            self.emit(str(exc))
            return
        courses = courses_for(pack.pack_id, self.courses_path)
        if not courses:
            self.emit(f"No course is defined for {pack.pack_id}, so there is no homework yet.")
            return
        if lesson_num is not None:
            if not 1 <= lesson_num <= len(courses):
                self.emit(f"Pick a lesson from 1 to {len(courses)}.")
                return
            self._start_homework(pack, courses[lesson_num - 1])
            return
        self._homework_pack = pack
        self._homework_courses = courses
        progress = load_homework_progress(self.attempt_dir)
        self.emit(render.rule(f"Homework · {pack.title}"))
        for index, course in enumerate(courses, start=1):
            entry = homework_entry(progress, pack.pack_id, str(course.get("id")))
            if entry:
                mark = ansi.style("✓", ansi.GREEN)
                note = f"best {entry.get('best_correct', 0)}/{entry.get('best_total', 0)} · {entry.get('runs', 1)} run(s)"
            else:
                mark = " "
                note = "not done"
            title = str(course.get("title", course.get("id", "?")))
            self.emit(
                f"  {mark} {ansi.style(str(index), ansi.BOLD, ansi.CYAN)}. {title}"
                f"  {ansi.style(note, ansi.GREY)}"
            )
        self.emit("Type a number to start that lesson's homework, or press Enter to cancel.")
        self.state = HOMEWORK_PICK

    def _handle_homework_pick(self, text: str) -> None:
        if not text:
            self.emit("Cancelled.")
            self._homework_courses = []
            self._homework_pack = None
            self.state = IDLE
            return
        if text.isdigit() and 1 <= int(text) <= len(self._homework_courses):
            course = self._homework_courses[int(text) - 1]
            pack = self._homework_pack
            self._homework_courses = []
            self._homework_pack = None
            self._start_homework(pack, course)
            return
        self.emit(f"Type a number from 1 to {len(self._homework_courses)}, or press Enter to cancel.")

    def _start_homework(self, pack: Any, course: dict[str, Any]) -> None:
        from ..homework import build_homework

        items = build_homework(course, pack=pack, seed=self._flashcard_seed,
                               compose_path=self.compose_path)
        if not items:
            self.emit("This lesson has no vocabulary or grammar to practice yet.")
            return
        self._typing_homework = (pack.pack_id, str(course.get("id")))
        self.emit(render.rule(f"Homework · Lesson {course.get('order', '?')}"))
        title_ko = str(course.get("title_ko", "")).strip()
        header = str(course.get("title", "")) + (ansi.style(f"  ({title_ko})", ansi.DIM) if title_ko else "")
        self.emit(ansi.style(header, ansi.BOLD, ansi.CYAN))
        for objective in course.get("objectives", []):
            self.emit(f"  • {objective}")
        if any(item.get("kind") == "pattern" for item in items):
            self.emit(ansi.style(GRAMMAR_LEGEND, ansi.DIM))
        self._start_typing(
            items, label="Homework", verb="Solved", title="Validate what this lesson taught:",
            hint="type the answer — options take their number · /say speaks it · /pause stops",
        )

    def cmd_stats(self, argument: str) -> None:
        from ..practice_log import load_practice_log, practice_summary, weak_items
        from ..stats import collect_stats, format_stats

        self.emit(render.rule("Study stats"))
        for line in format_stats(collect_stats(self.attempt_dir, self.library_dir)):
            self.emit(line)
        log = load_practice_log(self.attempt_dir)
        summary = practice_summary(log)
        if summary["runs"]:
            accuracy = f" · accuracy {summary['accuracy'] * 100:.0f}%" if summary["accuracy"] is not None else ""
            self.emit("")
            self.emit(ansi.style("Practice", ansi.BOLD))
            self.emit(f"  {summary['runs']} run(s) · {summary['hits']}/{summary['total']} correct{accuracy}")
            weak = weak_items(log, limit=8)
            if weak:
                listing = " · ".join(f"{entry['item']} (×{entry['count']})" for entry in weak)
                self.emit(f"  Weak items: {listing}")
                self.emit("  /misses drills them until they stop being weak.")

    def cmd_facts(self, argument: str) -> None:
        from ..facts import categories, filter_facts, load_facts

        if self._facts is None:
            self._facts = load_facts(self.facts_path)
        facts = self._facts
        if not facts:
            self.emit(f"No facts are available (looked for {self.facts_path}).")
            return

        wanted = argument.strip().lower()
        if wanted in {"list", "categories", "category"}:
            self.emit(render.rule("Korea facts · categories"))
            for category in categories(facts):
                self.emit(f"  {category} ({len(filter_facts(facts, category))})")
            self.emit("Try /facts <category>, or just /facts for a random one.")
            return

        pool = filter_facts(facts, wanted) if wanted else facts
        if not pool:
            self.emit(f"No facts match {argument!r}. /facts list shows the categories.")
            pool = facts
        fact = self._pick_fact(pool)
        self._fact_speech = str(fact.get("korean", "")).strip()
        self.emit(render.fact_card(fact))
        if self._fact_speech and self.audio_enabled:
            self.emit(ansi.style("(/say reads the Korean aloud)", ansi.GREY))

    def _pick_fact(self, pool: list[dict[str, Any]]) -> dict[str, Any]:
        """Pick a fact, avoiding repeats until the pool is exhausted."""
        pool_ids = {str(fact.get("id")) for fact in pool}
        fresh = [fact for fact in pool if str(fact.get("id")) not in self._facts_seen]
        if not fresh:
            self._facts_seen -= pool_ids  # whole pool seen — start it over
            fresh = pool
        choice = self._facts_rng.choice(fresh)
        self._facts_seen.add(str(choice.get("id")))
        return choice

    def cmd_tts(self, argument: str) -> None:
        if not argument:
            self.cmd_status("")
            return
        parts = argument.split()
        key = parts[0].lower()
        value = parts[1] if len(parts) > 1 else None
        try:
            if key == "on":
                self.audio_enabled = True
                self._tts_warned = False
                self.emit("TTS enabled.")
            elif key == "off":
                self.audio_enabled = False
                self.emit("TTS disabled.")
            elif key == "volume" and value is not None:
                volume = float(value)
                if volume <= 0:
                    raise ValueError("Volume must be greater than 0.")
                self.tts_config = replace(self.tts_config, volume=volume)
                self.emit(f"Volume set to {volume}.")
            elif key == "speed" and value is not None:
                speed = float(value)
                if speed <= 0:
                    raise ValueError("Speed must be greater than 0.")
                self.tts_config = replace(self.tts_config, speed=speed)
                self.emit(f"Speed set to {speed}.")
            elif key == "provider" and value is not None:
                if value not in TTS_PROVIDERS:
                    raise ValueError(f"Provider must be one of {', '.join(TTS_PROVIDERS)}.")
                self.tts_config = replace(self.tts_config, provider=value)
                self._tts_warned = False
                self.emit(f"Provider set to {value}.")
            elif key in {"voice", "speaker"} and value is not None:
                self.tts_config = replace(self.tts_config, speaker_id=value)
                self.emit(f"Voice set to {value}.")
            else:
                self.emit("Usage: /tts [on|off|volume <x>|speed <x>|provider <p>|voice <v>]")
        except ValueError as exc:
            self.emit(str(exc))

    # ------------------------------------------------------------- test flow

    def _present(self) -> None:
        if self.session is None:
            return
        question = self.session.current_question()
        if question is None:
            self._finish()
            return
        self._active_question = question
        self._hint_index = 0
        _, total = self.session.progress()
        self.emit("")
        self.emit(
            render.question_card(
                self.session.question_number(),
                total,
                question,
                self.show_transcript,
                audio_expected=self.audio_enabled,
            )
        )
        self.current_audio = []
        self._transcript_pre_shown = self.show_transcript
        media = question_audio_file(question)
        if media is not None:  # official recording; plays even with TTS off
            play_audio(media, volume=self.tts_config.volume)
            self.current_audio = [media]
        elif self.audio_enabled and is_listening_question(question):
            texts = collect_question_speech_texts(question, include_prompt=False)
            self.current_audio = self._speak(texts, playback=True)
        if is_listening_question(question) and not self._transcript_pre_shown and not self.current_audio:
            # TTS off, unavailable, or failed: the question must stay answerable.
            self.emit(ansi.style("(audio unavailable — transcript shown)", ansi.DIM))
            self.emit(render.transcript_block(question))
            self._transcript_pre_shown = True
        self._prefetch_next()
        self.session.mark_presented()
        self.state = ANSWERING

    def _submit(self, response: str) -> None:
        if self.session is None:
            return
        result = self.session.submit(response)
        self.emit(render.feedback_block(result, self._active_question or {}, self._transcript_pre_shown))
        self.emit(render.continue_hint())
        self.state = CONTINUE

    def _advance(self) -> None:
        if self.session is None:
            self.state = IDLE
            return
        if self.session.has_remaining():
            self._present()
        else:
            self._finish()

    def _finish(self) -> None:
        if self.session is None:
            return
        attempt = self.session.finalize()
        self.emit("")
        self.emit(render.summary_panel(attempt))
        missed = missed_question_ids(attempt)
        if missed:
            self.emit(f"Tip: /drill 1 re-practices the {len(missed)} missed question(s).")
        self._record_review_queue(attempt)
        self._refresh_recent()
        self._reset_session()
        if self._course is not None and self._course.get("in_sub"):
            self._course_after_subactivity()

    def _record_review_queue(self, attempt: dict[str, Any]) -> None:
        from .. import srs

        queue_path = srs.queue_path_for(self.attempt_dir)
        queue = srs.load_queue(queue_path)
        if srs.record_attempt(queue, attempt):
            srs.save_queue(queue, queue_path)
        due_count = len(srs.due_items(queue))
        if due_count:
            self.emit(f"Review queue: {due_count} item(s) due · /review")

    def _reset_session(self) -> None:
        self.session = None
        self.state = IDLE
        self.current_audio = []
        self._active_question = None
        self._transcript_pre_shown = False

    # ------------------------------------------------------------- helpers

    def _resolve_pack(self, ref: str) -> ExamPack:
        path = Path(ref)
        if path.exists():
            return load_pack(path)
        return load_pack_ref(ref, self.library_dir)

    def _suggest_packs(self, ref: str) -> list[str]:
        from difflib import get_close_matches

        try:
            packs = list_packs(self.library_dir)
        except (OSError, ValueError, KeyError):
            return []
        wanted = ref.split("@", 1)[0]
        pack_ids = sorted({str(pack["pack_id"]) for pack in packs})
        return get_close_matches(wanted, pack_ids, n=3, cutoff=0.5)

    def _cached_completions(self, key: str, builder: Callable[[], list], ttl: float = 2.0) -> list:
        now = time.monotonic()
        hit = self._completion_cache.get(key)
        if hit is not None and now - hit[0] < ttl:
            return hit[1]
        value = builder()
        self._completion_cache[key] = (now, value)
        return value

    def pack_completions(self) -> list[tuple[str, str]]:
        """(ref, description) pairs for pack autocompletion."""
        return self._cached_completions("packs", self._build_pack_completions)

    def _build_pack_completions(self) -> list[tuple[str, str]]:
        try:
            packs = list_packs(self.library_dir)
        except (OSError, ValueError, KeyError):
            return []
        by_id: dict[str, list[dict[str, Any]]] = {}
        for pack in packs:
            pack_id = str(pack.get("pack_id", ""))
            if pack_id:
                by_id.setdefault(pack_id, []).append(pack)
        items: list[tuple[str, str]] = []
        for pack_id, versions in by_id.items():
            latest = versions[-1]
            difficulty = f" · {latest['difficulty']}" if latest.get("difficulty") else ""
            meta = f"{latest.get('title', '')}{difficulty} · {latest.get('question_count', '?')} q"
            items.append((pack_id, meta))
            # A bare id always means the latest version; pinned refs only
            # earn a place in the menu when there is actually a choice.
            if len(versions) > 1:
                for version in versions:
                    ref = f"{pack_id}@{version.get('pack_version', '')}"
                    items.append((ref, f"{version.get('title', '')} · version {version.get('pack_version', '?')}"))
        return items

    def _resolve_pack_for_attempt(self, attempt: dict[str, Any]) -> ExamPack:
        """Prefer the library, but fall back to the source file the attempt was started from."""
        try:
            return self._resolve_pack(f"{attempt['pack_id']}@{attempt['pack_version']}")
        except (ValueError, ContentValidationError):
            pack_path = attempt.get("pack_path")
            if pack_path and Path(pack_path).exists():
                return load_pack(pack_path)
            raise

    def _refresh_recent(self) -> list[tuple[Path, dict[str, Any]]]:
        from ..cli import recent_attempt_entries

        self._recent_attempts = recent_attempt_entries(self.attempt_dir, RECENT_LIMIT)
        return self._recent_attempts

    def _locate_attempt(
        self,
        argument: str,
        want_completed: bool = False,
        action: str | None = None,
    ) -> tuple[Path, dict[str, Any]] | None:
        entries = self._refresh_recent()
        if argument:
            candidate = Path(argument)
            if candidate.exists():
                return candidate, load_attempt(candidate)
            if argument.isdigit():
                index = int(argument)
                if 1 <= index <= len(entries):
                    return entries[index - 1]
                self.emit(f"Pick a number from 1 to {len(entries)} (see /attempts).")
                return None
            self.emit(f"Attempt {argument!r} was not found.")
            return None

        wanted_status = "completed" if want_completed else "in_progress"
        candidates = [(path, attempt) for path, attempt in entries if attempt.get("status") == wanted_status]
        if not candidates:
            self.emit(f"No {wanted_status.replace('_', ' ')} attempt found. /attempts lists what is saved.")
            return None
        if len(candidates) == 1 or action is None:
            return candidates[0]
        if self.session is not None:
            # Mid-test there is no safe place to park a picker; keep the old
            # most-recent behavior instead.
            return candidates[0]
        self._pick_entries = candidates
        self._pick_action = action
        self.emit(render.rule(f"Pick an attempt to {action}"))
        for index, (path, attempt) in enumerate(candidates, start=1):
            self.emit(self._attempt_line(index, path, attempt))
        self.emit("Type the number, or press Enter to cancel.")
        self.state = PICK
        return None

    LEVEL_FILTERS = {"i": "TOPIK_I", "1": "TOPIK_I", "topik-i": "TOPIK_I", "ii": "TOPIK_II", "2": "TOPIK_II", "topik-ii": "TOPIK_II"}

    def _filter_pack_entries(self, entries: list[dict[str, Any]], filter_text: str) -> list[dict[str, Any]]:
        wanted = filter_text.strip().lower()
        if not wanted:
            return entries
        level = self.LEVEL_FILTERS.get(wanted)
        if level:
            return [entry for entry in entries if str(entry.get("topik_level", "")) == level]
        return [
            entry
            for entry in entries
            if wanted in " ".join(
                str(entry.get(field, "")) for field in ("pack_id", "title", "difficulty", "topik_level")
            ).lower()
        ]

    def _pack_progress_note(self, progress: dict[str, dict[str, Any]], pack_id: str) -> str:
        entry = progress.get(pack_id)
        if not entry:
            return "untaken"
        best_score, best_max = entry["best"]
        return f"best {best_score}/{best_max} · {entry['attempts']} attempt(s)"

    def _open_pack_picker(self, action: str, filter_text: str = "") -> bool:
        """Pack chooser for no-argument /take, /flashcards, /dictation:
        grouped by level, with difficulty and your progress per pack.
        Typing text instead of a number narrows the list."""
        if self.session is not None:
            return False
        from ..stats import pack_progress

        try:
            entries = latest_packs(self.library_dir)
        except (OSError, ValueError, KeyError):
            entries = []
        if not entries:
            return False
        matched = self._filter_pack_entries(entries, filter_text)
        if filter_text and not matched:
            self.emit(f"No pack matches {filter_text!r} — showing everything.")
            matched = entries
            filter_text = ""
        progress = pack_progress(self.attempt_dir)

        self._pack_pick_refs = []
        self._pack_pick_action = action
        label = f"Pick a pack to {action}" + (f" · filter: {filter_text}" if filter_text else "")
        self.emit(render.rule(label))
        by_level: dict[str, list[dict[str, Any]]] = {}
        for entry in matched:
            by_level.setdefault(str(entry.get("topik_level", "OTHER")), []).append(entry)
        index = 0
        for level in sorted(by_level):
            self.emit(ansi.style(level.replace("_", " "), ansi.BOLD))
            for entry in by_level[level]:
                index += 1
                pack_id = str(entry.get("pack_id", ""))
                self._pack_pick_refs.append(pack_id)
                meta_parts = [pack_id]
                if entry.get("difficulty"):
                    meta_parts.append(str(entry["difficulty"]))
                meta_parts.append(f"{entry.get('question_count', '?')} q")
                meta_parts.append(self._pack_progress_note(progress, pack_id))
                self.emit(
                    f"  {ansi.style(str(index), ansi.BOLD, ansi.CYAN)}. {entry.get('title', pack_id)}"
                    f"  {ansi.style(' · '.join(meta_parts), ansi.GREY)}"
                )
        self.emit("Type a number · type text (e.g. ii, authentic) to filter · Enter cancels.")
        self.state = PICK_PACK
        return True

    def _handle_pack_pick(self, text: str) -> None:
        if not text:
            self.emit("Cancelled.")
            self._clear_pack_pick()
            return
        if text.isdigit() and 1 <= int(text) <= len(self._pack_pick_refs):
            ref = self._pack_pick_refs[int(text) - 1]
            action = self._pack_pick_action
            self._clear_pack_pick()
            handler = {
                "take": self.cmd_take,
                "flashcards": self.cmd_flashcards,
                "dictation": self.cmd_dictation,
                "course": self.cmd_course,
                "homework": self.cmd_homework,
            }[action]
            handler(ref)
            return
        if not text.isdigit():
            # Anything non-numeric narrows the list instead of erroring.
            self._open_pack_picker(self._pack_pick_action, filter_text=text)
            return
        self.emit(f"Type a number from 1 to {len(self._pack_pick_refs)}, or press Enter to cancel.")

    def _clear_pack_pick(self) -> None:
        self._pack_pick_refs = []
        self._pack_pick_action = None
        if self.state == PICK_PACK:
            self.state = IDLE

    def _handle_pick(self, text: str) -> None:
        if not text:
            self.emit("Cancelled.")
            self._clear_pick()
            return
        if text.isdigit():
            index = int(text)
            if 1 <= index <= len(self._pick_entries):
                path, attempt = self._pick_entries[index - 1]
                action = self._pick_action
                self._clear_pick()
                if action == "resume":
                    self._do_resume(path, attempt)
                elif action == "drill":
                    self._do_drill(path, attempt)
                elif action == "report":
                    self._do_report(path, attempt)
                return
        self.emit(f"Enter a number from 1 to {len(self._pick_entries)}, or press Enter to cancel.")

    def _clear_pick(self) -> None:
        self._pick_entries = []
        self._pick_action = None
        if self.state == PICK:
            self.state = IDLE

    def _attempt_line(self, index: int, path: Path, attempt: dict[str, Any]) -> str:
        answered = len(attempt.get("answers", []))
        total = len(attempt.get("question_ids", []))
        status = attempt.get("status", "unknown")
        ref = f"{attempt.get('pack_id', '?')}@{attempt.get('pack_version', '?')}"
        updated = str(attempt.get("updated_at") or attempt.get("completed_at") or "")[:16].replace("T", " ")
        return f"  {index}. {status} · {answered}/{total} answered · {ref} · {updated} · {path.name}"

    def attempt_completion_items(self, command: str) -> list[tuple[str, str]]:
        """Tab-completion values for /resume, /drill, /report: the /attempts index plus a summary."""
        wanted = {"resume": "in_progress", "drill": "completed", "report": "completed"}.get(command)
        if wanted is None:
            return []
        return self._cached_completions(f"attempts:{wanted}", lambda: self._build_attempt_completions(wanted))

    def _build_attempt_completions(self, wanted: str) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        for index, (path, attempt) in enumerate(self._refresh_recent(), start=1):
            if attempt.get("status") != wanted:
                continue
            answered = len(attempt.get("answers", []))
            total = len(attempt.get("question_ids", []))
            ref = f"{attempt.get('pack_id', '?')}@{attempt.get('pack_version', '?')}"
            items.append((str(index), f"{attempt.get('status')} · {answered}/{total} · {ref}"))
        return items

    def _speak(self, texts: list[str], playback: bool) -> list[Path]:
        if not self.audio_enabled:
            return []
        config = replace(self.tts_config, playback=playback)
        try:
            return synthesize_many(texts, config)
        except RuntimeError as exc:
            if not self._tts_warned:
                self.emit(f"TTS unavailable: {exc}")
                self._tts_warned = True
            return []

    def _prefetch_next(self) -> None:
        if self.session is None or not self.audio_enabled:
            return
        upcoming = self.session.next_question()
        if upcoming is None or not is_listening_question(upcoming):
            return
        texts = collect_question_speech_texts(upcoming, include_prompt=False)
        self.prefetcher.schedule(texts, self.tts_config)


# ----------------------------------------------------------------- frontends


class PlainFrontend:
    """input()-based fallback used when prompt_toolkit is unavailable."""

    def __init__(self, shell: Shell, input_fn: Callable[[str], str] = input) -> None:
        self._input_fn = input_fn

    def readline(self) -> str:
        return self._input_fn("❯ ")


class PromptToolkitFrontend:
    """Claude Code-style input line: history, slash-command completion, status toolbar."""

    def __init__(self, shell: Shell) -> None:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory

        history_path = Path("data") / "shell_history.txt"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        self._session = PromptSession(
            history=FileHistory(str(history_path)),
            completer=_make_completer(shell),
            complete_while_typing=True,
            bottom_toolbar=shell.status_line,
            refresh_interval=1.0,  # the toolbar countdown ticks without keystrokes
            style=_make_style(),
        )

    def readline(self) -> str:
        return self._session.prompt("❯ ")


def _make_style():
    """Calm dark menu with a cyan selection bar and a dimmer meta column."""
    from prompt_toolkit.styles import Style

    return Style.from_dict(
        {
            "completion-menu": "bg:#20242e #d4dae3",
            "completion-menu.completion.current": "bg:#3fa7c4 #10151c bold",
            "completion-menu.meta.completion": "bg:#181c24 #8a94a3",
            "completion-menu.meta.completion.current": "bg:#3fa7c4 #10151c",
            "scrollbar.background": "bg:#20242e",
            "scrollbar.button": "bg:#3fa7c4",
            "bottom-toolbar": "bg:#181c24 #9aa5b5",
        }
    )


def _make_completer(shell: Shell):
    from prompt_toolkit.completion import Completer, Completion

    class SlashCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if not text.startswith("/"):
                return
            if " " not in text:
                for command in shell.registry.all():
                    for token in command.tokens():
                        if token.startswith(text.lower()):
                            yield Completion(
                                token,
                                start_position=-len(text),
                                display=token,
                                display_meta=command.description,
                            )
                            break
                return
            command_token, _, argument = text.partition(" ")
            name = command_token[1:].lower()
            if " " in argument:
                return
            if name in {"take", "flashcards", "cards", "dictation", "typing", "grammar", "gram", "recall", "translate", "course", "homework", "hw", "conjugate", "conj"}:
                for ref, meta in shell.pack_completions():
                    if ref.startswith(argument):
                        yield Completion(
                            ref,
                            start_position=-len(argument),
                            display=ref,
                            display_meta=meta,
                        )
            elif name in {"resume", "drill", "report"}:
                for value, meta in shell.attempt_completion_items(name):
                    if value.startswith(argument):
                        yield Completion(
                            value,
                            start_position=-len(argument),
                            display=value,
                            display_meta=meta,
                        )
            elif name in {"help", "h", "?"}:
                for command in shell.registry.all():
                    if command.name.startswith(argument.lstrip("/").lower()):
                        yield Completion(
                            command.name,
                            start_position=-len(argument),
                            display=command.name,
                            display_meta=command.description,
                        )

    return SlashCompleter()


def _build_frontend(shell: Shell, input_fn: Callable[[str], str] | None):
    if input_fn is not None:
        return PlainFrontend(shell, input_fn)
    try:
        return PromptToolkitFrontend(shell)
    except Exception:
        # No prompt_toolkit, or no real console (piped stdin); plain input still works.
        return PlainFrontend(shell)


def _offer_first_run_import(shell: Shell, frontend, source_dir: str | Path) -> None:
    """One-keystroke onboarding: with an empty library and bundled sources
    present, offer to import everything. Never prompts when packs exist."""
    from ..workspace import bundled_pack_paths, format_setup_summary, setup_workspace

    try:
        if list_packs(shell.library_dir):
            return
    except (OSError, ValueError, KeyError):
        return
    bundled = bundled_pack_paths(source_dir)
    if not bundled:
        return
    shell.emit(f"No exams are imported yet. Import {len(bundled)} bundled exam pack(s) now? [Y/n]")
    try:
        answer = frontend.readline()
    except (EOFError, KeyboardInterrupt):
        return
    if answer.strip().lower() in {"", "y", "yes"}:
        result = setup_workspace(shell.library_dir, source_dir=source_dir)
        for line in format_setup_summary(result):
            shell.emit(line)
        shell.emit("Press Enter to open the menu.")
    else:
        shell.emit("Skipped. Import the bundled packs anytime with: topik-sim setup")


def run_shell(
    library_dir: str | Path = DEFAULT_LIBRARY_DIR,
    attempt_dir: str | Path = DEFAULT_ATTEMPT_DIR,
    tts_config: TTSConfig | None = None,
    show_transcript: bool = False,
    audio_enabled: bool = True,
    keyboard_hints: bool = False,
    keyboard_pinned: bool = False,
    input_fn: Callable[[str], str] | None = None,
    source_dir: str | Path | None = None,
) -> int:
    from ..workspace import DEFAULT_SOURCE_DIR

    shell = Shell(
        library_dir=library_dir,
        attempt_dir=attempt_dir,
        tts_config=tts_config,
        show_transcript=show_transcript,
        audio_enabled=audio_enabled,
        keyboard_hints=keyboard_hints,
        keyboard_pinned=keyboard_pinned,
    )
    shell.emit(render.banner())
    frontend = _build_frontend(shell, input_fn)
    _offer_first_run_import(shell, frontend, DEFAULT_SOURCE_DIR if source_dir is None else source_dir)
    try:
        while True:
            try:
                line = frontend.readline()
            except KeyboardInterrupt:
                shell.emit("Interrupted. Progress is saved — /quit exits, anything else continues.")
                continue
            except EOFError:
                break
            if not shell.handle_line(line):
                break
    finally:
        shell.close()
    return 0
