import tempfile
import unittest
from pathlib import Path

from topik_sim.content import load_pack
from topik_sim.homework import (
    build_homework,
    homework_entry,
    load_homework_progress,
    record_homework,
)
from topik_sim.library import import_pack
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import HOMEWORK_PICK, IDLE, TYPING, Shell

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"

LESSON = {
    "id": "c01",
    "order": 1,
    "title": "Weather and the Library",
    "objectives": ["Describe the weather"],
    "new_vocabulary": [
        {"ko": "오늘", "en": "today"},
        {"ko": "날씨", "en": "weather"},
        {"ko": "좋다", "en": "to be good"},
        {"ko": "도서관", "en": "library"},
        {"ko": "책", "en": "book"},
        {"ko": "읽다", "en": "to read"},
    ],
    "new_grammar": [
        {"pattern": "-습니다", "explanation": "Formal polite declarative ending.", "example": "날씨가 좋습니다."},
        {"pattern": "N에서", "explanation": "Marks the place where an action happens.", "example": "도서관에서 책을 읽습니다."},
    ],
    "question_ids": ["r-001", "r-002"],
}


class BuildHomeworkTests(unittest.TestCase):
    def test_deterministic_and_covers_all_kinds(self):
        pack = load_pack(SAMPLE_PACK)
        first = build_homework(LESSON, pack=pack, seed=0)
        second = build_homework(LESSON, pack=pack, seed=0)
        self.assertEqual(first, second)
        kinds = {item["kind"] for item in first}
        self.assertEqual(kinds, {"recall", "meaning", "pattern", "cloze"})

    def test_recall_items_type_the_korean(self):
        items = [i for i in build_homework(LESSON, seed=0) if i["kind"] == "recall"]
        vocab = {entry["ko"] for entry in LESSON["new_vocabulary"]}
        for item in items:
            self.assertIn(item["answer"], vocab)
            self.assertIn(item["answer"], item["accept"])
            self.assertIn("meaning", item)

    def test_choice_items_accept_number_and_text(self):
        pack = load_pack(SAMPLE_PACK)
        choices = [i for i in build_homework(LESSON, pack=pack, seed=0) if i.get("options")]
        self.assertTrue(choices)
        for item in choices:
            self.assertIn(item["answer"], item["options"])
            number = str(item["options"].index(item["answer"]) + 1)
            self.assertIn(number, item["accept"])
            self.assertIn(item["answer"], item["accept"])
            self.assertTrue(item["reveal"].startswith(number + "."))
            # every option is listed in the prompt
            for option in item["options"]:
                self.assertIn(option, item["show"])

    def test_cloze_blanks_a_vocabulary_word_inside_the_example(self):
        items = [i for i in build_homework(LESSON, seed=0) if i["kind"] == "cloze"]
        self.assertEqual(len(items), 2)
        for item in items:
            self.assertIn("____", item["show"])
            self.assertNotIn(item["answer"], item["show"].split("____")[0].split(":")[-1] + item["show"].split("____")[-1])
            self.assertIn(item["answer"], {"날씨", "도서관", "책", "읽다", "오늘", "좋다"})

    def test_empty_lesson_yields_no_items(self):
        self.assertEqual(build_homework({"id": "x", "new_vocabulary": [], "new_grammar": []}), [])


class HomeworkProgressTests(unittest.TestCase):
    def test_record_keeps_best_and_counts_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = record_homework(temp_dir, "pack", "c01", 5, 8)
            self.assertEqual((entry["best_correct"], entry["runs"]), (5, 1))
            entry = record_homework(temp_dir, "pack", "c01", 3, 8)
            self.assertEqual((entry["best_correct"], entry["correct"], entry["runs"]), (5, 3, 2))
            entry = record_homework(temp_dir, "pack", "c01", 7, 8)
            self.assertEqual(entry["best_correct"], 7)
            progress = load_homework_progress(temp_dir)
            self.assertEqual(homework_entry(progress, "pack", "c01")["runs"], 3)
            self.assertIsNone(homework_entry(progress, "pack", "nope"))


