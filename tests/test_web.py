import json
import tempfile
import unittest
from pathlib import Path

from topik_sim.library import import_pack
from topik_sim.tts import TTSConfig
from topik_sim.web.app import WebApp

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


def listening_pack_data():
    def question(question_id, order, transcript):
        return {
            "question_id": question_id,
            "order": order,
            "skill": "listening",
            "audio_ref": f"transcript-only:{question_id}",
            "passage": f"Transcript: {transcript}",
            "prompt": "What is being said?",
            "options": [
                {"id": "A", "text": "greeting"},
                {"id": "B", "text": "thanks"},
            ],
            "answer": {"type": "single_choice", "correct_option_id": "A"},
            "explanation": {"summary": "Listen for the keyword."},
        }

    return {
        "schema_version": "topik-sim.content.v1",
        "pack_id": "listen-pack",
        "pack_version": "0.0.1",
        "title": "Listening Pack",
        "topik_level": "TOPIK_I",
        "language_pair": "ko-en",
        "source_type": "original",
        "sections": [
            {
                "section_id": "listening",
                "title": "Listening",
                "questions": [
                    question("l-001", 1, "안녕하세요."),
                    question("l-002", 2, "감사합니다."),
                ],
            }
        ],
    }


def fake_synthesizer(temp_dir: Path):
    """Writes a tiny fake WAV instead of running a TTS engine."""
    def synth(text: str, config: TTSConfig) -> Path:
        path = Path(temp_dir) / f"fake-{abs(hash(text))}.wav"
        path.write_bytes(b"RIFFfakeWAVEdata" + text.encode("utf-8"))
        return path
    return synth


class WebAppTestCase(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        import_pack(SAMPLE_PACK, self.temp_dir / "library")
        listen_path = self.temp_dir / "listen_pack.json"
        listen_path.write_text(json.dumps(listening_pack_data(), ensure_ascii=False), encoding="utf-8")
        import_pack(listen_path, self.temp_dir / "library")

    def tearDown(self):
        self._temp.cleanup()

    def make_app(self, **kwargs):
        kwargs.setdefault("library_dir", self.temp_dir / "library")
        kwargs.setdefault("attempt_dir", self.temp_dir / "attempts")
        kwargs.setdefault("tts_config", TTSConfig(output_dir=self.temp_dir / "audio"))
        kwargs.setdefault("seed", 0)
        return WebApp(**kwargs)


class StateAndListingTests(WebAppTestCase):
    def test_state_lists_packs_and_tts(self):
        app = self.make_app(audio_enabled=False)
        status, payload = app.handle("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertIn("topik-i-mini-pack", {p["pack_id"] for p in payload["packs"]})
        self.assertFalse(payload["tts"]["enabled"])

    def test_unknown_paths_are_404(self):
        app = self.make_app()
        self.assertEqual(app.handle("GET", "/api/nope")[0], 404)
        self.assertEqual(app.handle("GET", "/elsewhere")[0], 404)

    def test_tts_settings_update_and_validate(self):
        app = self.make_app(audio_enabled=False)
        status, payload = app.handle("POST", "/api/tts", body={"enabled": True, "volume": 0.8})
        self.assertEqual(status, 200)
        self.assertTrue(payload["enabled"])
        self.assertAlmostEqual(payload["volume"], 0.8)
        status, payload = app.handle("POST", "/api/tts", body={"volume": 0})
        self.assertEqual(status, 400)


class PackSectionsTests(WebAppTestCase):
    """The exam screen offers sections as choices, so nothing has to be typed."""

    def test_sections_are_listed_with_counts(self):
        app = self.make_app(audio_enabled=False)
        status, payload = app.handle("GET", "/api/packs/listen-pack/sections")
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["sections"]), 1)
        section = payload["sections"][0]
        self.assertEqual(section["section_id"], "listening")
        self.assertEqual(section["title"], "Listening")
        self.assertEqual(section["count"], 2)

    def test_section_ids_can_start_an_exam(self):
        """Every id offered must be one /api/exam/start accepts."""
        app = self.make_app(audio_enabled=False)
        sections = app.handle("GET", "/api/packs/listen-pack/sections")[1]["sections"]
        for section in sections:
            status, view = app.handle("POST", "/api/exam/start",
                                      body={"pack": "listen-pack", "section": section["section_id"]})
            self.assertEqual(status, 200, section["section_id"])
            self.assertEqual(view["progress"][1], section["count"])

    def test_unknown_pack_is_rejected(self):
        app = self.make_app(audio_enabled=False)
        self.assertEqual(app.handle("GET", "/api/packs/nope/sections")[0], 400)


