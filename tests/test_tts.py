import subprocess
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
    prompt_after_answer,
    question_display_passage,
)
from topik_sim.content import load_pack
from topik_sim.tts import (
    TTSConfig,
    adjust_wav_volume,
    build_provider,
    collect_question_speech_texts,
    play_audio,
    stable_audio_name,
    synthesize_many,
    transcript_text,
)
from topik_sim.tts_cli import main as tts_main


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
        speaker = stable_audio_name("hello", provider="melo", language="KR", speaker_id="KR")
        more_steps = stable_audio_name("hello", provider="supertonic", language="KR", steps=20)
        self.assertEqual(first, second)
        self.assertNotEqual(first, speaker)
        self.assertNotEqual(stable_audio_name("hello", provider="supertonic", language="KR"), more_steps)
        self.assertTrue(first.endswith(".wav"))
        self.assertNotIn("hello", first)

    def test_play_audio_applies_volume_to_temp_copy_only(self):
        import struct
        import wave

        with tempfile.TemporaryDirectory() as temp_dir:
            wav_path = Path(temp_dir) / "sample.wav"
            with wave.open(str(wav_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(44100)
                wav.writeframes(struct.pack("<hh", 1000, -1000))

            played = {}

            def fake_play(path):
                played["path"] = Path(path)
                with wave.open(str(path), "rb") as wav:
                    played["values"] = struct.unpack("<hh", wav.readframes(2))

            with patch("topik_sim.tts._play_audio_file", side_effect=fake_play):
                play_audio(wav_path, volume=0.5)

            self.assertNotEqual(played["path"], wav_path)
            self.assertEqual(played["values"], (500, -500))
            with wave.open(str(wav_path), "rb") as wav:
                self.assertEqual(struct.unpack("<hh", wav.readframes(2)), (1000, -1000))

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

    def test_post_answer_pause_can_replay_before_continuing(self):
        output = StringIO()
        with patch("builtins.input", side_effect=["/replay", ""]), redirect_stdout(output):
            prompt_after_answer([])
        self.assertIn("No question audio is available to replay.", output.getvalue())

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

    def test_supertonic_resolver_prefers_workspace_venv(self):
        import sys

        from topik_sim import tts as tts_module

        with tempfile.TemporaryDirectory() as temp_dir:
            venv_python = Path(temp_dir) / ".venv-tts" / "Scripts" / "python.exe"
            venv_python.parent.mkdir(parents=True)
            venv_python.write_bytes(b"")
            with patch.object(tts_module, "DEFAULT_WORKSPACE_TTS_PYTHONS", (venv_python,)):
                resolved = tts_module.resolve_supertonic_python(TTSConfig())
            self.assertEqual(resolved, venv_python)

        # An explicit --tts-python always wins over the workspace venv.
        with patch.object(tts_module, "DEFAULT_WORKSPACE_TTS_PYTHONS", (Path(sys.executable),)):
            resolved = tts_module.resolve_supertonic_python(TTSConfig(tts_python=Path(sys.executable)))
        self.assertEqual(resolved, Path(sys.executable))

    def test_supertonic_provider_is_available_without_loading_model(self):
        provider = build_provider("supertonic")
        self.assertIn("F1", provider.list_speakers(TTSConfig(provider="supertonic")))

    def test_tts_cli_lists_supertonic_speakers(self):
        output = StringIO()
        with redirect_stdout(output):
            exit_code = tts_main(["list-speakers"])
        self.assertEqual(exit_code, 0)
        self.assertIn("F1", output.getvalue())

    def test_tts_cli_play_reports_missing_audio(self):
        output = StringIO()
        with redirect_stdout(output), patch("sys.stderr", output):
            exit_code = tts_main(["play", "missing.wav"])
        self.assertEqual(exit_code, 1)
        self.assertIn("Audio file not found", output.getvalue())

    def test_tts_cli_speak_plays_temp_audio_by_default(self):
        captured = {}

        def fake_synthesize(texts, config):
            captured["texts"] = texts
            captured["config"] = config
            self.assertNotEqual(config.output_dir, Path("data/audio_cache"))
            return [config.output_dir / "spoken.wav"]

        output = StringIO()
        with patch("topik_sim.tts_cli.synthesize_many", side_effect=fake_synthesize), redirect_stdout(output):
            exit_code = tts_main(["speak", "hello"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["texts"], ["hello"])
        self.assertTrue(captured["config"].playback)
        self.assertTrue(captured["config"].force)
        self.assertEqual(output.getvalue(), "")

    def test_tts_cli_speak_save_keeps_and_prints_cached_audio(self):
        def fake_synthesize(texts, config):
            self.assertEqual(config.output_dir, Path("data/audio_cache"))
            self.assertFalse(config.playback)
            return [config.output_dir / "spoken.wav"]

        output = StringIO()
        with patch("topik_sim.tts_cli.synthesize_many", side_effect=fake_synthesize), redirect_stdout(output):
            exit_code = tts_main(["speak", "hello", "--save"])

        self.assertEqual(exit_code, 0)
        self.assertIn("data", output.getvalue())
        self.assertIn("spoken.wav", output.getvalue())


if __name__ == "__main__":
    unittest.main()


class Qwen3ProviderTests(unittest.TestCase):
    """Qwen3-TTS: a second engine behind the same provider protocol."""

    def test_build_provider_returns_qwen3(self):
        from topik_sim.tts import Qwen3TTSProvider

        for name in ("qwen3", "Qwen3-TTS", "qwen"):
            self.assertIsInstance(build_provider(name), Qwen3TTSProvider)

    def test_unknown_provider_message_lists_qwen3(self):
        with self.assertRaises(ValueError) as caught:
            build_provider("nope")
        self.assertIn("qwen3", str(caught.exception))

    def test_language_map_uses_the_models_own_names(self):
        from topik_sim.tts import qwen3_language

        self.assertEqual(qwen3_language("KR"), "korean")
        self.assertEqual(qwen3_language("ko"), "korean")
        self.assertEqual(qwen3_language("en"), "english")
        self.assertEqual(qwen3_language("japanese"), "japanese")
        self.assertEqual(qwen3_language(""), "auto")

    def test_resolver_prefers_explicit_config_then_env(self):
        import os
        import tempfile
        from topik_sim.tts import TTSConfig, resolve_qwen3_python

        with tempfile.TemporaryDirectory() as temp:
            explicit = Path(temp) / "explicit"; explicit.write_text("")
            from_env = Path(temp) / "from_env"; from_env.write_text("")
            with patch.dict(os.environ, {"TOPIK_QWEN3_PYTHON": str(from_env)}):
                self.assertEqual(resolve_qwen3_python(TTSConfig(tts_python=explicit)), explicit)
                self.assertEqual(resolve_qwen3_python(TTSConfig()), from_env)

    def test_resolver_reports_setup_script_when_missing(self):
        import os
        from topik_sim.tts import TTSConfig, resolve_qwen3_python

        with patch.dict(os.environ, {"TOPIK_QWEN3_PYTHON": ""}, clear=False), \
             patch("topik_sim.tts.DEFAULT_WORKSPACE_QWEN3_PYTHONS", ()):
            with self.assertRaises(RuntimeError) as caught:
                resolve_qwen3_python(TTSConfig())
        self.assertIn("setup-tts-qwen3.sh", str(caught.exception))

    def test_provider_runs_helper_with_korean_voice_and_language(self):
        import tempfile
        from topik_sim.tts import Qwen3TTSProvider, TTSConfig

        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            Path(command[command.index("--output") + 1]).write_bytes(b"RIFFfake")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as temp:
            python = Path(temp) / "python"; python.write_text("")
            out = Path(temp) / "out.wav"
            with patch("topik_sim.tts.subprocess.run", side_effect=fake_run):
                Qwen3TTSProvider().synthesize_to_file(
                    "안녕하세요", out, TTSConfig(tts_python=python, language="KR", speed=0.75))
            command, kwargs = calls[0]
            self.assertEqual(command[0], str(python))
            self.assertTrue(command[1].endswith("qwen3_synth.py"))
            self.assertEqual(command[command.index("--voice") + 1], "sohee")
            self.assertEqual(command[command.index("--lang") + 1], "korean")
            self.assertEqual(command[command.index("--speed") + 1], "0.75")
            self.assertEqual(kwargs["input"], "안녕하세요")
            self.assertTrue(out.exists())

    def test_provider_surfaces_helper_failure(self):
        import tempfile
        from topik_sim.tts import Qwen3TTSProvider, TTSConfig

        def failing_run(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="mlx-audio exploded")

        with tempfile.TemporaryDirectory() as temp:
            python = Path(temp) / "python"; python.write_text("")
            with patch("topik_sim.tts.subprocess.run", side_effect=failing_run):
                with self.assertRaises(RuntimeError) as caught:
                    Qwen3TTSProvider().synthesize_to_file("x", Path(temp) / "o.wav", TTSConfig(tts_python=python))
        self.assertIn("mlx-audio exploded", str(caught.exception))

    def test_speakers_include_the_korean_default(self):
        from topik_sim.tts import DEFAULT_QWEN3_VOICE, Qwen3TTSProvider, TTSConfig

        speakers = Qwen3TTSProvider().list_speakers(TTSConfig())
        self.assertIn(DEFAULT_QWEN3_VOICE, speakers)
        self.assertEqual(len(speakers), 9)
