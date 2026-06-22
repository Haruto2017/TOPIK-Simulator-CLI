import re
import tempfile
import unittest
from pathlib import Path

from topik_sim.numbers import (
    NUMBER_CATEGORIES,
    build_number_items,
    date_korean,
    math_korean,
    money_korean,
    native_counter,
    native_korean,
    ordinal_korean,
    phone_korean,
    sino_korean,
    time_korean,
)
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import IDLE, TYPING, Shell


class StubPrefetcher:
    def warm(self, *args, **kwargs):
        return None

    def shutdown(self):
        return None


class SinoKoreanTests(unittest.TestCase):
    def test_readings(self):
        cases = {
            0: "영", 5: "오", 10: "십", 15: "십오", 20: "이십", 100: "백",
            347: "삼백사십칠", 1000: "천", 2024: "이천이십사",
            10000: "만", 53000: "오만삼천", 100000: "십만",
        }
        for number, expected in cases.items():
            self.assertEqual(sino_korean(number), expected)

    def test_negative_rejected(self):
        with self.assertRaises(ValueError):
            sino_korean(-1)


class NativeKoreanTests(unittest.TestCase):
    def test_readings(self):
        self.assertEqual(native_korean(1), "하나")
        self.assertEqual(native_korean(11), "열하나")
        self.assertEqual(native_korean(20), "스물")
        self.assertEqual(native_korean(99), "아흔아홉")

    def test_counter_forms(self):
        self.assertEqual(native_counter(1), "한")
        self.assertEqual(native_counter(3), "세")
        self.assertEqual(native_counter(20), "스무")
        self.assertEqual(native_counter(21), "스물한")

    def test_out_of_range_rejected(self):
        for n in (0, 100):
            with self.assertRaises(ValueError):
                native_korean(n)


class MixedPhraseTests(unittest.TestCase):
    def test_date_uses_irregular_months(self):
        self.assertEqual(date_korean(2024, 6, 15), "이천이십사년 유월 십오일")
        self.assertEqual(date_korean(2020, 10, 3), "이천이십년 시월 삼일")

    def test_time_native_hour_sino_minute(self):
        self.assertEqual(time_korean(3, 15), "세 시 십오 분")
        self.assertEqual(time_korean(5, 0), "다섯 시")

    def test_money_and_phone_and_ordinal(self):
        self.assertEqual(money_korean(5300), "오천삼백 원")
        self.assertEqual(phone_korean("010-1234-5078"), "공일공 일이삼사 오공칠팔")
        self.assertEqual(ordinal_korean(1), "첫 번째")
        self.assertEqual(ordinal_korean(3), "세 번째")

    def test_math_topic_marker_follows_batchim(self):
        self.assertEqual(math_korean(2, "+", 3), "이 더하기 삼은 오")   # 삼 → 은
        self.assertEqual(math_korean(7, "-", 2), "칠 빼기 이는 오")      # 이 → 는
        self.assertEqual(math_korean(12, "÷", 3), "십이 나누기 삼은 사")


class BuildNumberItemsTests(unittest.TestCase):
    def test_deterministic_and_no_arabic_in_answers(self):
        first = build_number_items(seed=0, count=18)
        second = build_number_items(seed=0, count=18)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 18)
        for item in first:
            self.assertTrue(item["no_digits"])
            self.assertFalse(re.search(r"\d", item["answer"]), item["answer"])
            self.assertIn(item["answer"], item["accept"])

    def test_mix_rotates_through_every_category(self):
        items = build_number_items(seed=1, count=len(NUMBER_CATEGORIES))
        prompts = " ".join(item["show"] for item in items)
        for label in ("Sino-Korean", "Native-Korean", "Count", "Date", "Time",
                      "Money", "Solve", "Phone", "Ordinal"):
            self.assertIn(label, prompts)

    def test_single_category(self):
        items = build_number_items(seed=2, count=4, category="date")
        self.assertTrue(all(item["show"].startswith("Date:") for item in items))

    def test_unknown_category_rejected(self):
        with self.assertRaises(ValueError):
            build_number_items(seed=0, count=2, category="bogus")


class NumberShellTests(unittest.TestCase):
    def setUp(self):
        ansi.set_color_enabled(False)
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)

    def tearDown(self):
        ansi.set_color_enabled(None)
        self._temp.cleanup()

    def make_shell(self, **kwargs):
        output = []
        shell = Shell(
            library_dir=self.temp_dir / "library",
            attempt_dir=self.temp_dir / "attempts",
            tts_config=TTSConfig(output_dir=self.temp_dir / "audio"),
            output=output.append,
            prefetcher=StubPrefetcher(),
            flashcard_seed=0,
            **kwargs,
        )
        return shell, output

    def test_numbers_grades_korean_answers(self):
        shell, output = self.make_shell()
        shell.handle_line("/numbers 3")
        self.assertEqual(shell.state, TYPING)
        answers = [item["answer"] for item in shell._typing_items]
        for answer in answers:
            shell.handle_line(answer)
        text = "\n".join(output)
        self.assertIn("Read 3/3 correctly.", text)
        self.assertEqual(shell.state, IDLE)

    def test_spacing_is_forgiving(self):
        shell, output = self.make_shell()
        shell.handle_line("/numbers date 1")
        answer = shell._typing_items[0]["answer"]
        shell.handle_line(answer.replace(" ", ""))  # collapse all spaces
        self.assertIn("Read 1/1 correctly.", "\n".join(output))

    def test_digits_in_answer_are_rejected_and_retryable(self):
        shell, output = self.make_shell()
        shell.handle_line("/numbers 2")
        first = shell._typing_items[0]
        shell.handle_line("123")  # Arabic digits — not allowed
        self.assertEqual(shell.state, TYPING)
        self.assertEqual(shell._typing_index, 0)  # same item, no miss recorded
        self.assertIn("not digits", "\n".join(output))
        shell.handle_line(first["answer"])  # corrected answer advances
        self.assertEqual(shell._typing_index, 1)

    def test_unknown_category_message(self):
        shell, output = self.make_shell()
        shell.handle_line("/numbers bogus")
        self.assertIn("Unknown category", "\n".join(output))
        self.assertEqual(shell.state, IDLE)

    def test_pause_stops_early(self):
        shell, output = self.make_shell()
        shell.handle_line("/numbers 5")
        shell.handle_line("/pause")
        self.assertIn("stopped after 0/5", "\n".join(output))
        self.assertEqual(shell.state, IDLE)


if __name__ == "__main__":
    unittest.main()
