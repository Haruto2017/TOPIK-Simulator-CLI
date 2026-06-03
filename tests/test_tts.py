import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from topik_sim.cli import (
    build_tts_config,
    is_listening_question,
    is_replay_request,
    print_post_answer_transcript,
    question_display_passage,
)
from topik_sim.content import load_pack
from topik_sim.tts import (
    TTSConfig,
    adjust_wav_volume,
    build_provider,
    collect_question_speech_texts,
    stable_audio_name,
    synthesize_many,
    transcript_text,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"
HELLO_KO = "\uc548\ub155\ud558\uc138\uc694"


class TTSTests(unittest.TestCase):
    def test_collect_question_speech_texts_includes_korean_passage_and_teaching(self):
        pack = load_pack(SAMPLE_PACK)
        question = pack.questions()[0]
        texts = collect_question_speech_texts(question, include_prompt=False, include_explanation=True)
        joined = "\n".join(texts)
        self.assertIn("\uc624\ub298\uc740 \ub0a0\uc528\uac00 \uc88b\uc2b5\ub2c8\ub2e4.", joined)
        self.assertIn("\uc624\ub298", joined)
        self.assertNotIn("What does the sentence mean?", joined)

    def test_stable_audio_name_is_repeatable_and_safe(self):
        first = stable_audio_name("hello", provider="melo", language="KR")
        second = stable_audio_name("hello", provider="melo", language="KR")
        louder = stable_audio_name("hello", provider="melo", language="KR", volume=1.4)
        speaker = stable_audio_name("hello", provider="melo", language="KR", speaker_id="KR")
        more_steps = stable_audio_name("hello", provider="supertonic", language="KR", steps=20)
        self.assertEqual(first, second)
        self.assertNotEqual(first, louder)
        self.assertNotEqual(first, speaker)
        self.assertNotEqual(stable_audio_name("hello", provider="supertonic", language="KR"), more_steps)
        self.assertTrue(first.endswith(".wav"))
        self.assertNotIn("hello", first)

    def test_synthesize_many_skips_existing_cache_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = TTSConfig(output_dir=Path(temp_dir), provider="melo", device="cuda:0")
            existing = Path(temp_dir) / stable_audio_name(HELLO_KO, provider="melo", language="KR")
            existing.write_bytes(b"fake")
            with patch("topik_sim.tts.build_provider") as build_provider:
                paths = synthesize_many([HELLO_KO], config)
            build_provider.assert_not_called()
            self.assertEqual(paths, [existing])

    def test_adjust_wav_volume_scales_pcm_samples(self):
        import struct
        import wave

        with tempfile.TemporaryDirectory() as temp_dir:
            wav_path = Path(temp_dir) / "sample.wav"
            with wave.open(str(wav_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(44100)
                wav.writeframes(struct.pack("<hhh", 1000, -1000, 2000))

            adjust_wav_volume(wav_path, 0.5)

            with wave.open(str(wav_path), "rb") as wav:
                values = struct.unpack("<hhh", wav.readframes(3))
            self.assertEqual(values, (500, -500, 1000))

    def test_listening_transcript_is_speech_source_but_hidden_by_default(self):
        question = {
            "question_id": "l-001",
            "skill": "listening",
            "audio_ref": "transcript-only:l-001",
            "passage": f"Transcript: {HELLO_KO}.",
            "prompt": "What is the speaker saying?",
        }
        self.assertTrue(is_listening_question(question))
        self.assertEqual(transcript_text(question), f"{HELLO_KO}.")
        self.assertEqual(collect_question_speech_texts(question), [f"{HELLO_KO}."])
        self.assertIsNone(question_display_passage(question, show_transcript=False))
        self.assertEqual(question_display_passage(question, show_transcript=True), f"Transcript: {HELLO_KO}.")

    def test_listening_transcript_is_shown_after_answer(self):
        question = {
            "question_id": "l-001",
            "skill": "listening",
            "audio_ref": "transcript-only:l-001",
            "passage": f"Transcript: {HELLO_KO}.",
        }
        output = StringIO()
        with redirect_stdout(output):
            print_post_answer_transcript(question, was_shown_before_answer=False)
        self.assertIn(f"Transcript: {HELLO_KO}.", output.getvalue())

        output = StringIO()
        with redirect_stdout(output):
            print_post_answer_transcript(question, was_shown_before_answer=True)
        self.assertEqual(output.getvalue(), "")

    def test_replay_commands_are_distinct_from_answer_choices(self):
        self.assertTrue(is_replay_request("/replay"))
        self.assertTrue(is_replay_request("/R"))
        self.assertTrue(is_replay_request(" replay "))
        self.assertFalse(is_replay_request("A"))
        self.assertFalse(is_replay_request("r"))

    def test_tts_volume_must_be_positive(self):
        class Args:
            tts_provider = "melo"
            tts_language = "KR"
            tts_device = "cuda:0"
            tts_output_dir = "data/audio_cache"
            tts_speed = 1.0
            tts_volume = 0.0
            tts_play = False
            tts_force = False
            tts_speaker_id = None
            tts_speaker_wav = None
            tts_onnx_provider = "dml"
            tts_steps = 10
            tts_python = None

        with self.assertRaisesRegex(ValueError, "volume"):
            build_tts_config(Args())

    def test_supertonic_provider_is_available_without_loading_model(self):
        provider = build_provider("supertonic")
        self.assertIn("F1", provider.list_speakers(TTSConfig(provider="supertonic")))


if __name__ == "__main__":
    unittest.main()
