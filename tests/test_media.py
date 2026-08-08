import json
import tempfile
import unittest
from pathlib import Path

from topik_sim.library import import_pack
from topik_sim.media import media_mime_type, resolve_media_ref
from topik_sim.tts import TTSConfig
from topik_sim.web.app import WebApp


class ResolveMediaRefTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def test_non_file_refs_resolve_to_none(self):
        self.assertIsNone(resolve_media_ref(""))
        self.assertIsNone(resolve_media_ref(None))
        self.assertIsNone(resolve_media_ref("transcript-only:l-001"))
        self.assertIsNone(resolve_media_ref("cd1-track3"))

    def test_absolute_path_resolves_only_when_file_exists(self):
        target = self.temp_dir / "clip.mp3"
        self.assertIsNone(resolve_media_ref(f"file:{target}"))
        target.write_bytes(b"ID3fake")
        self.assertEqual(resolve_media_ref(f"file:{target}"), target)

    def test_relative_path_resolves_against_base_dirs(self):
        (self.temp_dir / "audio").mkdir()
        target = self.temp_dir / "audio" / "q01.mp3"
        target.write_bytes(b"ID3fake")
        found = resolve_media_ref("file:audio/q01.mp3", base_dirs=(self.temp_dir,))
        self.assertEqual(found, target)
        self.assertIsNone(resolve_media_ref("file:audio/missing.mp3", base_dirs=(self.temp_dir,)))

    def test_mime_types(self):
        self.assertEqual(media_mime_type(Path("a.mp3")), "audio/mpeg")
        self.assertEqual(media_mime_type(Path("a.PNG")), "image/png")
        self.assertEqual(media_mime_type(Path("a.xyz")), "application/octet-stream")


def media_pack_data(audio_path: Path, image_path: Path):
    return {
        "schema_version": "topik-sim.content.v1",
        "pack_id": "media-pack",
        "pack_version": "0.0.1",
        "title": "Official Media Pack",
        "topik_level": "TOPIK_I",
        "language_pair": "ko-ko",
        "source_type": "user_provided",
        "sections": [
            {
                "section_id": "listening",
                "title": "듣기",
                "questions": [
                    {
                        "question_id": "l-001",
                        "order": 1,
                        "skill": "listening",
                        "audio_ref": f"file:{audio_path}",
                        "image_ref": f"file:{image_path}",
                        "passage": "Transcript: 남자: 안녕하세요.",
                        "prompt": "알맞은 그림을 고르십시오.",
                        "options": [
                            {"id": "1", "text": "그림 ①"},
                            {"id": "2", "text": "그림 ②"},
                        ],
                        "answer": {"type": "single_choice", "correct_option_id": "1"},
                        "explanation": {"summary": "The greeting matches picture one."},
                    }
                ],
            }
        ],
    }


class WebFileMediaTests(unittest.TestCase):
    """Past-paper packs: official MP3 beats TTS, images are served."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        self.audio_file = self.temp_dir / "q01.mp3"
        self.audio_file.write_bytes(b"ID3official-audio")
        self.image_file = self.temp_dir / "q01.png"
        self.image_file.write_bytes(b"\x89PNGofficial-image")
        pack_path = self.temp_dir / "media_pack.json"
        pack_path.write_text(
            json.dumps(media_pack_data(self.audio_file, self.image_file), ensure_ascii=False),
            encoding="utf-8",
        )
        import_pack(pack_path, self.temp_dir / "library")
        self.app = WebApp(
            library_dir=self.temp_dir / "library",
            attempt_dir=self.temp_dir / "attempts",
            tts_config=TTSConfig(output_dir=self.temp_dir / "audio-cache"),
            audio_enabled=False,  # file audio must not depend on TTS
            seed=0,
        )
        status, view = self.app.handle("POST", "/api/exam/start", body={"pack": "media-pack"})
        assert status == 200
        self.activity = view["id"]
        self.question = view["question"]

    def tearDown(self):
        self._temp.cleanup()

    def test_view_reports_playable_audio_and_image_with_tts_off(self):
        self.assertEqual(self.question["audio_parts"], 1)
        self.assertTrue(self.question["has_image"])
        self.assertTrue(self.question["transcript_hidden"])
        self.assertNotIn("passage", self.question)

    def test_audio_endpoint_serves_the_official_recording(self):
        status, payload = self.app.handle(
            "GET", f"/api/activity/{self.activity}/audio", query={"part": "0"}
        )
        self.assertEqual(status, 200)
        body, mime = payload
        self.assertEqual(body, self.audio_file.read_bytes())
        self.assertEqual(mime, "audio/mpeg")

    def test_image_endpoint_serves_the_question_image(self):
        status, payload = self.app.handle("GET", f"/api/activity/{self.activity}/image")
        self.assertEqual(status, 200)
        body, mime = payload
        self.assertEqual(body, self.image_file.read_bytes())
        self.assertEqual(mime, "image/png")

    def test_transcript_still_revealed_after_answer(self):
        status, result = self.app.handle(
            "POST", f"/api/activity/{self.activity}/answer", body={"value": "1"}
        )
        self.assertEqual(status, 200)
        self.assertIn("안녕하세요", result["transcript"])


if __name__ == "__main__":
    unittest.main()
