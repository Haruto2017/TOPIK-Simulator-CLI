import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from topik_sim.sentences import (
    DEFAULT_SENTENCES_PATH,
    accepted_answers,
    build_drill,
    filter_sentences,
    is_correct,
    load_sentences,
    normalize_answer,
    topics,
)
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import COMPOSE_GRADE, COMPOSE_TYPE, IDLE, Shell

try:
    from test_shell import StubPrefetcher
except ImportError:
    from tests.test_shell import StubPrefetcher


ROOT = Path(__file__).resolve().parents[1]
BUNDLED_SENTENCES = ROOT / "content" / "sentences"

SAMPLE = [
    {"id": "s1", "topic": "greet", "english": "Hello.", "korean": "안녕하세요.", "accepted": ["안녕하세요."]},
    {"id": "s2", "topic": "greet", "english": "Thank you.", "korean": "감사합니다.", "accepted": ["감사합니다.", "고맙습니다."], "note": "**thanks**"},
    {"id": "s3", "topic": "food", "english": "I eat rice.", "korean": "밥을 먹어요.", "accepted": ["밥을 먹어요."]},
]


def _sentences_file(directory):
    path = Path(directory) / "sample.json"
    path.write_text(json.dumps({"schema_version": "topik-sim.sentences.v1", "sentences": SAMPLE}, ensure_ascii=False), encoding="utf-8")
    return path


