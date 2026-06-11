from __future__ import annotations

import shlex
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

    # ------------------------------------------------------------- plumbing

    def emit(self, text: str = "") -> None:
        self._output(text)

    def close(self) -> None:
        self.prefetcher.close()

    def status_line(self) -> str:
        tts_state = self.tts_config.provider if self.audio_enabled else "off"
        if self.session is None:
            return f" idle · /take <pack> to start · TTS {tts_state} · /help "
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
        elif text:
            self.emit("No test is running. /take <pack> to start, /help for commands.")
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

    def cmd_help(self, argument: str) -> None:
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
            answered = len(attempt.get("answers", []))
            total = len(attempt.get("question_ids", []))
            status = attempt.get("status", "unknown")
            ref = f"{attempt.get('pack_id', '?')}@{attempt.get('pack_version', '?')}"
            self.emit(f"  {index}. {status} · {answered}/{total} answered · {ref} · {path.name}")
        self.emit("Use /resume <n> or /drill <n>.")

    def cmd_take(self, argument: str) -> None:
        if not argument:
            self.emit("Usage: /take <pack_id[@version]|path> [section] [limit]")
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
        located = self._locate_attempt(argument)
        if located is None:
            return
        path, attempt = located
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
        located = self._locate_attempt(argument, want_completed=True)
        if located is None:
            return
        path, source = located
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

    def cmd_say(self, argument: str) -> None:
        if not argument:
            self.emit("Usage: /say <text> — pronounces the sentence without touching your answer.")
            return
        self._speak([argument], playback=True)

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
        from ..report import build_report

        located = self._locate_attempt(argument, want_completed=True)
        if located is None:
            return
        path, attempt = located
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
        self._refresh_recent()
        self._reset_session()

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

    def pack_completions(self) -> list[str]:
        """Pack ids (plus pinned refs) offered by /take autocompletion."""
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

    def _locate_attempt(self, argument: str, want_completed: bool = False) -> tuple[Path, dict[str, Any]] | None:
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
        for path, attempt in entries:
            if attempt.get("status") == wanted_status:
                return path, attempt
        self.emit(f"No {wanted_status.replace('_', ' ')} attempt found. /attempts lists what is saved.")
        return None

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
            if command_token.lower() == "/take" and " " not in argument:
                for ref in shell.pack_completions():
                    if ref.startswith(argument):
                        yield Completion(ref, start_position=-len(argument), display=ref)

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
    input_fn: Callable[[str], str] | None = None,
) -> int:
    shell = Shell(
        library_dir=library_dir,
        attempt_dir=attempt_dir,
        tts_config=tts_config,
        show_transcript=show_transcript,
        audio_enabled=audio_enabled,
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
