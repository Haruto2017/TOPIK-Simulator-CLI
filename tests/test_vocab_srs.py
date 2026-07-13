import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from topik_sim import vocab_srs
from topik_sim.library import import_pack
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import IDLE, TYPING, Shell
from topik_sim.web.app import WebApp

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"
GLOSSES = {"오늘": "today", "날씨": "weather", "좋다": "to be good",
           "도서관": "library", "책": "book", "읽다": "to read"}


class SchedulerTests(unittest.TestCase):
    def test_correct_promotes_and_pushes_due_out(self):
        deck = {"cards": {}}
        now = vocab_srs.utc_now()
        card = vocab_srs.record(deck, "오늘", "today", True, now)
        self.assertEqual(card["box"], 2)
        due = vocab_srs._due_at(card)
        self.assertAlmostEqual((due - now).days, vocab_srs.BOX_INTERVALS_DAYS[2], delta=1)
        # a second correct promotes further out
        card = vocab_srs.record(deck, "오늘", "today", True, now)
        self.assertEqual(card["box"], 3)

    def test_miss_resets_to_box_one(self):
        deck = {"cards": {}}
        now = vocab_srs.utc_now()
        vocab_srs.record(deck, "책", "book", True, now)
        vocab_srs.record(deck, "책", "book", True, now)
        card = vocab_srs.record(deck, "책", "book", False, now)
        self.assertEqual(card["box"], 1)
        self.assertEqual(card["lapses"], 1)

    def test_session_is_due_first_then_new_and_deterministic(self):
        deck = {"cards": {}}
        now = vocab_srs.utc_now()
        # nothing scheduled yet → all items are new, capped at new_limit
        session = vocab_srs.build_session(deck, GLOSSES, now=now, count=10, new_limit=3)
        self.assertEqual(len(session), 3)
        self.assertTrue(all(item["new"] for item in session))
        self.assertEqual(session, vocab_srs.build_session(deck, GLOSSES, now=now, count=10, new_limit=3))

        # make one due in the past; it should lead the next session
        vocab_srs.record(deck, "읽다", "to read", False, now - timedelta(days=5))
        session = vocab_srs.build_session(deck, GLOSSES, now=now, count=10, new_limit=3)
        self.assertEqual(session[0]["ko"], "읽다")
        self.assertFalse(session[0]["new"])

    def test_not_yet_due_cards_are_skipped(self):
        deck = {"cards": {}}
        now = vocab_srs.utc_now()
        for ko, en in GLOSSES.items():
            vocab_srs.record(deck, ko, en, True, now)  # all due in 3 days
        self.assertEqual(vocab_srs.due_count(deck, now), 0)
        # every word is now "learning", none new, none due → empty session today
        self.assertEqual(vocab_srs.build_session(deck, GLOSSES, now=now, count=10), [])


class StubPrefetcher:
    def warm(self, *a, **k):
        return None

    def close(self):
        return None


class VocabShellTests(unittest.TestCase):
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
            audio_enabled=False,
            flashcard_seed=0,
        )
        return shell, output

    def test_vocab_review_schedules_each_answer(self):
        shell, output = self.make_shell()
        shell.handle_line("/vocab 4")
        self.assertEqual(shell.state, TYPING)
        first_wrong = False
        while shell.state == TYPING:
            item = shell._typing_items[shell._typing_index]
            self.assertIn("srs_key", item)
            shell.handle_line(item["answer"] if first_wrong else "아무거나")
            first_wrong = True
        self.assertEqual(shell.state, IDLE)
        self.assertIn("Scheduled", "\n".join(output))
        deck = vocab_srs.load_deck(self.temp_dir / "attempts")
        self.assertEqual(len(deck["cards"]), 4)
        # the deliberately-missed first card is back in box 1
        self.assertTrue(any(c["box"] == 1 and c["last_result"] is False for c in deck["cards"].values()))


class VocabWebTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        import_pack(SAMPLE_PACK, self.temp_dir / "library")

    def tearDown(self):
        self._temp.cleanup()

    def test_vocab_mode_records_and_state_reports_due(self):
        app = WebApp(library_dir=self.temp_dir / "library", attempt_dir=self.temp_dir / "attempts",
                     tts_config=TTSConfig(output_dir=self.temp_dir / "audio"), audio_enabled=False, seed=0)
        status, view = app.handle("POST", "/api/drill/start", body={"mode": "vocab", "count": 3})
        self.assertEqual(status, 200)
        self.assertEqual(view["label"], "Vocabulary review")
        activity = view["id"]
        while True:
            item = app._activities[activity]["items"][view["progress"][0]]
            status, result = app.handle("POST", f"/api/activity/{activity}/answer",
                                        body={"value": item["answer"]})
            if result.get("finished"):
                break
            status, view = app.handle("GET", f"/api/activity/{activity}")
        deck = vocab_srs.load_deck(self.temp_dir / "attempts")
        self.assertEqual(len(deck["cards"]), 3)
        self.assertTrue(all(c["box"] == 2 for c in deck["cards"].values()))
        # nothing due same-day after all-correct
        status, state = app.handle("GET", "/api/state")
        self.assertEqual(state["vocab_due"], 0)


if __name__ == "__main__":
    unittest.main()
