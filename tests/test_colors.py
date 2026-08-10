import tempfile
import unittest
from pathlib import Path

from topik_sim.colors import (
    COLOR_CATEGORIES,
    COLOR_LIST,
    build_color_items,
    cheat_sheet,
    color_by_name,
    topic_particle,
)
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import Shell
from topik_sim.web.app import WebApp


class ColorDataTests(unittest.TestCase):
    def test_every_color_has_a_hex_swatch_and_gloss(self):
        for color in COLOR_LIST:
            self.assertRegex(color["hex"], r"^#[0-9A-Fa-f]{6}$", color["ko"])
            self.assertTrue(color["en"])
            self.assertIn(color["ko"], color["accept"])

    def test_h_irregular_modifiers_are_correct(self):
        """빨갛다 → 빨간: the ㅎ drops before -ㄴ. Wrong forms teach wrong Korean."""
        expected = {
            "빨갛다": "빨간",
            "노랗다": "노란",
            "파랗다": "파란",
            "까맣다": "까만",
            "하얗다": "하얀",
        }
        found = {c["adjective"]: c["modifier"] for c in COLOR_LIST if c.get("adjective")}
        self.assertEqual(found, expected)

    def test_color_lookup_accepts_alternate_forms(self):
        self.assertEqual(color_by_name("빨강")["ko"], "빨간색")
        self.assertEqual(color_by_name("하얀색")["ko"], "흰색")
        self.assertIsNone(color_by_name("무지개색"))

    def test_cheat_sheet_matches_the_drill_data(self):
        sheet = cheat_sheet()
        self.assertEqual(len(sheet["colors"]), len(COLOR_LIST))
        self.assertEqual(len(sheet["irregulars"]), 5)
        self.assertTrue(sheet["usage"])
        for row in sheet["colors"]:
            self.assertNotIn(row["ko"], row["also"])  # "also" lists only alternates


class ColorItemTests(unittest.TestCase):
    def test_mixed_drill_rotates_every_category(self):
        items = build_color_items(seed=1, count=len(COLOR_CATEGORIES))
        self.assertEqual(len(items), len(COLOR_CATEGORIES))
        for item in items:
            self.assertTrue(item["answer"])
            self.assertIn(item["answer"], item["accept"])
            self.assertTrue(item["no_latin"])

    def test_seed_makes_items_reproducible(self):
        self.assertEqual(build_color_items(seed=7, count=6), build_color_items(seed=7, count=6))

    def test_swatch_items_carry_a_color_and_a_fallback_name(self):
        items = build_color_items(seed=3, count=4, category="swatch")
        for item in items:
            self.assertRegex(item["swatch"], r"^#[0-9A-Fa-f]{6}$")
            self.assertTrue(item["swatch_only"])
            self.assertTrue(item["meaning"])  # the English name, for no-color terminals

    def test_modifier_items_use_the_irregular_form_not_the_noun(self):
        items = build_color_items(seed=5, count=8, category="modifier")
        for item in items:
            first = item["answer"].split()[0]
            self.assertFalse(first.endswith("색"), item["answer"])
            self.assertIn(item["answer"].replace(" ", ""), item["accept"])

    def test_object_items_have_no_swatch(self):
        """바나나는 무슨 색이에요? — showing the color would be the answer."""
        for item in build_color_items(seed=2, count=4, category="object"):
            self.assertNotIn("swatch", item)

    def test_object_items_pick_the_right_topic_particle(self):
        self.assertEqual(topic_particle("바나나"), "는")   # ends in a vowel
        self.assertEqual(topic_particle("당근"), "은")     # ends in ㄴ
        self.assertEqual(topic_particle("하늘"), "은")     # ends in ㄹ
        for item in build_color_items(seed=8, count=12, category="object"):
            self.assertNotIn("은/는", item["show"])

    def test_unknown_category_is_rejected(self):
        with self.assertRaises(ValueError):
            build_color_items(category="rainbow")


class AnsiSwatchTests(unittest.TestCase):
    def tearDown(self):
        ansi.set_color_enabled(None)

    def test_swatch_is_empty_without_terminal_color(self):
        ansi.set_color_enabled(False)
        self.assertEqual(ansi.swatch("#E03131"), "")

    def test_swatch_renders_truecolor_background(self):
        ansi.set_color_enabled(True)
        self.assertIn("48;2;224;49;49", ansi.swatch("#E03131"))

    def test_malformed_hex_is_ignored(self):
        ansi.set_color_enabled(True)
        self.assertEqual(ansi.swatch("nope"), "")
        self.assertEqual(ansi.swatch("#GGGGGG"), "")


class ColorShellTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        ansi.set_color_enabled(False)
        self.output: list[str] = []
        self.shell = Shell(
            library_dir=Path(self._temp.name) / "library",
            attempt_dir=Path(self._temp.name) / "attempts",
            tts_config=TTSConfig(output_dir=Path(self._temp.name) / "audio"),
            audio_enabled=False,
            output=self.output.append,
            flashcard_seed=4,
        )

    def tearDown(self):
        ansi.set_color_enabled(None)
        self._temp.cleanup()

    def text(self) -> str:
        return "\n".join(self.output)

    def test_colors_learn_shows_the_reference_table(self):
        self.shell.handle_line("/colors learn")
        body = self.text()
        self.assertIn("빨간색", body)
        self.assertIn("빨갛다 → 빨간", body)
        self.assertIn("무슨 색이에요?", body)

    def test_colors_drill_grades_a_correct_answer(self):
        self.shell.handle_line("/colors word 3")
        self.assertIn("Color practice", self.text())
        item = self.shell._typing_items[0]
        self.output.clear()
        self.shell.handle_line(item["answer"])
        self.assertIn("✓", self.text())

    def test_alternate_color_form_is_accepted(self):
        self.shell.handle_line("/colors word 2")
        self.shell._typing_items[0] = dict(
            self.shell._typing_items[0], answer="빨간색", accept=["빨강", "빨간색"], show="Color:  red"
        )
        self.output.clear()
        self.shell.handle_line("빨강")
        self.assertIn("✓", self.text())

    def test_english_answer_is_rejected_with_a_hangul_hint(self):
        self.shell.handle_line("/colors swatch 2")
        self.output.clear()
        self.shell.handle_line("red")
        self.assertIn("한글", self.text())
        self.assertEqual(self.shell._typing_index, 0)  # still on the same item

    def test_swatch_names_the_color_when_the_terminal_has_no_color(self):
        self.shell.handle_line("/colors swatch 2")
        item = self.shell._typing_items[0]
        self.assertIn(f"({item['meaning']})", self.text())

    def test_unknown_category_is_reported(self):
        self.shell.handle_line("/colors rainbow")
        self.assertIn("Unknown category", self.text())


class ColorWebTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        temp = Path(self._temp.name)
        self.app = WebApp(
            library_dir=temp / "library",
            attempt_dir=temp / "attempts",
            tts_config=TTSConfig(output_dir=temp / "audio"),
            audio_enabled=False,
            seed=4,
        )

    def tearDown(self):
        self._temp.cleanup()

    def test_guide_endpoint_returns_the_cheat_sheet(self):
        status, payload = self.app.handle("GET", "/api/colors/guide")
        self.assertEqual(status, 200)
        self.assertTrue(payload["colors"])
        self.assertEqual(len(payload["irregulars"]), 5)

    def test_drill_serves_a_swatch_and_grades_the_answer(self):
        status, view = self.app.handle("POST", "/api/drill/start",
                                       body={"mode": "colors", "category": "swatch", "count": 3})
        self.assertEqual(status, 200)
        self.assertEqual(view["label"], "Color practice")
        item = view["item"]
        self.assertRegex(item["swatch"], r"^#[0-9A-Fa-f]{6}$")
        self.assertTrue(item["no_latin"])

        activity = view["id"]
        answer = self.app._activities[activity]["items"][0]["answer"]
        status, result = self.app.handle("POST", f"/api/activity/{activity}/answer",
                                         body={"value": answer})
        self.assertEqual(status, 200)
        self.assertTrue(result["correct"])

    def test_english_answer_asks_for_hangul_instead_of_failing(self):
        status, view = self.app.handle("POST", "/api/drill/start",
                                       body={"mode": "colors", "count": 3, "category": "swatch"})
        activity = view["id"]
        status, result = self.app.handle("POST", f"/api/activity/{activity}/answer",
                                         body={"value": "red"})
        self.assertEqual(status, 200)
        self.assertTrue(result["retry"])
        self.assertIn("한글", result["message"])

    def test_colors_mode_needs_no_pack(self):
        status, view = self.app.handle("POST", "/api/drill/start", body={"mode": "colors"})
        self.assertEqual(status, 200)
        self.assertEqual(view["progress"][1], 10)


if __name__ == "__main__":
    unittest.main()