class ExamFlowTests(WebAppTestCase):
    def test_full_exam_lifecycle_with_sanitized_questions(self):
        app = self.make_app(audio_enabled=False)
        status, view = app.handle("POST", "/api/exam/start",
                                  body={"pack": "topik-i-mini-pack", "section": "reading"})
        self.assertEqual(status, 200)
        question = view["question"]
        self.assertNotIn("answer", question)
        self.assertNotIn("explanation", question)
        self.assertTrue(question["options"])
        activity = view["id"]

        # Wrong, then right; the answer response carries the teaching payload.
        status, result = app.handle("POST", f"/api/activity/{activity}/answer", body={"value": "A"})
        self.assertEqual(status, 200)
        self.assertFalse(result["correct"])
        self.assertTrue(result["correct_answer"])
        self.assertIn("summary", result["explanation"])
        self.assertFalse(result["finished"])

        status, view = app.handle("GET", f"/api/activity/{activity}")
        self.assertEqual(view["progress"], [1, 2])
        status, result = app.handle("POST", f"/api/activity/{activity}/answer",
                                    body={"value": view["question"]["options"][0]["id"]})
        self.assertTrue(result["finished"])
        summary = result["summary"]
        self.assertEqual(summary["score"][1], 2)
        self.assertTrue(summary["attempt_file"].endswith(".json"))
        # Finalized: the activity is gone, the attempt file is completed.
        self.assertEqual(app.handle("GET", f"/api/activity/{activity}")[0], 404)
        status, listing = app.handle("GET", "/api/attempts")
        self.assertEqual(listing["attempts"][0]["status"], "completed")

    def test_listening_hides_transcript_only_when_audio_available(self):
        with_audio = self.make_app(audio_enabled=True,
                                   synthesizer=fake_synthesizer(self.temp_dir))
        status, view = with_audio.handle("POST", "/api/exam/start",
                                         body={"pack": "listen-pack"})
        question = view["question"]
        self.assertTrue(question["listening"])
        self.assertTrue(question["transcript_hidden"])
        self.assertNotIn("passage", question)
        self.assertGreater(question["audio_parts"], 0)
        activity = view["id"]
        status, payload = with_audio.handle("GET", f"/api/activity/{activity}/audio",
                                            query={"part": "0"})
        self.assertEqual(status, 200)
        data, content_type = payload
        self.assertEqual(content_type, "audio/wav")
        self.assertTrue(data.startswith(b"RIFF"))
        status, reveal = with_audio.handle("POST", f"/api/activity/{activity}/transcript")
        self.assertTrue(reveal["transcript"])

        without_audio = self.make_app(audio_enabled=False)
        status, view = without_audio.handle("POST", "/api/exam/start",
                                            body={"pack": "listen-pack"})
        question = view["question"]
        self.assertFalse(question["transcript_hidden"])
        self.assertIn("passage", question)
        self.assertEqual(question["audio_parts"], 0)

    def test_transcript_arrives_with_the_answer(self):
        app = self.make_app(audio_enabled=True, synthesizer=fake_synthesizer(self.temp_dir))
        status, view = app.handle("POST", "/api/exam/start",
                                  body={"pack": "listen-pack"})
        activity = view["id"]
        status, result = app.handle("POST", f"/api/activity/{activity}/answer", body={"value": "A"})
        self.assertTrue(result["transcript"])

    def test_resume_and_drill_and_traversal_guard(self):
        app = self.make_app(audio_enabled=False)
        status, view = app.handle("POST", "/api/exam/start", body={"pack": "topik-i-mini-pack"})
        activity = view["id"]
        app.handle("POST", f"/api/activity/{activity}/answer", body={"value": "A"})
        status, paused = app.handle("POST", f"/api/activity/{activity}/pause")
        self.assertTrue(paused["paused"])
        name = paused["attempt_file"]

        status, view = app.handle("POST", "/api/exam/resume", body={"file": name})
        self.assertEqual(status, 200)
        self.assertEqual(view["progress"][0], 1)
        activity = view["id"]
        while True:
            status, result = app.handle("POST", f"/api/activity/{activity}/answer", body={"value": "A"})
            if result["finished"]:
                break
        finished_file = result["summary"]["attempt_file"]

        status, drill = app.handle("POST", "/api/exam/drill", body={"file": finished_file})
        self.assertEqual(status, 200)
        self.assertEqual(drill["activity"], "drill")

        self.assertEqual(app.handle("POST", "/api/exam/resume", body={"file": "../../etc/passwd"})[0], 400)
        self.assertEqual(app.handle("GET", "/api/report", query={"file": "nope.json"})[0], 404)

    def test_course_exam_marks_course_done(self):
        from topik_sim.courses import is_done, load_progress

        app = self.make_app(audio_enabled=False)
        status, view = app.handle("POST", "/api/exam/course",
                                  body={"pack": "topik-i-mini-pack", "course_id": "c01"})
        self.assertEqual(status, 200)
        activity = view["id"]
        while True:
            status, result = app.handle("POST", f"/api/activity/{activity}/answer", body={"value": "B"})
            if result["finished"]:
                break
        self.assertTrue(result["summary"]["course_completed"])
        progress = load_progress(self.temp_dir / "attempts")
        self.assertTrue(is_done(progress, "topik-i-mini-pack", "c01"))


