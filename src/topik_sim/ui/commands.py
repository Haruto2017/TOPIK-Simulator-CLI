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

    def tokens(self) -> list[str]:
        return [f"/{self.name}"] + [f"/{alias}" for alias in self.aliases]


COMMANDS: list[Command] = [
    Command("help", "cmd_help", "/help", "Show available commands.", ("h", "?")),
    Command("take", "cmd_take", "/take <pack> [section] [limit]", "Start a test from the library or a pack file."),
    Command("resume", "cmd_resume", "/resume [n|path]", "Resume a recent in-progress attempt."),
    Command("drill", "cmd_drill", "/drill [n|path]", "Re-practice the questions missed in a completed attempt."),
    Command("attempts", "cmd_attempts", "/attempts", "List recent attempts."),
    Command("packs", "cmd_packs", "/packs", "List imported content packs."),
    Command("say", "cmd_say", "/say <korean text>", "Pronounce any sentence aloud; does not touch your answer.", ("speak",)),
    Command("hint", "cmd_hint", "/hint", "Reveal one vocabulary hint for the current question."),
    Command("replay", "cmd_replay", "/replay", "Play the current question audio again.", ("r",)),
    Command("transcript", "cmd_transcript", "/transcript", "Reveal the transcript of the current listening question.", ("t",)),
    Command("skip", "cmd_skip", "/skip", "Submit a blank answer for the current question."),
    Command("pause", "cmd_pause", "/pause", "Save the current test and return to idle; resume later."),
    Command("status", "cmd_status", "/status", "Show session progress and speech settings."),
    Command("stats", "cmd_stats", "/stats", "Per-skill accuracy and trends across completed attempts."),
    Command("tts", "cmd_tts", "/tts [on|off|volume <x>|speed <x>|provider <p>|voice <v>]", "Show or change speech settings."),
    Command("quit", "cmd_quit", "/quit", "Exit the shell. Progress is already saved.", ("exit", "q")),
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
