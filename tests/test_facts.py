import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from topik_sim.cli import main
from topik_sim.facts import DEFAULT_FACTS_PATH, categories, filter_facts, load_facts
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi, render
from topik_sim.ui.shell import IDLE, Shell

try:
    from test_shell import StubPrefetcher
except ImportError:
    from tests.test_shell import StubPrefetcher


ROOT = Path(__file__).resolve().parents[1]
BUNDLED_FACTS = ROOT / "content" / "korea_facts.json"


def _facts_file(directory, facts):
    path = Path(directory) / "facts.json"
    path.write_text(json.dumps({"schema_version": "topik-sim.facts.v1", "facts": facts}, ensure_ascii=False), encoding="utf-8")
    return path


SAMPLE_FACTS = [
    {"id": "h1", "category": "history", "title": "Fact One", "fact": "First.", "korean": "하나입니다.", "korean_en": "It is one."},
    {"id": "f1", "category": "food", "title": "Fact Two", "fact": "Second.", "korean": "둘입니다."},
    {"id": "f2", "category": "food", "title": "Fact Three", "fact": "Third."},
]


class FactsModuleTests(unittest.TestCase):
    def test_load_missing_or_malformed_returns_empty(self):
        self.assertEqual(load_facts("nope/does-not-exist.json"), [])
        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            self.assertEqual(load_facts(bad), [])
            notalist = Path(temp_dir) / "n.json"
            notalist.write_text('{"facts": "x"}', encoding="utf-8")
            self.assertEqual(load_facts(notalist), [])

    def test_categories_and_filter(self):
        self.assertEqual(categories(SAMPLE_FACTS), ["food", "history"])
        self.assertEqual(len(filter_facts(SAMPLE_FACTS, "food")), 2)
        self.assertEqual(len(filter_facts(SAMPLE_FACTS, "")), 3)
        # substring fallback when no exact category matches
        self.assertEqual([f["id"] for f in filter_facts(SAMPLE_FACTS, "one")], ["h1"])
        self.assertEqual(filter_facts(SAMPLE_FACTS, "zzz"), [])


class BundledFactsTests(unittest.TestCase):
    def test_bundled_file_is_well_formed(self):
        facts = load_facts(BUNDLED_FACTS)
        self.assertGreaterEqual(len(facts), 40)
        ids = [f.get("id") for f in facts]
        self.assertEqual(len(ids), len(set(ids)), "fact ids must be unique")
        for fact in facts:
            self.assertTrue(fact.get("id"))
            self.assertTrue(fact.get("category"))
            self.assertTrue(str(fact.get("fact", "")).strip())
        # spans many areas, both historical and current, incl. music/film/pop culture
        cats = set(categories(facts))
        for expected in {"history", "geography", "food", "shopping", "sightseeing",
                         "literature", "music", "film", "pop_culture"}:
            self.assertIn(expected, cats)

    def test_film_facts_match_either_film_or_movie(self):
        # film cards carry a "movie" tag so /facts movie also finds them
        facts = load_facts(BUNDLED_FACTS)
        film_facts = filter_facts(facts, "film")
        self.assertTrue(film_facts)
        movie_matches = filter_facts(facts, "movie")
        self.assertTrue(movie_matches)
        self.assertTrue({f["id"] for f in movie_matches} & {f["id"] for f in film_facts})

    def test_default_path_points_at_bundled_file(self):
        self.assertEqual(Path(DEFAULT_FACTS_PATH), Path("content") / "korea_facts.json")


class FactRenderTests(unittest.TestCase):
    def setUp(self):
        ansi.set_color_enabled(False)

    def tearDown(self):
        ansi.set_color_enabled(None)

    def test_fact_card_includes_all_parts(self):
        card = render.fact_card(
            {
                "category": "pop_culture",
                "title": "T",
                "fact": "Body with **bold**.",
                "korean": "한국어 문장.",
                "korean_en": "Korean sentence.",
                "vocabulary": [{"ko": "노래", "en": "song"}],
                "note": "A **strong** note.",
            }
        )
        self.assertIn("Korea fact · pop culture", card)
        self.assertIn("한국어  한국어 문장.", card)
        self.assertIn("Korean sentence.", card)
        self.assertIn("• 노래: song", card)
        self.assertIn("메모:", card)
        # markdown markers are stripped when color is off
        self.assertIn("Body with bold.", card)
        self.assertNotIn("**", card)

    def test_inline_markdown_styles_when_color_on(self):
        ansi.set_color_enabled(True)
        try:
            rendered = render.inline_markdown("a **b** c")
            self.assertIn("\x1b[", rendered)
            self.assertNotIn("**", rendered)
        finally:
            ansi.set_color_enabled(False)


