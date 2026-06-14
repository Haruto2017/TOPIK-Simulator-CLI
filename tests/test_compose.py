import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from topik_sim.compose import (
    DEFAULT_COMPOSE_PATH,
    accepted_answers,
    collect_pack_grammar,
    filter_lessons,
    is_correct,
    lesson_pack_evidence,
    lesson_sentences,
    load_lessons,
    normalize_answer,
)
from topik_sim.library import import_pack
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi, render
from topik_sim.ui.shell import COMPOSE_GRADE, COMPOSE_PICK, COMPOSE_TYPE, IDLE, Shell

try:
    from test_shell import StubPrefetcher
except ImportError:
    from tests.test_shell import StubPrefetcher


ROOT = Path(__file__).resolve().parents[1]
BUNDLED_COMPOSE = ROOT / "content" / "compose"
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"

SAMPLE_LESSONS = [
    {
        "id": "want-to",
        "pattern": "-고 싶다",
        "meaning": "to want to",
        "example": "가고 싶어요.",
        "example_en": "I want to go.",
        "note": "**-고 싶어요**",
        "match": ["고 싶"],
        "sentences": [
            {"english": "I want to eat.", "korean": "먹고 싶어요.", "accepted": ["먹고 싶어요.", "먹고 싶습니다."]},
            {"english": "I want to sleep.", "korean": "자고 싶어요.", "accepted": ["자고 싶어요."]},
        ],
    },
    {
        "id": "location",
        "pattern": "N에서",
        "meaning": "at (action place)",
        "example": "집에서 쉬어요.",
        "example_en": "I rest at home.",
        "match": ["에서"],
        "sentences": [
            {"english": "I study at the library.", "korean": "도서관에서 공부해요.", "accepted": ["도서관에서 공부해요."]},
        ],
    },
]


def _lessons_file(directory):
    path = Path(directory) / "lessons.json"
    path.write_text(json.dumps({"schema_version": "topik-sim.compose.v1", "lessons": SAMPLE_LESSONS}, ensure_ascii=False), encoding="utf-8")
    return path


