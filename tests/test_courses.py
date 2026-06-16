import tempfile
import unittest
from pathlib import Path

from topik_sim.content import load_pack
from topik_sim.courses import (
    courses_for,
    course_questions,
    is_done,
    load_course_doc,
    load_progress,
    mark_done,
    validate_course_doc,
)
from topik_sim.library import latest_packs, load_pack_ref
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import COURSE_PICK, COURSE_STEP, IDLE, Shell

try:
    from test_shell import StubPrefetcher
except ImportError:
    from tests.test_shell import StubPrefetcher


ROOT = Path(__file__).resolve().parents[1]
MINI_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"
BUNDLED_COURSES = ROOT / "content" / "courses"
LIBRARY = ROOT / "content" / "library"


def _make_doc(courses, limits=None):
    return {
        "schema_version": "topik-sim.course.v1",
        "pack_id": "topik-i-mini-pack",
        "limits": limits or {"max_new_vocab": 12, "max_new_grammar": 3},
        "courses": courses,
    }


class CoursesModuleTests(unittest.TestCase):
    def setUp(self):
        self.pack = load_pack(MINI_PACK)

    def test_full_valid_doc_passes(self):
        doc = _make_doc([
            {"id": "c01", "order": 1, "title": "A", "new_vocabulary": [{"ko": "오늘", "en": "today"}],
             "new_grammar": [{"pattern": "-습니다"}], "question_ids": ["r-001"]},
            {"id": "c02", "order": 2, "title": "B", "new_vocabulary": [{"ko": "책", "en": "book"}],
             "new_grammar": [{"pattern": "N에서"}], "question_ids": ["r-002"]},
        ])
        self.assertEqual(validate_course_doc(doc, self.pack), [])

    def test_missing_coverage_is_flagged(self):
        doc = _make_doc([{"id": "c01", "order": 1, "question_ids": ["r-001"]}])
        errors = validate_course_doc(doc, self.pack)
        self.assertTrue(any("not covered" in e for e in errors))

    def test_unknown_and_duplicate_questions_flagged(self):
        doc = _make_doc([
            {"id": "c01", "order": 1, "question_ids": ["r-001", "r-002"]},
            {"id": "c02", "order": 2, "question_ids": ["r-002", "r-999"]},
        ])
        errors = validate_course_doc(doc, self.pack)
        self.assertTrue(any("not in the pack" in e for e in errors))
        self.assertTrue(any("also in course" in e for e in errors))

    def test_limit_and_repeat_violations_flagged(self):
        doc = _make_doc([
            {"id": "c01", "order": 1, "new_vocabulary": [{"ko": "오늘", "en": "x"}],
             "new_grammar": [{"pattern": "-습니다"}], "question_ids": ["r-001"]},
            {"id": "c02", "order": 2, "new_vocabulary": [{"ko": "오늘", "en": "x"}],
             "new_grammar": [{"pattern": "-습니다"}], "question_ids": ["r-002"]},
        ], limits={"max_new_vocab": 0, "max_new_grammar": 0})
        errors = validate_course_doc(doc, self.pack)
        self.assertTrue(any("exceeds limit" in e for e in errors))
        self.assertTrue(any("already introduced" in e for e in errors))

    def test_noncontiguous_order_flagged(self):
        doc = _make_doc([
            {"id": "c01", "order": 1, "question_ids": ["r-001"]},
            {"id": "c02", "order": 5, "question_ids": ["r-002"]},
        ])
        self.assertTrue(any("contiguous" in e for e in validate_course_doc(doc, self.pack)))

    def test_course_questions_resolves_ids(self):
        course = {"question_ids": ["r-002", "r-001", "missing"]}
        qs = course_questions(course, self.pack)
        self.assertEqual([q["question_id"] for q in qs], ["r-002", "r-001"])

    def test_progress_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(is_done(load_progress(d), "p", "c01"))
            mark_done(d, "p", "c01")
            self.assertTrue(is_done(load_progress(d), "p", "c01"))


class BundledCoursesTests(unittest.TestCase):
    def test_mini_example_validates(self):
        doc = load_course_doc("topik-i-mini-pack", BUNDLED_COURSES)
        self.assertTrue(doc)
        self.assertEqual(validate_course_doc(doc, load_pack(MINI_PACK)), [])

    def test_every_library_pack_course_file_validates(self):
        if not (LIBRARY / "manifest.json").exists():
            self.skipTest("no imported library")
        checked = 0
        for entry in latest_packs(LIBRARY):
            doc = load_course_doc(entry["pack_id"], BUNDLED_COURSES)
            if not doc:
                continue
            pack = load_pack_ref(f"{entry['pack_id']}@{entry['pack_version']}", LIBRARY)
            self.assertEqual(validate_course_doc(doc, pack), [], entry["pack_id"])
            checked += 1
        self.assertGreaterEqual(checked, 1)


class CourseShellTests(unittest.TestCase):
    def setUp(self):
        ansi.set_color_enabled(False)
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)

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
            flashcard_seed=0,
        )
        shell.courses_path = BUNDLED_COURSES
        return shell, output

    def test_full_course_walkthrough_marks_complete(self):
        shell, output = self.make_shell()
        shell.handle_line(f"/course {MINI_PACK}")
        self.assertEqual(shell.state, COURSE_PICK)
        self.assertIn("Course ·", "\n".join(output))

        shell.handle_line("1")          # start the one course → intro
        self.assertEqual(shell.state, COURSE_STEP)

        shell.handle_line("")           # begin step 1: vocabulary (6 cards)
        for _ in range(6):
            shell.handle_line("")       # flip
            shell.handle_line("y")      # graded known
        self.assertEqual(shell.state, COURSE_STEP)

        shell.handle_line("")           # begin step 2: grammar (2 cards)
        for _ in range(2):
            shell.handle_line("")
            shell.handle_line("y")
        self.assertEqual(shell.state, COURSE_STEP)

        output.clear()
        shell.handle_line("")           # begin step 3: exam (r-001, r-002)
        shell.handle_line("B")          # r-001 correct
        shell.handle_line("")
        shell.handle_line("A")          # r-002 correct
        shell.handle_line("")
        text = "\n".join(output)
        self.assertIn("Course complete", text)
        self.assertEqual(shell.state, IDLE)
        self.assertIsNone(shell._course)
        self.assertTrue(is_done(load_progress(self.temp_dir / "attempts"), "topik-i-mini-pack", "c01"))

    def test_pause_leaves_a_course(self):
        shell, output = self.make_shell()
        shell.handle_line(f"/course {MINI_PACK}")
        shell.handle_line("1")
        shell.handle_line("")           # into vocabulary flashcards
        shell.handle_line("/pause")
        self.assertIn("Left the course", "\n".join(output))
        self.assertEqual(shell.state, IDLE)
        self.assertIsNone(shell._course)

    def test_unknown_pack_course_reports(self):
        shell, output = self.make_shell()
        shell.handle_line(f"/course {ROOT / 'examples' / 'content' / 'topik_i_formats_pack.json'}")
        self.assertIn("No course is defined", "\n".join(output))


if __name__ == "__main__":
    unittest.main()