class DrillFlowTests(WebAppTestCase):
    def test_homework_drill_grades_and_records(self):
        app = self.make_app(audio_enabled=False)
        status, view = app.handle("POST", "/api/drill/start",
                                  body={"mode": "homework", "pack": "topik-i-mini-pack", "course_id": "c01"})
        self.assertEqual(status, 200)
        self.assertEqual(view["label"], "Homework")
        activity = view["id"]
        # A choice item must never expose accept/answer to the client.
        self.assertNotIn("accept", view["item"])
        self.assertNotIn("answer", view["item"])
        while True:
            status, result = app.handle("POST", f"/api/activity/{activity}/answer", body={"value": "오늘"})
            if result.get("finished"):
                break
        self.assertIn("homework", result["summary"])
        status, courses = app.handle("GET", "/api/courses")
        lesson = courses["packs"][0]["lessons"][0]
        self.assertIsNotNone(lesson["homework"])

    def test_numbers_digit_rejection_is_a_retry(self):
        app = self.make_app(audio_enabled=False)
        status, view = app.handle("POST", "/api/drill/start", body={"mode": "numbers", "count": 2})
        activity = view["id"]
        status, result = app.handle("POST", f"/api/activity/{activity}/answer", body={"value": "12"})
        self.assertTrue(result["retry"])
        status, again = app.handle("GET", f"/api/activity/{activity}")
        self.assertEqual(again["progress"], [0, 2])  # same item, no penalty

    def test_dictation_uses_accuracy_and_reveals_text_without_tts(self):
        app = self.make_app(audio_enabled=False)
        status, view = app.handle("POST", "/api/drill/start",
                                  body={"mode": "dictation", "pack": "listen-pack", "count": 1})
        self.assertEqual(status, 200)
        item = view["item"]
        self.assertTrue(item["dictation"])
        self.assertFalse(item["audio"])
        self.assertIn("Type this sentence", item["show"])  # no-TTS fallback shows the text
        expected = item["show"].split(":", 1)[1].strip()
        activity = view["id"]
        status, result = app.handle("POST", f"/api/activity/{activity}/answer", body={"value": expected})
        self.assertTrue(result["correct"])
        self.assertGreaterEqual(result["accuracy"], 0.999)

    def test_typing_and_recall_start(self):
        app = self.make_app(audio_enabled=False)
        for mode in ("typing", "recall"):
            status, view = app.handle("POST", "/api/drill/start",
                                      body={"mode": mode, "pack": "topik-i-mini-pack", "count": 4})
            self.assertEqual(status, 200, mode)
            self.assertTrue(view["item"]["show"], mode)

    def test_say_returns_503_without_tts(self):
        app = self.make_app(audio_enabled=False)
        status, payload = app.handle("GET", "/api/say", query={"text": "안녕"})
        self.assertEqual(status, 503)

    def test_say_streams_wav_with_fake_tts(self):
        app = self.make_app(audio_enabled=True, synthesizer=fake_synthesizer(self.temp_dir))
        status, payload = app.handle("GET", "/api/say", query={"text": "안녕"})
        self.assertEqual(status, 200)
        data, content_type = payload
        self.assertEqual(content_type, "audio/wav")

    def test_synthesis_failure_marks_audio_failed(self):
        def broken(text, config):
            raise RuntimeError("engine exploded")
        app = self.make_app(audio_enabled=True, synthesizer=broken)
        status, _ = app.handle("GET", "/api/say", query={"text": "안녕"})
        self.assertEqual(status, 503)
        self.assertTrue(app.tts_state()["failed"])
        # Listening questions fall back to visible transcripts afterwards.
        status, view = app.handle("POST", "/api/exam/start",
                                  body={"pack": "listen-pack"})
        self.assertFalse(view["question"]["transcript_hidden"])