class StubPrefetcher:
    def warm(self, *args, **kwargs):
        return None

    def close(self):
        return None


class HomeworkShellTests(unittest.TestCase):
    def setUp(self):
        ansi.set_color_enabled(False)
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        import_pack(SAMPLE_PACK, self.temp_dir / "library")

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
        return shell, output

    def test_homework_lists_lessons_then_runs_and_records(self):
        shell, output = self.make_shell()
        shell.handle_line("/homework topik-i-mini-pack")
        self.assertEqual(shell.state, HOMEWORK_PICK)
        self.assertIn("not done", "\n".join(output))

        shell.handle_line("1")
        self.assertEqual(shell.state, TYPING)
        while shell.state == TYPING:
            item = shell._typing_items[shell._typing_index]
            shell.handle_line(item["accept"][0])
        text = "\n".join(output)
        self.assertIn("Homework saved:", text)
        self.assertEqual(shell.state, IDLE)

        # The list and /course now show the recorded score.
        output.clear()
        shell.handle_line("/homework topik-i-mini-pack")
        self.assertIn("best ", "\n".join(output))
        shell.handle_line("")
        output.clear()
        shell.handle_line("/course topik-i-mini-pack")
        self.assertIn("homework ", "\n".join(output))
        shell.handle_line("")

    def test_pause_does_not_record(self):
        shell, output = self.make_shell()
        shell.handle_line("/homework topik-i-mini-pack 1")
        self.assertEqual(shell.state, TYPING)
        shell.handle_line("/pause")
        text = "\n".join(output)
        self.assertNotIn("Homework saved:", text)
        self.assertEqual(load_homework_progress(self.temp_dir / "attempts"), {})
        self.assertEqual(shell.state, IDLE)

    def test_choice_answer_accepts_option_number(self):
        shell, output = self.make_shell()
        shell.handle_line("/homework topik-i-mini-pack 1")
        while shell.state == TYPING:
            item = shell._typing_items[shell._typing_index]
            if item.get("options"):
                number = str(item["options"].index(item["answer"]) + 1)
                shell.handle_line(number)
            else:
                shell.handle_line(item["answer"])
        self.assertIn("Solved", "\n".join(output))
        self.assertIn("Homework saved:", "\n".join(output))

    def test_wrong_choice_reveals_numbered_answer_without_keys(self):
        shell, output = self.make_shell()
        shell.handle_line("/homework topik-i-mini-pack 1")
        while shell.state == TYPING:
            item = shell._typing_items[shell._typing_index]
            if item.get("options"):
                output.clear()
                shell.handle_line("없는답")  # wrong on purpose
                miss = "\n".join(output)
                self.assertIn(item["reveal"], miss)
                self.assertNotIn("Keys:", miss.split("\n")[0])
                # answer the rest correctly to finish cleanly
                while shell.state == TYPING:
                    current = shell._typing_items[shell._typing_index]
                    shell.handle_line(current["accept"][0])
                break
            shell.handle_line(item["accept"][0])

    def test_lesson_number_without_pack_is_rejected(self):
        shell, output = self.make_shell()
        shell.handle_line("/homework 1")
        self.assertIn("Name the pack first", "\n".join(output))
        self.assertEqual(shell.state, IDLE)

    def test_finish_course_suggests_homework(self):
        shell, output = self.make_shell()
        shell.handle_line("/course topik-i-mini-pack")
        shell.handle_line("1")          # start lesson 1
        shell.handle_line("")           # begin step 1: vocabulary cards
        while shell.state != IDLE and len(output) < 400:
            state = shell.state
            if state in {"flash_front"}:
                shell.handle_line("")   # flip
            elif state in {"flash_back"}:
                shell.handle_line("y")
            elif state == "course_step":
                shell.handle_line("")
            elif state == "answering":
                shell.handle_line("1")
            elif state == "continue":
                shell.handle_line("")
            else:
                break
        text = "\n".join(output)
        self.assertIn("Course complete", text)
        self.assertIn("/homework topik-i-mini-pack 1", text)


if __name__ == "__main__":
    unittest.main()
