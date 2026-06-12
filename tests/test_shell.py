import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from topik_sim.attempts import (
    answer_question,
    complete_attempt,
    create_attempt,
    load_attempt,
    save_attempt_to_dir,
)
from topik_sim.cli import main
from topik_sim.content import load_pack
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import ANSWERING, CONTINUE, IDLE, PICK, Shell


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


class StubPrefetcher:
    def __init__(self):
        self.scheduled = []

    def schedule(self, texts, config):
        self.scheduled.append(list(texts))

    def close(self):
        pass


def listening_pack_data():
    def question(question_id, order, transcript):
        return {
            "question_id": question_id,
            "order": order,
            "skill": "listening",
            "audio_ref": f"transcript-only:{question_id}",
            "passage": f"Transcript: {transcript}",
            "prompt": "What is being said?",
            "options": [
                {"id": "A", "text": "greeting"},
                {"id": "B", "text": "thanks"},
            ],
            "answer": {"type": "single_choice", "correct_option_id": "A"},
            "explanation": {"summary": "Listen for the keyword."},
        }

    return {
        "schema_version": "topik-sim.content.v1",
        "pack_id": "listen-pack",
        "pack_version": "0.0.1",
        "title": "Listening Pack",
        "topik_level": "TOPIK_I",
        "language_pair": "ko-en",
        "source_type": "original",
        "sections": [
            {
                "section_id": "listening",
                "title": "Listening",
                "questions": [
                    question("l-001", 1, "안녕하세요."),
                    question("l-002", 2, "감사합니다."),
                ],
            }
        ],
    }