class ReleasePatchTests(WebAppTestCase):
    def test_exam_hint_walks_vocabulary_then_exhausts_and_resets(self):
        app = self.make_app(audio_enabled=False)
        status, view = app.handle("POST", "/api/exam/start",
                                  body={"pack": "topik-i-mini-pack", "section": "reading"})
        activity = view["id"]
        status, first = app.handle("POST", f"/api/activity/{activity}/hint")
        self.assertEqual(status, 200)
        self.assertTrue(first["hint"])
        self.assertEqual(first["shown"], 1)
        total = first["total"]
        for _ in range(total - 1):
            status, last = app.handle("POST", f"/api/activity/{activity}/hint")
        status, done = app.handle("POST", f"/api/activity/{activity}/hint")
        self.assertIsNone(done["hint"])
        self.assertIn("No more hints", done["message"])
        # Answering and moving on resets the hint counter.
        app.handle("POST", f"/api/activity/{activity}/answer", body={"value": "A"})
        status, view = app.handle("GET", f"/api/activity/{activity}")
        status, again = app.handle("POST", f"/api/activity/{activity}/hint")
        self.assertEqual(again.get("shown"), 1)

    def test_drill_audio_never_spoils_the_answer(self):
        app = self.make_app(audio_enabled=True, synthesizer=fake_synthesizer(self.temp_dir))
        status, view = app.handle("POST", "/api/drill/start", body={"mode": "numbers", "count": 2})
        self.assertFalse(view["item"]["audio"])  # speech == expected answer
        activity = view["id"]
        status, result = app.handle("POST", f"/api/activity/{activity}/answer", body={"value": "영"})
        self.assertIn("speech", result)  # the answer's audio arrives with grading

        status, view = app.handle("POST", "/api/drill/start",
                                  body={"mode": "dictation", "pack": "listen-pack", "count": 1})
        self.assertTrue(view["item"]["audio"])  # hearing it IS the task

    def test_homework_meaning_miss_records_korean_not_gloss(self):
        app = self.make_app(audio_enabled=False)
        status, view = app.handle("POST", "/api/drill/start",
                                  body={"mode": "homework", "pack": "topik-i-mini-pack", "course_id": "c01"})
        activity = view["id"]
        while True:
            status, result = app.handle("POST", f"/api/activity/{activity}/answer",
                                        body={"value": "완전오답"})
            if result.get("finished"):
                break
        glosses = {"today", "weather", "to be good", "library", "book", "to read"}
        for item in result["summary"]["missed"]:
            self.assertNotIn(item, glosses,
                             f"missed list leaked an English gloss: {item!r}")

    def test_homework_compose_item_tolerates_missing_period(self):
        app = self.make_app(audio_enabled=False)
        status, view = app.handle("POST", "/api/drill/start",
                                  body={"mode": "homework", "pack": "topik-i-mini-pack", "course_id": "c01"})
        activity = view["id"]
        saw_compose = False
        while True:
            item = view["item"]
            if item["kind"] == "compose":
                saw_compose = True
                # The model answer ends with a period; typing without it passes.
                expected = app._activities[activity]["items"][view["progress"][0]]["answer"]
                status, result = app.handle("POST", f"/api/activity/{activity}/answer",
                                            body={"value": expected.rstrip(".?!")})
                self.assertTrue(result["correct"], expected)
            else:
                accept = app._activities[activity]["items"][view["progress"][0]]["accept"][0]
                status, result = app.handle("POST", f"/api/activity/{activity}/answer",
                                            body={"value": accept})
            if result.get("finished"):
                break
            status, view = app.handle("GET", f"/api/activity/{activity}")
        self.assertTrue(saw_compose)
        self.assertEqual(result["summary"]["hits"], result["summary"]["total"])

    def test_conjugation_forms_and_drill_across_tenses(self):
        app = self.make_app(audio_enabled=False)
        status, forms = app.handle("GET", "/api/conjugation/forms")
        self.assertEqual(status, 200)
        keys = {f["key"] for f in forms["forms"]}
        self.assertTrue({"aeo", "seumnida", "past", "future", "if"} <= keys)
        for form in ("past", "future", "if"):
            status, view = app.handle("POST", "/api/drill/start",
                                      body={"mode": "conjugate", "form": form, "pack": "topik-i-mini-pack"})
            self.assertEqual(status, 200, form)
            self.assertEqual(view["label"], "Conjugation")
            self.assertIn("→", view["item"]["show"])

    def test_keyboard_chart_and_version(self):
        app = self.make_app(audio_enabled=False)
        status, keyboard = app.handle("GET", "/api/keyboard")
        self.assertEqual(status, 200)
        flat = [cell for row in keyboard["rows"] for cell in row if cell]
        self.assertIn(("Q", "ㅂ", "ㅃ"), [(c["key"], c["jamo"], c["shift"]) for c in flat])
        self.assertIn(None, keyboard["rows"][0])  # the hand-split gap survives
        status, state = app.handle("GET", "/api/state")
        self.assertRegex(state["version"], r"^\d+\.\d+\.\d+$")
        status, doctor = app.handle("GET", "/api/doctor")
        self.assertEqual(doctor["version"], state["version"])


