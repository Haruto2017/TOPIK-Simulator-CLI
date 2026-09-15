import json
import tempfile
import unittest
from pathlib import Path

from topik_sim import vocab_srs
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import Shell
from topik_sim.web.app import WebApp
from topik_sim.wordlists import WORDLIST_SCHEMA_VERSION

WORDS = [("사과", "apple"), ("바다", "sea"), ("학교", "school"), ("친구", "friend")]


def write_wordlist(root: Path) -> None:
    (root / "vocabulary").mkdir(parents=True, exist_ok=True)
    (root / "vocabulary" / "unit.json").write_text(json.dumps({
        "schema_version": WORDLIST_SCHEMA_VERSION,
        "words": [{"ko": ko, "en": en, "unit": "test-unit"} for ko, en in WORDS],
    }, ensure_ascii=False), encoding="utf-8")


class ShellRoundsTests(unittest.TestCase):
    """Missed words come straight back, round after round, until cleared."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        (root / "library").mkdir()
        write_wordlist(root)
        ansi.set_color_enabled(False)
        self.attempts = root / "attempts"
        self.out: list[str] = []
        self.shell = Shell(
            library_dir=root / "library", attempt_dir=self.attempts,
            tts_config=TTSConfig(output_dir=root / "audio"),
            audio_enabled=False, output=self.out.append, flashcard_seed=0,
        )

    def tearDown(self):
        ansi.set_color_enabled(None)
        self._temp.cleanup()

    def text(self) -> str:
        return "\n".join(self.out)

    def answer_round(self, wrong: set[str]) -> None:
        """Answer every item in the current round; type garbage for ``wrong``."""
        for _ in range(len(self.shell._typing_items)):
            item = self.shell._typing_items[self.shell._typing_index]
            self.shell.handle_line("틀림" if item["answer"] in wrong else item["answer"])

    def test_misses_return_until_every_word_is_cleared(self):
        self.shell.handle_line("/recall unit:test-unit 4 loop")
        self.assertIn("misses come back until cleared", self.text())
        self.answer_round(wrong={"사과", "바다"})
        self.assertIn("Round 1: 2/4 · 2 to clear", self.text())
        self.assertEqual(self.shell._typing_round, 2)
        self.assertEqual({i["answer"] for i in self.shell._typing_items}, {"사과", "바다"})

        self.answer_round(wrong={"바다"})          # still missing one
        self.assertEqual(self.shell._typing_round, 3)
        self.assertEqual([i["answer"] for i in self.shell._typing_items], ["바다"])

        self.answer_round(wrong=set())              # clear it
        body = self.text()
        self.assertIn("All clear in 3 rounds", body)
        self.assertIn("First pass: 2/4 correct.", body)
        self.assertEqual(self.shell.state, "idle") if isinstance(self.shell.state, str) else None

    def test_first_pass_is_what_gets_logged(self):
        from topik_sim.practice_log import load_practice_log

        self.shell.handle_line("/recall unit:test-unit 4 loop")
        self.answer_round(wrong={"사과"})
        self.answer_round(wrong=set())
        run = load_practice_log(self.attempts)["runs"][-1]
        self.assertEqual((run["hits"], run["total"]), (3, 4))
        self.assertEqual(run["missed"], ["사과"])

    def test_without_loop_a_miss_just_ends_the_session(self):
        self.shell.handle_line("/recall unit:test-unit 4")
        self.answer_round(wrong={"사과"})
        self.assertEqual(self.shell._typing_round, 1)
        self.assertNotIn("Round", self.text())
        self.assertIn("Recalled 3/4 correctly.", self.text())

    def test_recall_miss_is_scheduled_for_tomorrow_once(self):
        """A first-pass miss lands in the SRS deck; later rounds don't pile on lapses."""
        self.shell.handle_line("/recall unit:test-unit 4 loop")
        self.answer_round(wrong={"사과"})
        self.answer_round(wrong={"사과"})           # missed again in round 2
        self.answer_round(wrong=set())
        deck = vocab_srs.load_deck(self.attempts)
        self.assertIn("사과", deck["cards"])
        self.assertEqual(deck["cards"]["사과"]["lapses"], 1)
        self.assertEqual(deck["cards"]["사과"]["box"], 1)
        self.assertNotIn("바다", deck["cards"])       # correct answers are not scheduled

    def test_pause_ends_the_loop_without_a_new_round(self):
        self.shell.handle_line("/recall unit:test-unit 4 loop")
        item = self.shell._typing_items[0]
        self.shell.handle_line("틀림")               # one miss
        self.shell.handle_line("/pause")
        self.assertEqual(self.shell._typing_items, [])
        self.assertFalse(self.shell._typing_loop)


class WebRoundsTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        (root / "library").mkdir()
        write_wordlist(root)
        self.attempts = root / "attempts"
        self.app = WebApp(library_dir=root / "library", attempt_dir=self.attempts,
                          tts_config=TTSConfig(output_dir=root / "audio"),
                          audio_enabled=False, seed=0)

    def tearDown(self):
        self._temp.cleanup()

    def start(self, **body):
        status, view = self.app.handle("POST", "/api/drill/start",
                                       body={"mode": "recall", "unit": "test-unit", "count": 4, **body})
        self.assertEqual(status, 200)
        return view["id"]

    def answer_round(self, aid, wrong):
        last = None
        while True:
            _, view = self.app.handle("GET", f"/api/activity/{aid}")
            if view["done"] or last and (last.get("finished") or last.get("next_round")):
                return last
            activity = self.app._activities[aid]
            item = activity["items"][activity["index"]]
            _, last = self.app.handle("POST", f"/api/activity/{aid}/answer",
                                      body={"value": "틀림" if item["answer"] in wrong else item["answer"]})
            if last.get("finished") or last.get("next_round"):
                return last

    def test_rounds_until_cleared(self):
        aid = self.start(until_correct=True)
        result = self.answer_round(aid, wrong={"사과", "바다"})
        self.assertFalse(result["finished"])
        self.assertEqual(result["next_round"], {"round": 2, "count": 2})
        _, view = self.app.handle("GET", f"/api/activity/{aid}")
        self.assertEqual(view["round"], 2)
        self.assertEqual(view["progress"], [0, 2])

        result = self.answer_round(aid, wrong=set())
        self.assertTrue(result["finished"])
        summary = result["summary"]
        self.assertEqual((summary["hits"], summary["total"]), (2, 4))   # first pass
        self.assertEqual(summary["rounds"], 2)
        self.assertTrue(summary["cleared"])
        self.assertEqual(summary["missed"], ["사과", "바다"]) if summary["missed"][0] == "사과" \
            else self.assertEqual(set(summary["missed"]), {"사과", "바다"})

    def test_no_loop_by_default(self):
        aid = self.start()
        result = self.answer_round(aid, wrong={"사과"})
        self.assertTrue(result["finished"])
        self.assertNotIn("next_round", result)
        self.assertEqual(result["summary"]["rounds"], 1)

    def test_vocab_mode_never_loops(self):
        """Spaced review already reschedules a miss; looping it would double-count."""
        status, view = self.app.handle("POST", "/api/drill/start",
                                       body={"mode": "vocab", "unit": "test-unit",
                                             "count": 4, "until_correct": True})
        self.assertEqual(status, 200)
        self.assertFalse(view["loop"])

    def test_recall_miss_is_scheduled_once(self):
        aid = self.start(until_correct=True)
        self.answer_round(aid, wrong={"사과"})
        self.answer_round(aid, wrong={"사과"})
        self.answer_round(aid, wrong=set())
        deck = vocab_srs.load_deck(self.attempts)
        self.assertEqual(deck["cards"]["사과"]["lapses"], 1)
        self.assertNotIn("바다", deck["cards"])


if __name__ == "__main__":
    unittest.main()
