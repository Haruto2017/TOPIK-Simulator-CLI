import tempfile
import unittest
from pathlib import Path

from topik_sim.compose import DEFAULT_COMPOSE_PATH
from topik_sim.courses import DEFAULT_COURSES_PATH
from topik_sim.curriculum import (
    DEFAULT_CURRICULUM_PATH,
    load_curriculum,
    resolve_units,
    unit_status,
)
from topik_sim.dialogues import DEFAULT_DIALOGUES_PATH
from topik_sim.library import import_pack
from topik_sim.tts import TTSConfig
from topik_sim.web.app import WebApp

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


class CurriculumContentTests(unittest.TestCase):
    def test_bundled_curriculum_is_complete_and_ordered(self):
        units = load_curriculum(DEFAULT_CURRICULUM_PATH)
        self.assertEqual(len(units), 21)  # Hangul stage + 2 levels x 10 units
        orders = [(u["level"], u["order"]) for u in units]
        self.assertEqual(orders, sorted(orders))
        for unit in units:
            self.assertTrue(unit["id"] and unit["title"] and unit["scope"], unit.get("id"))
            self.assertTrue(unit.get("tasks"), unit["id"])
        levels = {u["level"] for u in units}
        self.assertEqual(levels, {0, 1, 2})

    def test_resolution_links_units_to_real_activities(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "library"
            import_pack(SAMPLE_PACK, library)
            units = load_curriculum(DEFAULT_CURRICULUM_PATH)
            resolved = resolve_units(units, library, DEFAULT_COURSES_PATH,
                                     DEFAULT_COMPOSE_PATH, DEFAULT_DIALOGUES_PATH)
            by_id = {u["id"]: u for u in resolved}
            # The greetings unit names an existing dialogue and a formal-polite drill.
            self.assertIn("self-intro", by_id["greetings"]["dialogues"])
            self.assertTrue(any(f["form"] == "seumnida" for f in by_id["greetings"]["conjugation"]))
            # Food matches the want-to compose structure via its grammar scope.
            self.assertIn("want-to", [s["id"] for s in by_id["food"]["compose_structures"]])
            # The Hangul stage has no grammar and resolves to drills only.
            self.assertEqual(by_id["hangul"]["compose_structures"], [])
            self.assertEqual(by_id["hangul"]["courses"], [])

    def test_unknown_dialogues_are_dropped(self):
        units = [{"id": "x", "title": "X", "order": 1, "level": 1, "scope": "s",
                  "grammar": [], "dialogues": ["restaurant", "no-such-dialogue"]}]
        with tempfile.TemporaryDirectory() as temp:
            resolved = resolve_units(units, Path(temp) / "library", DEFAULT_COURSES_PATH,
                                     DEFAULT_COMPOSE_PATH, DEFAULT_DIALOGUES_PATH)
        self.assertEqual(resolved[0]["dialogues"], ["restaurant"])


class UnitStatusTests(unittest.TestCase):
    def test_status_reflects_course_homework_and_practice(self):
        from topik_sim.courses import mark_done
        from topik_sim.homework import record_homework
        from topik_sim.practice_log import record_practice

        unit = {"id": "u", "courses": [{"pack_id": "p", "course_id": "c1", "title": "t", "order": 1}],
                "drills": [{"mode": "numbers"}], "dialogues": []}
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(unit_status(unit, temp)["state"], "new")
            record_practice(temp, "numbers", "Number practice", 1, 2)
            self.assertEqual(unit_status(unit, temp)["state"], "started")
            mark_done(temp, "p", "c1")
            record_homework(temp, "p", "c1", 5, 6)
            status = unit_status(unit, temp)
            self.assertEqual(status["state"], "done")
            self.assertEqual(status["lessons_done"], 1)
            self.assertEqual(status["homework_done"], 1)

    def test_courseless_unit_is_practiced_not_done(self):
        from topik_sim.practice_log import record_practice

        unit = {"id": "h", "courses": [], "drills": [{"mode": "sounds"}], "dialogues": []}
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(unit_status(unit, temp)["state"], "new")
            record_practice(temp, "sounds", "Pronunciation", 3, 4)
            self.assertEqual(unit_status(unit, temp)["state"], "practiced")


class PathEndpointTests(unittest.TestCase):
    def test_api_path_returns_units_with_status(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "library"
            import_pack(SAMPLE_PACK, library)
            app = WebApp(library_dir=library, attempt_dir=Path(temp) / "attempts",
                         tts_config=TTSConfig(output_dir=Path(temp) / "audio"),
                         audio_enabled=False)
            status, payload = app.handle("GET", "/api/path")
            self.assertEqual(status, 200)
            self.assertEqual(len(payload["units"]), 21)
            first = payload["units"][0]
            self.assertIn("status", first)
            self.assertIn(first["status"]["state"], {"new", "started", "practiced", "done"})


if __name__ == "__main__":
    unittest.main()
