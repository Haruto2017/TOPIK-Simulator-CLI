import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from topik_sim.content import load_pack
from topik_sim.dictation import accuracy, collect_dictation_texts, feedback_lines
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import DICTATION, IDLE, Shell

try:
    from test_shell import StubPrefetcher, listening_pack_data
except ImportError:  # direct module invocation instead of discovery
    from tests.test_shell import StubPrefetcher, listening_pack_data


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


class DictationModuleTests(unittest.TestCase):
    def test_collect_dictation_texts_uses_listening_transcripts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_path = Path(temp_dir) / "pack.json"
            pack_path.write_text(json.dumps(listening_pack_data(), ensure_ascii=False), encoding="utf-8")
            pack = load_pack(pack_path)
            texts = collect_dictation_texts(pack)
            self.assertEqual(texts, ["안녕하세요.", "감사합니다."])
            self.assertEqual(collect_dictation_texts(pack, limit=1), ["안녕하세요."])
        reading_pack = load_pack(SAMPLE_PACK)
        self.assertEqual(collect_dictation_texts(reading_pack), [])

    def test_accuracy_and_feedback(self):
        self.assertEqual(accuracy("안녕하세요.", "안녕하세요."), 1.0)
        self.assertEqual(feedback_lines("안녕하세요.", " 안녕하세요. "), ["Perfect! 100%"])
        lines = feedback_lines("오늘은 날씨가 좋습니다.", "오늘은 좋습니다.")
        text = "\n".join(lines)
        self.assertIn("Accuracy:", text)
        self.assertIn("Missing or wrong: 날씨가", text)

        lines = feedback_lines("좋습니다.", "정말 좋습니다.")
        self.assertIn("Not in the sentence: 정말", "\n".join(lines))


class DictationShellTests(unittest.TestCase):
    def setUp(self):
        ansi.set_color_enabled(False)
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        self.pack_path = self.temp_dir / "listen_pack.json"
        self.pack_path.write_text(json.dumps(listening_pack_data(), ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        ansi.set_color_enabled(None)
        self._temp.cleanup()

    def make_shell(self):
        output = []
        shell = Shell(
            library_dir=self.temp_dir / "library",
            attempt_dir=self.temp_dir / "attempts",
            tts_config=TTSConfig(output_dir=self.temp_dir / "audio"),
            output=output.append,
            prefetcher=StubPrefetcher(),
        )
        return shell, output

    def test_dictation_flow_grades_and_summarizes(self):
        shell, output = self.make_shell()
        spoken = []

        def fake_synthesize(texts, config):
            spoken.append(list(texts))
            return [self.temp_dir / "audio" / "x.wav"]

        with patch("topik_sim.ui.shell.synthesize_many", side_effect=fake_synthesize):
            shell.handle_line(f"/dictation {self.pack_path}")
            self.assertEqual(shell.state, DICTATION)
            shell.handle_line("안녕하세요.")
            shell.handle_line("감사합니다 맞아요")

        text = "\n".join(output)
        self.assertIn("Dictation 1/2", text)
        self.assertIn("Perfect! 100%", text)
        self.assertIn("Dictation 2/2", text)
        self.assertIn("Not in the sentence: 맞아요", text)
        self.assertIn("Average accuracy:", text)
        self.assertIn("perfect 1/2", text)
        self.assertEqual(shell.state, IDLE)
        self.assertEqual(spoken, [["안녕하세요."], ["감사합니다."]])

    def test_dictation_pause_and_empty_input(self):
        shell, output = self.make_shell()
        with patch("topik_sim.ui.shell.synthesize_many", return_value=[]):
            shell.handle_line(f"/dictation {self.pack_path}")
            shell.handle_line("")
            shell.handle_line("/pause")
        text = "\n".join(output)
        self.assertIn("audio unavailable", text)
        self.assertIn("Type what you heard", text)
        self.assertIn("Dictation stopped after 0/2", text)
        self.assertEqual(shell.state, IDLE)


if __name__ == "__main__":
    unittest.main()
