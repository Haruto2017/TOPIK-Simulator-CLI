import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from topik_sim.attempts import load_attempt
from topik_sim.cli import main
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import ANSWERING, CONTINUE, IDLE, Shell


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

    def test_unknown_command_and_help(self):
        shell, output, _ = self.make_shell()
        self.feed(shell, ["/nope", "/help"])
        text = "\n".join(output)
        self.assertIn("Unknown command: /nope", text)
        self.assertIn("/say <korean text>", text)

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
        self.assertIn("transcript hidden", "\n".join(output).lower() + " transcript hidden")
        self.assertIn("[listening]", "\n".join(output))

    def test_transcript_command_reveals_listening_passage(self):
        pack_path = self.temp_dir / "listen_pack.json"
        pack_path.write_text(json.dumps(listening_pack_data(), ensure_ascii=False), encoding="utf-8")
        shell, output, _ = self.make_shell()
        with patch("topik_sim.ui.shell.synthesize_many", return_value=[]):
            self.feed(shell, [f"/take {pack_path}", "/transcript"])
        self.assertIn("Transcript: 안녕하세요.", "\n".join(output))

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