class ComposeModuleTests(unittest.TestCase):
    def test_load_and_validate(self):
        self.assertEqual(load_lessons("nope/x.json"), [])
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "bad.json").write_text("{nope", encoding="utf-8")
            self.assertEqual(load_lessons(Path(d) / "bad.json"), [])
            # lessons without a pattern or without sentences are dropped
            partial = {"lessons": [{"pattern": "x", "sentences": []}, {"sentences": [{"english": "a", "korean": "ㄱ"}]}, SAMPLE_LESSONS[0]]}
            (Path(d) / "p.json").write_text(json.dumps(partial, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(len(load_lessons(Path(d) / "p.json")), 1)

    def test_filter_and_sentences(self):
        self.assertEqual(len(filter_lessons(SAMPLE_LESSONS, "싶")), 1)
        self.assertEqual([l["id"] for l in filter_lessons(SAMPLE_LESSONS, "location")], ["location"])
        self.assertEqual(len(lesson_sentences(SAMPLE_LESSONS[0])), 2)

    def test_grading_tolerant(self):
        s = SAMPLE_LESSONS[0]["sentences"][0]
        self.assertEqual(normalize_answer("  먹고  싶어요. "), "먹고 싶어요")
        self.assertTrue(is_correct(s, "먹고 싶어요"))
        self.assertTrue(is_correct(s, "먹고 싶습니다."))
        self.assertFalse(is_correct(s, "자고 싶어요."))
        self.assertEqual(accepted_answers({"korean": "안녕"}), ["안녕"])

    def test_pack_evidence_grounds_in_pack_grammar(self):
        with tempfile.TemporaryDirectory() as d:
            library = Path(d) / "library"
            import_pack(SAMPLE_PACK, library)
            grammar = collect_pack_grammar(library)
            # the mini pack teaches N에서, so the location lesson is grounded
            location = next(l for l in SAMPLE_LESSONS if l["id"] == "location")
            evidence = lesson_pack_evidence(location, grammar)
            self.assertGreaterEqual(evidence["count"], 1)
            self.assertTrue(evidence["packs"])
            # a pattern the pack does not teach yields no evidence
            absent = {"pattern": "-습니까", "match": ["을까요"], "sentences": [{"english": "x", "korean": "ㄱ"}]}
            self.assertEqual(lesson_pack_evidence(absent, grammar)["count"], 0)


class BundledComposeTests(unittest.TestCase):
    def test_default_path_and_bundled_lessons(self):
        self.assertEqual(Path(DEFAULT_COMPOSE_PATH), Path("content") / "compose")
        lessons = load_lessons(BUNDLED_COMPOSE)
        self.assertGreaterEqual(len(lessons), 5)
        ids = [l["id"] for l in lessons]
        self.assertEqual(len(ids), len(set(ids)), "lesson ids must be unique")
        for lesson in lessons:
            self.assertTrue(lesson["pattern"] and lesson.get("meaning"))
            sentences = lesson_sentences(lesson)
            self.assertGreaterEqual(len(sentences), 3)
            for s in sentences:
                self.assertTrue(is_correct(s, s["korean"]))  # the model itself passes

    def test_bundled_lessons_are_grounded_in_the_real_library(self):
        # Every bundled lesson's structure should appear in the shipped exams.
        grammar = collect_pack_grammar("content/library")
        if not grammar:
            self.skipTest("no imported packs in this environment")
        lessons = load_lessons(BUNDLED_COMPOSE)
        grounded = [l for l in lessons if lesson_pack_evidence(l, grammar)["count"] > 0]
        self.assertGreaterEqual(len(grounded), len(lessons) - 1)


class ComposeShellTests(unittest.TestCase):
    def setUp(self):
        ansi.set_color_enabled(False)
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        self.compose_path = _lessons_file(self.temp_dir)

    def tearDown(self):
        ansi.set_color_enabled(None)
        self._temp.cleanup()

    def make_shell(self, compose_path=None):
        output = []
        shell = Shell(
            library_dir=self.temp_dir / "library",
            attempt_dir=self.temp_dir / "attempts",
            tts_config=TTSConfig(output_dir=self.temp_dir / "audio"),
            output=output.append,
            prefetcher=StubPrefetcher(),
            flashcard_seed=0,
            compose_path=compose_path or self.compose_path,
        )
        return shell, output

    def test_bare_compose_opens_structure_picker(self):
        shell, output = self.make_shell()
        shell.handle_line("/compose")
        text = "\n".join(output)
        self.assertEqual(shell.state, COMPOSE_PICK)
        self.assertIn("pick a structure", text)
        self.assertIn("-고 싶다", text)

        output.clear()
        shell.handle_line("1")
        text = "\n".join(output)
        self.assertIn("Structure · -고 싶다", text)
        self.assertIn("Now write", text)
        self.assertEqual(shell.state, COMPOSE_TYPE)

    def test_direct_structure_by_substring(self):
        shell, output = self.make_shell()
        shell.handle_line("/compose 싶")
        self.assertIn("Structure · -고 싶다", "\n".join(output))
        self.assertEqual(shell.state, COMPOSE_TYPE)

    def test_exact_pass_then_self_grade_flow(self):
        shell, output = self.make_shell()
        shell.handle_line("/compose 싶")
        first = shell._compose_items[0]["korean"]
        shell.handle_line(first)
        self.assertIn("✓", "\n".join(output))
        self.assertEqual(shell.state, COMPOSE_TYPE)

        # answer the rest wrong to reach the self-grade branch and summary
        output.clear()
        shell.handle_line("몰라요")
        self.assertEqual(shell.state, COMPOSE_GRADE)
        self.assertIn("Model:", "\n".join(output))
        shell.handle_line("n")
        text = "\n".join(output)
        self.assertIn("Correct 1/2.", text)
        self.assertIn("Review again:", text)
        self.assertEqual(shell.state, IDLE)

    def test_say_speaks_the_model(self):
        shell, output = self.make_shell()
        calls = []
        with patch("topik_sim.ui.shell.synthesize_many", side_effect=lambda t, c: calls.append(list(t)) or []):
            shell.handle_line("/compose 싶")
            shell.handle_line("/say")
        self.assertEqual(calls, [[shell._compose_items[0]["korean"]]])

    def test_pause_from_picker_and_drill(self):
        shell, output = self.make_shell()
        shell.handle_line("/compose")
        shell.handle_line("/pause")
        self.assertEqual(shell.state, IDLE)

        shell.handle_line("/compose 싶")
        output.clear()
        shell.handle_line("/pause")
        self.assertIn("stopped after 0/2", "\n".join(output))
        self.assertEqual(shell.state, IDLE)

    def test_structure_card_shows_pack_evidence(self):
        import_pack(SAMPLE_PACK, self.temp_dir / "library")
        shell, output = self.make_shell()
        shell.handle_line("/compose location")
        self.assertIn("From your packs", "\n".join(output))

    def test_empty_lessons_reports_gently(self):
        shell, output = self.make_shell(compose_path=self.temp_dir / "absent")
        shell.handle_line("/compose")
        self.assertIn("No writing lessons are available", "\n".join(output))
        self.assertEqual(shell.state, IDLE)


if __name__ == "__main__":
    unittest.main()
