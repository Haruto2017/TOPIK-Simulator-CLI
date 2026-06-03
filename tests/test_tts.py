import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from topik_sim.content import load_pack
from topik_sim.tts import TTSConfig, collect_question_speech_texts, synthesize_many, stable_audio_name


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


class TTSTests(unittest.TestCase):
    def test_collect_question_speech_texts_includes_korean_passage_and_teaching(self):
        pack = load_pack(SAMPLE_PACK)
        question = pack.questions()[0]
        texts = collect_question_speech_texts(question, include_prompt=False, include_explanation=True)
        joined = "\n".join(texts)
        self.assertIn("오늘은 날씨가 좋습니다.", joined)
        self.assertIn("오늘", joined)
        self.assertNotIn("What does the sentence mean?", joined)

    def test_stable_audio_name_is_repeatable_and_safe(self):
        first = stable_audio_name("안녕하세요", provider="melo", language="KR")
        second = stable_audio_name("안녕하세요", provider="melo", language="KR")
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(".wav"))
        self.assertNotIn("안녕", first)

    def test_synthesize_many_skips_existing_cache_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = TTSConfig(output_dir=Path(temp_dir), provider="melo", device="cuda:0")
            existing = Path(temp_dir) / stable_audio_name("안녕하세요", provider="melo", language="KR")
            existing.write_bytes(b"fake")
            with patch("topik_sim.tts.build_provider") as build_provider:
                paths = synthesize_many(["안녕하세요"], config)
            build_provider.assert_not_called()
            self.assertEqual(paths, [existing])


if __name__ == "__main__":
    unittest.main()

