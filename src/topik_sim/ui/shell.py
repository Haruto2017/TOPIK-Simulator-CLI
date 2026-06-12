from __future__ import annotations

import shlex
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from ..activities import create_drill_attempt, missed_question_ids
from ..attempts import load_attempt, save_attempt_to_dir
from ..content import ContentValidationError, ExamPack, load_pack
from ..library import DEFAULT_LIBRARY_DIR, list_packs, load_pack_ref
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
PICK = "pick"
PICK_PACK = "pick_pack"
MENU = "menu"
MENU_CATEGORY = "menu_category"

TTS_PROVIDERS = ("supertonic", "melo", "xtts-v2")
DEFAULT_ATTEMPT_DIR = "data/attempts"
RECENT_LIMIT = 10


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
        self._typing_items: list[str] = []
        self._typing_index = 0
        self._typing_hits = 0
        self._typing_missed: list[str] = []

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
        packs = list_packs(self.library_dir)
        if not packs:
            self.emit("No packs imported. Use: python -m topik_sim import-pack <pack.json>")
            return
        self.emit(render.rule("Packs"))
        for pack in packs:
            ref = f"{pack['pack_id']}@{pack['pack_version']}"
            self.emit(f"  {ansi.style(ref, ansi.CYAN)}  {pack['title']} ({pack['question_count']} question(s))")
        self.emit("Start one with /take <pack_id>")

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
            self._speak([self._typing_items[self._typing_index]], playback=True)
            return
        if not argument:
            self.emit("Usage: /say <text> — pronounces the sentence without touching your answer.")
            return
        self._speak([argument], playback=True)

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
        from ..typing_drill import build_typing_items

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
        pack = None
        count = 12
        for part in argument.split():
            if part.isdigit():
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
        self._typing_items = build_typing_items(
            seed=self._flashcard_seed,
            pack=pack,
            count=count,
            library_dir=None if pack else self.library_dir,
        )
        self._typing_index = 0
        self._typing_hits = 0
        self._typing_missed = []
        title = f"Typing practice: {pack.title}" if pack else "Typing practice"
        self.emit(ansi.style(title, ansi.BOLD))
        self.emit(f"{len(self._typing_items)} item(s) · type what you see · /keyboard shows the layout · /pause stops")
        self._present_typing()

    def _present_typing(self) -> None:
        item = self._typing_items[self._typing_index]
        self.emit("")
        self.emit(render.rule(f"Typing {self._typing_index + 1}/{len(self._typing_items)}"))
        self.emit(ansi.style(item, ansi.BOLD, ansi.CYAN))
        self.state = TYPING

    def _grade_typing(self, typed: str) -> None:
        from ..hangul import keystroke_hint
        from ..typing_drill import normalize_typed

        target = self._typing_items[self._typing_index]
        if normalize_typed(typed) == normalize_typed(target):
            self._typing_hits += 1
            self.emit(ansi.style("✓", ansi.BOLD, ansi.GREEN))
        else:
            self._typing_missed.append(target)
            self.emit(ansi.style(f"✗ {target}", ansi.BOLD, ansi.RED) + f" — {keystroke_hint(target)}")
        self._typing_index += 1
        if self._typing_index >= len(self._typing_items):
            self._end_typing()
        else:
            self._present_typing()

    def _end_typing(self, early: bool = False) -> None:
        from ..hangul import keystrokes

        done = self._typing_index
        if early:
            self.emit(f"Typing practice stopped after {done}/{len(self._typing_items)} item(s).")
        if done:
            self.emit(f"Typed {self._typing_hits}/{done} correctly.")
        if self._typing_missed:
            review = " · ".join(f"{item} ({keystrokes(item)})" for item in dict.fromkeys(self._typing_missed))
            self.emit(f"Practice again: {review}")
        self._typing_items = []
        self._typing_index = 0
        self._typing_hits = 0
        self._typing_missed = []
        self.state = IDLE

    def _end_minigames(self) -> None:
        if self.state in {FLASH_FRONT, FLASH_BACK}:
            self._end_flashcards(early=True)
        elif self.state == DICTATION:
            self._end_dictation(early=True)
        elif self.state == TYPING:
            self._end_typing(early=True)

    def cmd_flashcards(self, argument: str) -> None:
        from ..flashcards import build_deck

        if self.session is not None:
            self.emit("Finish or /pause the current test first.")
            return
        self._end_minigames()
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
        deck = [
            {
                "front": card["ko"],
                "back": f"{card['en']} ({card['note']})" if card.get("note") else card["en"],
                "example": "",
                "speech": card["ko"],
                "keys": card["ko"],
            }
            for card in build_deck(pack, seed=self._flashcard_seed)
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
        if not self.current_audio:
            self.emit("No question audio is available to replay.")
            return
        for path in self.current_audio:
            play_audio(path, volume=self.tts_config.volume)

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
        if self.state in {FLASH_FRONT, FLASH_BACK, DICTATION, TYPING}:
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

    def cmd_stats(self, argument: str) -> None:
        from ..stats import collect_stats, format_stats

        self.emit(render.rule("Study stats"))
        for line in format_stats(collect_stats(self.attempt_dir, self.library_dir)):
            self.emit(line)

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
        self.emit(render.question_card(self.session.question_number(), total, question, self.show_transcript))
        self.current_audio = []
        if self.audio_enabled and is_listening_question(question):
            texts = collect_question_speech_texts(question, include_prompt=False)
            self.current_audio = self._speak(texts, playback=True)
        self._prefetch_next()
        self.session.mark_presented()
        self.state = ANSWERING

    def _submit(self, response: str) -> None:
        if self.session is None:
            return
        result = self.session.submit(response)
        self.emit(render.feedback_block(result, self._active_question or {}, self.show_transcript))
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

    def pack_completions(self) -> list[str]:
        """Pack ids (plus pinned refs) offered by /take autocompletion."""
        return self._cached_completions("packs", self._build_pack_completions)

    def _build_pack_completions(self) -> list[str]:
        try:
            packs = list_packs(self.library_dir)
        except (OSError, ValueError, KeyError):
            return []
        refs: list[str] = []
        for pack in packs:
            pack_id = str(pack.get("pack_id", ""))
            if pack_id and pack_id not in refs:
                refs.append(pack_id)
            refs.append(f"{pack_id}@{pack.get('pack_version', '')}")
        return refs

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

    def _open_pack_picker(self, action: str) -> bool:
        """Numbered pack chooser for no-argument /take, /flashcards, /dictation."""
        if self.session is not None:
            return False
        try:
            packs = list_packs(self.library_dir)
        except (OSError, ValueError, KeyError):
            packs = []
        if not packs:
            return False
        self._pack_pick_refs = [f"{pack['pack_id']}@{pack['pack_version']}" for pack in packs]
        self._pack_pick_action = action
        self.emit(render.rule(f"Pick a pack to {action}"))
        for index, pack in enumerate(packs, start=1):
            meta = f"{self._pack_pick_refs[index - 1]} · {pack.get('question_count', '?')} question(s)"
            self.emit(f"  {ansi.style(str(index), ansi.BOLD, ansi.CYAN)}. {pack['title']}  {ansi.style(meta, ansi.GREY)}")
        self.emit("Type the number, or press Enter to cancel.")
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
            handler = {"take": self.cmd_take, "flashcards": self.cmd_flashcards, "dictation": self.cmd_dictation}[action]
            handler(ref)
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
        )

    def readline(self) -> str:
        return self._session.prompt("❯ ")


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
            if name in {"take", "flashcards", "cards", "dictation", "typing", "grammar", "gram"}:
                for ref in shell.pack_completions():
                    if ref.startswith(argument):
                        yield Completion(ref, start_position=-len(argument), display=ref)
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


def run_shell(
    library_dir: str | Path = DEFAULT_LIBRARY_DIR,
    attempt_dir: str | Path = DEFAULT_ATTEMPT_DIR,
    tts_config: TTSConfig | None = None,
    show_transcript: bool = False,
    audio_enabled: bool = True,
    keyboard_hints: bool = False,
    keyboard_pinned: bool = False,
    input_fn: Callable[[str], str] | None = None,
) -> int:
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