class SentencesModuleTests(unittest.TestCase):
    def test_load_missing_or_malformed(self):
        self.assertEqual(load_sentences("nope/x.json"), [])
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            self.assertEqual(load_sentences(bad), [])

    def test_load_drops_items_missing_english_or_korean(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.json"
            path.write_text(json.dumps({"sentences": [{"english": "x"}, {"english": "a", "korean": "ㄱ"}]}, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(len(load_sentences(path)), 1)

    def test_topics_and_filter(self):
        self.assertEqual(topics(SAMPLE), ["food", "greet"])
        self.assertEqual(len(filter_sentences(SAMPLE, "greet")), 2)
        self.assertEqual(len(filter_sentences(SAMPLE, "")), 3)
        self.assertEqual([s["id"] for s in filter_sentences(SAMPLE, "rice")], ["s3"])
        self.assertEqual(filter_sentences(SAMPLE, "zzz"), [])

    def test_accepted_defaults_to_korean(self):
        self.assertEqual(accepted_answers({"korean": "안녕"}), ["안녕"])
        self.assertEqual(accepted_answers(SAMPLE[1]), ["감사합니다.", "고맙습니다."])

    def test_normalize_and_is_correct_tolerant(self):
        self.assertEqual(normalize_answer("  안녕하세요. "), "안녕하세요")
        self.assertEqual(normalize_answer("밥을   먹어요"), "밥을 먹어요")
        item = SAMPLE[0]
        self.assertTrue(is_correct(item, "안녕하세요."))
        self.assertTrue(is_correct(item, "안녕하세요"))   # missing period
        self.assertTrue(is_correct(item, " 안녕하세요. "))  # spacing
        self.assertFalse(is_correct(item, "안녕"))
        self.assertTrue(is_correct(SAMPLE[1], "고맙습니다"))  # accepted variant

    def test_build_drill_count_topic_and_determinism(self):
        self.assertEqual(len(build_drill(SAMPLE, count=2, seed=0)), 2)
        greet = build_drill(SAMPLE, topic="greet", seed=0)
        self.assertTrue(all(s["topic"] == "greet" for s in greet))
        self.assertEqual(build_drill(SAMPLE, seed=0), build_drill(SAMPLE, seed=0))


class BundledSentencesTests(unittest.TestCase):
    def test_default_path_and_bundled_files(self):
        self.assertEqual(Path(DEFAULT_SENTENCES_PATH), Path("content") / "sentences")
        sentences = load_sentences(BUNDLED_SENTENCES)
        self.assertGreaterEqual(len(sentences), 20)
        ids = [s["id"] for s in sentences]
        self.assertEqual(len(ids), len(set(ids)), "sentence ids must be unique")
        for topic_file in sorted(BUNDLED_SENTENCES.glob("*.json")):
            items = load_sentences(topic_file)
            self.assertTrue(items, f"{topic_file.name} empty")
            self.assertEqual({s["topic"] for s in items}, {topic_file.stem})
            for s in items:
                self.assertTrue(s["english"] and s["korean"])
                self.assertTrue(is_correct(s, s["korean"]))  # the model itself passes


class ComposeShellTests(unittest.TestCase):
    def setUp(self):
        ansi.set_color_enabled(False)
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        self.sentences_path = _sentences_file(self.temp_dir)

    def tearDown(self):
        ansi.set_color_enabled(None)
        self._temp.cleanup()

    def make_shell(self, sentences_path=None):
        output = []
        shell = Shell(
            library_dir=self.temp_dir / "library",
            attempt_dir=self.temp_dir / "attempts",
            tts_config=TTSConfig(output_dir=self.temp_dir / "audio"),
            output=output.append,
            prefetcher=StubPrefetcher(),
            flashcard_seed=0,
            sentences_path=sentences_path or self.sentences_path,
        )
        return shell, output

    def test_exact_match_auto_passes(self):
        shell, output = self.make_shell()
        shell.handle_line("/compose 2")
        self.assertEqual(shell.state, COMPOSE_TYPE)
        first = shell._compose_items[0]["korean"]
        shell.handle_line(first)
        self.assertIn("✓", "\n".join(output))
        # advanced straight to the next item — no self-grade step
        self.assertEqual(shell.state, COMPOSE_TYPE)
        second = shell._compose_items[1]["korean"]
        shell.handle_line(second)
        self.assertIn("Correct 2/2.", "\n".join(output))
        self.assertEqual(shell.state, IDLE)

    def test_non_exact_reveals_model_and_self_grades(self):
        shell, output = self.make_shell()
        shell.handle_line("/compose 1")
        model = shell._compose_items[0]["korean"]
        shell.handle_line("모르겠어요")  # not an accepted answer
        text = "\n".join(output)
        self.assertIn(f"Model: {model}", text)
        self.assertEqual(shell.state, COMPOSE_GRADE)
        shell.handle_line("y")
        self.assertIn("Correct 1/1.", "\n".join(output))
        self.assertEqual(shell.state, IDLE)

    def test_self_grade_no_lists_for_review(self):
        shell, output = self.make_shell()
        shell.handle_line("/compose 1")
        shell.handle_line("틀린 답")
        shell.handle_line("n")
        text = "\n".join(output)
        self.assertIn("Correct 0/1.", text)
        self.assertIn("Review again:", text)

    def test_topic_filter_and_fallback(self):
        shell, output = self.make_shell()
        shell.handle_line("/compose food")
        self.assertTrue(all(s["topic"] == "food" for s in shell._compose_items))

        shell2, output2 = self.make_shell()
        shell2.handle_line("/compose zzz")
        self.assertIn("using all topics", "\n".join(output2))
        self.assertEqual(shell2.state, COMPOSE_TYPE)

    def test_pause_stops_early(self):
        shell, output = self.make_shell()
        shell.handle_line("/compose 3")
        shell.handle_line("/pause")
        self.assertIn("stopped after 0/3", "\n".join(output))
        self.assertEqual(shell.state, IDLE)

    def test_say_speaks_the_model(self):
        shell, output = self.make_shell()
        calls = []

        def fake_synthesize(texts, config):
            calls.append(list(texts))
            return []

        with patch("topik_sim.ui.shell.synthesize_many", side_effect=fake_synthesize):
            shell.handle_line("/compose 1")
            shell.handle_line("/say")
        self.assertEqual(calls, [[shell._compose_items[0]["korean"]]])

    def test_empty_sentences_reports_gently(self):
        shell, output = self.make_shell(sentences_path=self.temp_dir / "absent")
        shell.handle_line("/compose")
        self.assertIn("No sentences are available", "\n".join(output))
        self.assertEqual(shell.state, IDLE)


if __name__ == "__main__":
    unittest.main()