class FactShellTests(unittest.TestCase):
    def setUp(self):
        ansi.set_color_enabled(False)
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        self.facts_path = _facts_file(self.temp_dir, SAMPLE_FACTS)

    def tearDown(self):
        ansi.set_color_enabled(None)
        self._temp.cleanup()

    def make_shell(self, audio_enabled=True):
        output = []
        shell = Shell(
            library_dir=self.temp_dir / "library",
            attempt_dir=self.temp_dir / "attempts",
            tts_config=TTSConfig(output_dir=self.temp_dir / "audio"),
            output=output.append,
            prefetcher=StubPrefetcher(),
            flashcard_seed=0,
            facts_path=self.facts_path,
            audio_enabled=audio_enabled,
        )
        return shell, output

    def test_facts_shows_a_card_and_stays_idle(self):
        shell, output = self.make_shell(audio_enabled=False)
        shell.handle_line("/facts")
        text = "\n".join(output)
        self.assertIn("Korea fact ·", text)
        self.assertEqual(shell.state, IDLE)

    def test_facts_list_shows_categories(self):
        shell, output = self.make_shell()
        shell.handle_line("/facts list")
        text = "\n".join(output)
        self.assertIn("categories", text)
        self.assertIn("food (2)", text)
        self.assertIn("history (1)", text)

    def test_facts_category_filters(self):
        shell, output = self.make_shell(audio_enabled=False)
        shell.handle_line("/facts history")
        # only the history fact can appear
        self.assertIn("Fact One", "\n".join(output))

    def test_facts_unknown_category_falls_back(self):
        shell, output = self.make_shell(audio_enabled=False)
        shell.handle_line("/facts zzz")
        text = "\n".join(output)
        self.assertIn("No facts match", text)
        self.assertIn("Korea fact ·", text)  # still shows one

    def test_facts_do_not_repeat_until_pool_exhausted(self):
        shell, _ = self.make_shell(audio_enabled=False)
        titles = []
        for _ in range(len(SAMPLE_FACTS)):
            out = []
            shell._output = out.append
            shell.cmd_facts("")
            titles.append(next(line for line in out if "Fact" in line))
        self.assertEqual(len(set(titles)), len(SAMPLE_FACTS), "every fact shown once before repeating")

    def test_say_reads_last_fact_korean_at_idle(self):
        shell, output = self.make_shell()
        calls = []

        def fake_synthesize(texts, config):
            calls.append(list(texts))
            return []

        with patch("topik_sim.ui.shell.synthesize_many", side_effect=fake_synthesize):
            shell.handle_line("/facts history")  # korean: 하나입니다.
            shell.handle_line("/say")
        self.assertEqual(calls, [["하나입니다."]])

    def test_missing_facts_file_reports_gently(self):
        output = []
        shell = Shell(
            library_dir=self.temp_dir / "library",
            attempt_dir=self.temp_dir / "attempts",
            tts_config=TTSConfig(output_dir=self.temp_dir / "audio"),
            output=output.append,
            prefetcher=StubPrefetcher(),
            facts_path=self.temp_dir / "absent.json",
        )
        shell.handle_line("/facts")
        self.assertIn("No facts are available", "\n".join(output))


class FactCliTests(unittest.TestCase):
    def test_facts_cli_prints_a_card(self):
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["facts", "--facts-file", str(BUNDLED_FACTS)])
        self.assertEqual(exit_code, 0)
        self.assertIn("Korea fact ·", output.getvalue())

    def test_facts_cli_list(self):
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["facts", "--list", "--facts-file", str(BUNDLED_FACTS)])
        self.assertEqual(exit_code, 0)
        self.assertIn("history", output.getvalue())

    def test_facts_cli_missing_file(self):
        err = StringIO()
        with redirect_stdout(StringIO()), patch("sys.stderr", err):
            exit_code = main(["facts", "--facts-file", "nope.json"])
        self.assertEqual(exit_code, 1)
        self.assertIn("No facts", err.getvalue())


if __name__ == "__main__":
    unittest.main()