class ShellTests(unittest.TestCase):
    def setUp(self):
        ansi.set_color_enabled(False)
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)

    def tearDown(self):
        ansi.set_color_enabled(None)
        self._temp.cleanup()

    def make_shell(self, **kwargs):
        output = []
        prefetcher = StubPrefetcher()
        shell = Shell(
            library_dir=self.temp_dir / "library",
            attempt_dir=self.temp_dir / "attempts",
            tts_config=TTSConfig(output_dir=self.temp_dir / "audio"),
            output=output.append,
            prefetcher=prefetcher,
            **kwargs,
        )
        return shell, output, prefetcher

    def feed(self, shell, lines):
        for line in lines:
            shell.handle_line(line)

    def test_full_take_flow_reaches_summary(self):
        shell, output, _ = self.make_shell()
        self.feed(shell, [f"/take {SAMPLE_PACK}", "B", "", "A", ""])
        text = "\n".join(output)
        self.assertIn("Question 1/2", text)
        self.assertIn("✓ Correct.", text)
        self.assertIn("Score: 2/2", text)
        self.assertEqual(shell.state, IDLE)
        self.assertIsNone(shell.session)
        saved = list((self.temp_dir / "attempts").glob("*.json"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(load_attempt(saved[0])["status"], "completed")

    def test_say_is_intercepted_and_does_not_answer(self):
        shell, output, _ = self.make_shell()
        calls = []

        def fake_synthesize(texts, config):
            calls.append((list(texts), config.playback))
            return []

        with patch("topik_sim.ui.shell.synthesize_many", side_effect=fake_synthesize):
            self.feed(shell, [f"/take {SAMPLE_PACK}", "/say 안녕하세요"])

        self.assertEqual(calls, [(["안녕하세요"], True)])
        self.assertEqual(shell.state, ANSWERING)
        self.assertEqual(shell.session.progress(), (0, 2))

    def test_skip_submits_blank_answer(self):
        shell, output, _ = self.make_shell()
        self.feed(shell, [f"/take {SAMPLE_PACK}", "/skip"])
        text = "\n".join(output)
        self.assertIn("Skipped", text)
        self.assertIn("✗ Not quite.", text)
        self.assertEqual(shell.state, CONTINUE)
        self.assertEqual(shell.session.progress(), (1, 2))

    def test_pause_then_resume_continues_attempt(self):
        shell, output, _ = self.make_shell()
        self.feed(shell, [f"/take {SAMPLE_PACK}", "B", "", "/pause"])
        self.assertEqual(shell.state, IDLE)
        self.assertIsNone(shell.session)

        self.feed(shell, ["/resume", "A", ""])
        text = "\n".join(output)
        self.assertIn("Resuming: 1/2 answered", text)
        self.assertIn("Score: 2/2", text)
        self.assertEqual(shell.state, IDLE)

    def _save_attempt(self, responses, updated_at, completed=False):
        pack = load_pack(SAMPLE_PACK)
        attempt = create_attempt(pack)
        for response in responses:
            attempt = answer_question(attempt, pack, response)
        if completed:
            attempt = complete_attempt(attempt, pack)
        attempt["updated_at"] = updated_at
        return save_attempt_to_dir(attempt, self.temp_dir / "attempts")

    def test_resume_picker_lists_choices_and_resumes_selection(self):
        newest = self._save_attempt(["B"], "2026-06-09T10:00:00+00:00")
        oldest = self._save_attempt([], "2026-06-08T10:00:00+00:00")
        shell, output, _ = self.make_shell()

        self.feed(shell, ["/resume"])
        text = "\n".join(output)
        self.assertEqual(shell.state, PICK)
        self.assertIn("Pick an attempt to resume", text)
        self.assertIn(f"1. in_progress · 1/2 answered · topik-i-mini-pack@0.1.0 · 2026-06-09 10:00 · {newest.name}", text)
        self.assertIn(f"2. in_progress · 0/2 answered", text)

        output.clear()
        self.feed(shell, ["2", "B", "", "A", ""])
        text = "\n".join(output)
        self.assertIn("Resuming: 0/2 answered", text)
        self.assertIn("Score: 2/2", text)
        self.assertEqual(load_attempt(oldest)["status"], "completed")
        self.assertEqual(load_attempt(newest)["status"], "in_progress")

    def test_resume_picker_cancels_and_rejects_bad_input(self):
        self._save_attempt(["B"], "2026-06-09T10:00:00+00:00")
        self._save_attempt([], "2026-06-08T10:00:00+00:00")
        shell, output, _ = self.make_shell()
        self.feed(shell, ["/resume", "7", "x"])
        text = "\n".join(output)
        self.assertEqual(text.count("Enter a number from 1 to 2"), 2)
        self.assertEqual(shell.state, PICK)

        self.feed(shell, [""])
        self.assertIn("Cancelled.", "\n".join(output))
        self.assertEqual(shell.state, IDLE)

    def test_resume_with_single_candidate_skips_picker(self):
        self._save_attempt(["B"], "2026-06-09T10:00:00+00:00")
        shell, output, _ = self.make_shell()
        self.feed(shell, ["/resume"])
        self.assertEqual(shell.state, ANSWERING)
        self.assertIn("Resuming: 1/2 answered", "\n".join(output))

    def test_drill_picker_for_multiple_completed_attempts(self):
        self._save_attempt(["B", "C"], "2026-06-09T10:00:00+00:00", completed=True)
        self._save_attempt(["C", "A"], "2026-06-08T10:00:00+00:00", completed=True)
        shell, output, _ = self.make_shell()
        self.feed(shell, ["/drill"])
        self.assertEqual(shell.state, PICK)
        self.assertIn("Pick an attempt to drill", "\n".join(output))

        output.clear()
        self.feed(shell, ["2"])
        text = "\n".join(output)
        # The older attempt missed r-001, so the drill asks exactly that question.
        self.assertIn("1 missed question(s)", text)
        self.assertIn("r-001", text)
        self.assertEqual(shell.state, ANSWERING)

    def test_completion_results_are_briefly_cached(self):
        from topik_sim.library import import_pack

        import_pack(SAMPLE_PACK, self.temp_dir / "library")
        shell, _, _ = self.make_shell()
        with patch("topik_sim.ui.shell.list_packs", wraps=__import__("topik_sim.library", fromlist=["list_packs"]).list_packs) as spy:
            first = shell.pack_completions()
            second = shell.pack_completions()
        self.assertEqual(first, second)
        self.assertEqual(spy.call_count, 1)

    def test_attempt_completion_items_match_recent_indices(self):
        self._save_attempt(["B"], "2026-06-09T10:00:00+00:00")
        self._save_attempt(["B", "C"], "2026-06-08T10:00:00+00:00", completed=True)
        shell, _, _ = self.make_shell()
        resume_items = shell.attempt_completion_items("resume")
        drill_items = shell.attempt_completion_items("drill")
        self.assertEqual([value for value, _ in resume_items], ["1"])
        self.assertEqual([value for value, _ in drill_items], ["2"])
        self.assertIn("in_progress · 1/2", resume_items[0][1])
        self.assertIn("completed · 2/2", drill_items[0][1])

    def test_drill_replays_only_missed_questions(self):
        shell, output, _ = self.make_shell()
        # Miss r-002 (correct is A), then drill it.
        self.feed(shell, [f"/take {SAMPLE_PACK}", "B", "", "C", ""])
        self.assertIn("Tip: /drill 1", "\n".join(output))

        output.clear()
        self.feed(shell, ["/drill", "A", ""])
        text = "\n".join(output)
        self.assertIn("1 missed question(s)", text)
        self.assertIn("Question 1/1", text)
        self.assertIn("r-002", text)
        self.assertIn("Score: 1/1", text)

        attempts = [load_attempt(path) for path in (self.temp_dir / "attempts").glob("*.json")]
        drills = [attempt for attempt in attempts if attempt.get("activity") == "drill"]
        self.assertEqual(len(drills), 1)
        self.assertEqual(drills[0]["question_ids"], ["r-002"])

    def test_hint_reveals_vocabulary_one_item_at_a_time(self):
        shell, output, _ = self.make_shell()
        self.feed(shell, ["/hint"])
        self.assertIn("Hints are available while a question", "\n".join(output))

        output.clear()
        self.feed(shell, [f"/take {SAMPLE_PACK}", "/hint", "/hint", "/hint", "/hint"])
        text = "\n".join(output)
        self.assertIn("Hint 1/3: 오늘: today", text)
        self.assertIn("Hint 3/3", text)
        self.assertIn("No more hints", text)
        self.assertEqual(shell.state, ANSWERING)

    def test_take_suggests_close_pack_ids(self):
        from topik_sim.library import import_pack

        import_pack(SAMPLE_PACK, self.temp_dir / "library")
        shell, output, _ = self.make_shell()
        self.feed(shell, ["/take topik-i-mini-pak"])
        text = "\n".join(output)
        self.assertIn("was not found", text)
        self.assertIn("Did you mean: topik-i-mini-pack?", text)

    def test_pack_completions_dedupe_versions_and_carry_meta(self):
        import json as json_module

        from topik_sim.library import import_pack

        import_pack(SAMPLE_PACK, self.temp_dir / "library")
        shell, _, _ = self.make_shell()
        completions = shell.pack_completions()
        refs = [ref for ref, _ in completions]
        # One imported version: the bare id only — no redundant pinned twin.
        self.assertEqual(refs, ["topik-i-mini-pack"])
        self.assertEqual(completions[0][1], "TOPIK I Mini Pack · 2 q")

        # A second version earns pinned refs for both.
        data = json_module.loads(SAMPLE_PACK.read_text(encoding="utf-8"))
        data["pack_version"] = "0.2.0"
        newer = self.temp_dir / "mini_v2.json"
        newer.write_text(json_module.dumps(data, ensure_ascii=False), encoding="utf-8")
        import_pack(newer, self.temp_dir / "library")
        shell._completion_cache.clear()
        refs = [ref for ref, _ in shell.pack_completions()]
        self.assertEqual(
            refs,
            ["topik-i-mini-pack", "topik-i-mini-pack@0.1.0", "topik-i-mini-pack@0.2.0"],
        )

    def test_prompt_style_constructs(self):
        from topik_sim.ui.shell import _make_style

        style = _make_style()
        self.assertTrue(style.style_rules)

    def test_unknown_command_and_help(self):
        shell, output, _ = self.make_shell()
        self.feed(shell, ["/nope", "/help"])
        text = "\n".join(output)
        self.assertIn("Unknown command: /nope", text)
        self.assertIn("/say [text]", text)
        self.assertIn("/help <command> explains its arguments", text)

    def test_help_for_one_command_explains_arguments(self):
        shell, output, _ = self.make_shell()
        self.feed(shell, ["/help typing"])
        text = "\n".join(output)
        self.assertIn("Usage: /typing [pack] [count]", text)
        self.assertIn("from every imported pack", text)
        self.assertIn("/typing topik-i-mini-pack 15", text)

        output.clear()
        self.feed(shell, ["/help kb"])  # aliases resolve too
        self.assertIn("Usage: /keyboard", "\n".join(output))

        output.clear()
        self.feed(shell, ["/help nonsense"])
        self.assertIn("Unknown command: /nonsense", "\n".join(output))

    def test_every_command_documents_its_arguments(self):
        from topik_sim.ui.commands import COMMANDS

        missing = [command.name for command in COMMANDS if not command.details.strip()]
        self.assertEqual(missing, [])

    def test_tts_settings_change_at_runtime(self):
        shell, output, _ = self.make_shell()
        self.feed(shell, ["/tts volume 0.5", "/tts provider bogus", "/tts off"])
        text = "\n".join(output)
        self.assertEqual(shell.tts_config.volume, 0.5)
        self.assertIn("Provider must be one of", text)
        self.assertFalse(shell.audio_enabled)

    def test_replay_without_audio_reports_gently(self):
        shell, output, _ = self.make_shell()
        self.feed(shell, ["/replay"])
        self.assertIn("No question audio is available to replay.", "\n".join(output))

    def test_listening_question_plays_audio_and_prefetches_next(self):
        pack_path = self.temp_dir / "listen_pack.json"
        pack_path.write_text(json.dumps(listening_pack_data(), ensure_ascii=False), encoding="utf-8")
        shell, output, prefetcher = self.make_shell()

        def fake_synthesize(texts, config):
            return [self.temp_dir / "audio" / f"{index}.wav" for index, _ in enumerate(texts)]

        with patch("topik_sim.ui.shell.synthesize_many", side_effect=fake_synthesize):
            self.feed(shell, [f"/take {pack_path}"])

        self.assertTrue(shell.current_audio)
        self.assertEqual(prefetcher.scheduled, [["감사합니다."]])
        text = "\n".join(output)
        self.assertIn("[listening]", text)
        # With playable audio the transcript stays hidden until after the answer.
        self.assertNotIn("audio unavailable", text)
        self.assertNotIn("Transcript: 안녕하세요.", text)

    def test_listening_with_audio_reveals_transcript_after_answer_only(self):
        pack_path = self.temp_dir / "listen_pack.json"
        pack_path.write_text(json.dumps(listening_pack_data(), ensure_ascii=False), encoding="utf-8")
        shell, output, _ = self.make_shell()

        def fake_synthesize(texts, config):
            return [self.temp_dir / "audio" / f"{index}.wav" for index, _ in enumerate(texts)]

        with patch("topik_sim.ui.shell.synthesize_many", side_effect=fake_synthesize):
            self.feed(shell, [f"/take {pack_path}", "A"])
        text = "\n".join(output)
        self.assertIn("Transcript: 안녕하세요.", text)
        self.assertEqual(text.count("Transcript: 안녕하세요."), 1)
        self.assertEqual(shell.state, CONTINUE)

    def test_listening_without_audio_shows_transcript_before_answer(self):
        pack_path = self.temp_dir / "listen_pack.json"
        pack_path.write_text(json.dumps(listening_pack_data(), ensure_ascii=False), encoding="utf-8")
        shell, output, _ = self.make_shell()
        with patch("topik_sim.ui.shell.synthesize_many", return_value=[]):
            self.feed(shell, [f"/take {pack_path}"])
        text = "\n".join(output)
        self.assertIn("(audio unavailable — transcript shown)", text)
        self.assertIn("Transcript: 안녕하세요.", text)
        self.assertEqual(shell.state, ANSWERING)

    def test_tts_off_listening_exam_is_fully_usable(self):
        pack_path = self.temp_dir / "listen_pack.json"
        pack_path.write_text(json.dumps(listening_pack_data(), ensure_ascii=False), encoding="utf-8")
        shell, output, _ = self.make_shell()
        self.feed(shell, ["/tts off", f"/take {pack_path}", "A", "", "A", ""])
        text = "\n".join(output)
        self.assertIn("(audio unavailable — transcript shown)", text)
        self.assertIn("Transcript: 안녕하세요.", text)
        self.assertIn("Transcript: 감사합니다.", text)
        # Shown before the answer, and not repeated in the feedback block.
        self.assertEqual(text.count("Transcript: 안녕하세요."), 1)
        self.assertIn("Score: 2/2", text)
        self.assertEqual(shell.state, IDLE)
        self.assertIsNone(shell.session)

    def test_show_transcript_mode_skips_unavailable_audio_notice(self):
        pack_path = self.temp_dir / "listen_pack.json"
        pack_path.write_text(json.dumps(listening_pack_data(), ensure_ascii=False), encoding="utf-8")
        shell, output, _ = self.make_shell(show_transcript=True)
        self.feed(shell, ["/tts off", f"/take {pack_path}"])
        text = "\n".join(output)
        # The transcript is already on the question card; no duplicate reveal.
        self.assertNotIn("audio unavailable", text)
        self.assertIn("Transcript: 안녕하세요.", text)

    def test_transcript_command_reveals_listening_passage(self):
        pack_path = self.temp_dir / "listen_pack.json"
        pack_path.write_text(json.dumps(listening_pack_data(), ensure_ascii=False), encoding="utf-8")
        shell, output, _ = self.make_shell()
        with patch("topik_sim.ui.shell.synthesize_many", return_value=[]):
            self.feed(shell, [f"/take {pack_path}", "/transcript"])
        self.assertIn("Transcript: 안녕하세요.", "\n".join(output))

    def test_flashcards_flip_grade_and_summarize(self):
        shell, output, _ = self.make_shell(flashcard_seed=0)
        self.feed(shell, [f"/flashcards {SAMPLE_PACK}"])
        text = "\n".join(output)
        self.assertIn("6 card(s)", text)
        self.assertIn("Card 1/6", text)

        # Flip and grade every card: know the first three, miss the rest.
        lines = []
        for index in range(6):
            lines.extend(["", "y" if index < 3 else "n"])
        output.clear()
        self.feed(shell, lines)
        text = "\n".join(output)
        self.assertIn("Card 6/6", text)
        self.assertIn("Knew 3/6.", text)
        self.assertIn("Review again:", text)
        self.assertEqual(shell.state, IDLE)

    def test_flashcards_pause_stops_early(self):
        shell, output, _ = self.make_shell(flashcard_seed=0)
        self.feed(shell, [f"/flashcards {SAMPLE_PACK}", "", "y", "/pause"])
        text = "\n".join(output)
        self.assertIn("Flashcards stopped after 1/6", text)
        self.assertEqual(shell.state, IDLE)

    def test_flashcards_say_without_text_speaks_current_card(self):
        shell, output, _ = self.make_shell(flashcard_seed=0)
        calls = []

        def fake_synthesize(texts, config):
            calls.append(list(texts))
            return []

        with patch("topik_sim.ui.shell.synthesize_many", side_effect=fake_synthesize):
            self.feed(shell, [f"/flashcards {SAMPLE_PACK}", "/say"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], shell._flash_deck[0]["speech"])

    def test_flashcards_blocked_during_test(self):
        shell, output, _ = self.make_shell()
        self.feed(shell, [f"/take {SAMPLE_PACK}", f"/flashcards {SAMPLE_PACK}"])
        self.assertIn("Finish or /pause the current test first.", "\n".join(output))

    def test_enter_at_idle_opens_menu_and_navigates_to_a_command(self):
        from topik_sim.ui.shell import MENU, MENU_CATEGORY

        shell, output, _ = self.make_shell()
        self.feed(shell, [""])
        text = "\n".join(output)
        self.assertEqual(shell.state, MENU)
        self.assertIn("Take a test", text)
        self.assertIn("Practice", text)
        self.assertIn("/take", text)

        output.clear()
        self.feed(shell, ["3"])  # Progress
        text = "\n".join(output)
        self.assertEqual(shell.state, MENU_CATEGORY)
        self.assertIn("/stats", text)

        output.clear()
        self.feed(shell, ["3"])  # /stats inside Progress
        text = "\n".join(output)
        self.assertIn("→ /stats", text)
        self.assertIn("No completed attempts yet", text)
        self.assertEqual(shell.state, IDLE)

    def test_menu_enter_goes_back_then_closes(self):
        from topik_sim.ui.shell import MENU

        shell, output, _ = self.make_shell()
        self.feed(shell, ["", "1", ""])  # open, into category, back
        self.assertEqual(shell.state, MENU)
        self.feed(shell, [""])
        self.assertIn("Menu closed.", "\n".join(output))
        self.assertEqual(shell.state, IDLE)

    def test_menu_blocked_during_question(self):
        shell, output, _ = self.make_shell()
        self.feed(shell, [f"/take {SAMPLE_PACK}", "/menu"])
        self.assertIn("Finish the current activity first", "\n".join(output))
        self.assertEqual(shell.state, ANSWERING)

    def test_take_without_argument_opens_pack_picker(self):
        from topik_sim.library import import_pack
        from topik_sim.ui.shell import PICK_PACK

        import_pack(SAMPLE_PACK, self.temp_dir / "library")
        shell, output, _ = self.make_shell()
        self.feed(shell, ["/take"])
        text = "\n".join(output)
        self.assertEqual(shell.state, PICK_PACK)
        self.assertIn("Pick a pack to take", text)
        self.assertIn("topik-i-mini-pack@0.1.0", text)

        output.clear()
        self.feed(shell, ["1"])
        text = "\n".join(output)
        self.assertIn("Question 1/2", text)
        self.assertEqual(shell.state, ANSWERING)

    def test_pack_picker_cancel_and_empty_library(self):
        shell, output, _ = self.make_shell()
        self.feed(shell, ["/take"])  # empty library: no picker, usage instead
        self.assertIn("No packs are imported yet", "\n".join(output))
        self.assertEqual(shell.state, IDLE)

        from topik_sim.library import import_pack

        import_pack(SAMPLE_PACK, self.temp_dir / "library")
        output.clear()
        self.feed(shell, ["/flashcards", ""])
        text = "\n".join(output)
        self.assertIn("Pick a pack to flashcards", text)
        self.assertIn("Cancelled.", text)
        self.assertEqual(shell.state, IDLE)

    def test_dictation_without_argument_uses_picker(self):
        from topik_sim.library import import_pack
        from topik_sim.ui.shell import PICK_PACK

        import_pack(SAMPLE_PACK, self.temp_dir / "library")
        shell, output, _ = self.make_shell()
        self.feed(shell, ["/dictation"])
        self.assertEqual(shell.state, PICK_PACK)
        self.feed(shell, ["1"])
        # The mini pack has no listening transcripts, so dictation reports that.
        self.assertIn("no listening transcripts", "\n".join(output))

    def test_help_is_grouped_by_category(self):
        shell, output, _ = self.make_shell()
        self.feed(shell, ["/help"])
        text = "\n".join(output)
        for category in ("Take a test", "Practice", "Progress", "Library & settings", "While answering", "Shell"):
            self.assertIn(category, text)
        self.assertIn("/menu", text)

    def test_quit_returns_false_to_stop_loop(self):
        shell, output, _ = self.make_shell()
        self.assertTrue(shell.handle_line("/status"))
        self.assertFalse(shell.handle_line("/quit"))

    def test_main_without_arguments_launches_shell(self):
        with patch("topik_sim.ui.shell.run_shell", return_value=0) as run:
            exit_code = main([])
        self.assertEqual(exit_code, 0)
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