class ContentEndpointTests(WebAppTestCase):
    def test_decks_report_stats_doctor(self):
        app = self.make_app(audio_enabled=False)
        status, deck = app.handle("GET", "/api/deck/flashcards", query={"pack": "topik-i-mini-pack"})
        self.assertEqual(status, 200)
        self.assertTrue(deck["cards"])
        status, grammar = app.handle("GET", "/api/deck/grammar", query={"pack": "topik-i-mini-pack"})
        self.assertTrue(grammar["cards"])
        status, stats = app.handle("GET", "/api/stats")
        self.assertIn("attempt_count", stats)
        status, doctor = app.handle("GET", "/api/doctor")
        self.assertEqual(len(doctor["checks"]), 8)  # incl. the optional Qwen3-TTS check
        status, lessons = app.handle("GET", "/api/compose/lessons")
        self.assertEqual(status, 200)
        status, facts = app.handle("GET", "/api/facts")
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()


class UnitVocabularyApiTests(WebAppTestCase):
    """Study-path stages expose their words, and the words are drillable."""

    def setUp(self):
        super().setUp()
        vocab = self.temp_dir / "vocabulary"
        vocab.mkdir()
        (vocab / "units.json").write_text(json.dumps({
            "schema_version": "topik-sim.vocabulary.v1",
            "words": [
                {"ko": "인사", "en": "greeting", "unit": "greetings"},
                {"ko": "이름", "en": "name", "unit": "greetings"},
                {"ko": "김치", "en": "kimchi", "unit": "food"},
            ],
        }, ensure_ascii=False), encoding="utf-8")

    def test_flashcards_deck_can_be_scoped_to_a_unit(self):
        app = self.make_app(audio_enabled=False)
        status, payload = app.handle("GET", "/api/deck/flashcards", query={"unit": "greetings"})
        self.assertEqual(status, 200)
        self.assertEqual({c["ko"] for c in payload["cards"]}, {"인사", "이름"})

    def test_recall_can_be_scoped_to_a_unit(self):
        app = self.make_app(audio_enabled=False)
        status, view = app.handle("POST", "/api/drill/start",
                                  body={"mode": "recall", "unit": "food", "count": 5})
        self.assertEqual(status, 200)
        self.assertEqual(view["progress"][1], 1)
        status, result = app.handle("POST", f"/api/activity/{view['id']}/answer",
                                    body={"value": "김치"})
        self.assertTrue(result["correct"])

    def test_vocab_review_can_be_scoped_to_a_unit(self):
        app = self.make_app(audio_enabled=False)
        status, view = app.handle("POST", "/api/drill/start",
                                  body={"mode": "vocab", "unit": "greetings", "count": 5})
        self.assertEqual(status, 200)
        self.assertIn(view["item"]["show"].split(":")[-1].strip(), {"greeting", "name"})

    def test_unknown_unit_is_rejected(self):
        app = self.make_app(audio_enabled=False)
        self.assertEqual(app.handle("GET", "/api/deck/flashcards", query={"unit": "nope"})[0], 400)
        self.assertEqual(app.handle("POST", "/api/drill/start",
                                    body={"mode": "recall", "unit": "nope"})[0], 400)

    def test_unit_scope_wins_over_a_pack_argument(self):
        """The picker sends one choice; a unit selection must not also filter by pack."""
        app = self.make_app(audio_enabled=False)
        status, view = app.handle("POST", "/api/drill/start",
                                  body={"mode": "recall", "unit": "food",
                                        "pack": "topik-i-mini-pack", "count": 5})
        self.assertEqual(status, 200)
        self.assertEqual(view["progress"][1], 1)   # only the unit's one word
