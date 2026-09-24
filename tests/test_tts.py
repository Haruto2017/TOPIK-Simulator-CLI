import subprocess
import os
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
    def setUp(self):
        # Isolate CLI-driven tests from any real topik.config.json in the
        # workspace (a developer's machine may default to another engine).
        self._temp = tempfile.TemporaryDirectory()
        self._old_config_env = os.environ.get("TOPIK_CONFIG")
        os.environ["TOPIK_CONFIG"] = str(Path(self._temp.name) / "missing.config.json")

    def tearDown(self):
        if self._old_config_env is None:
            os.environ.pop("TOPIK_CONFIG", None)
        else:
            os.environ["TOPIK_CONFIG"] = self._old_config_env
        self._temp.cleanup()

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


class ProsodyStyleTests(unittest.TestCase):
    """A reading style shapes the audio, so it must shape the cache identity — but
    only for engines that have one, or every existing Supertonic file would be orphaned."""

    def test_style_changes_the_name_only_when_set(self):
        base = stable_audio_name("안녕", provider="supertonic", language="KR")
        same = stable_audio_name("안녕", provider="supertonic", language="KR", style="")
        styled = stable_audio_name("안녕", provider="qwen3", language="KR", style="calm|t=0.40")
        other = stable_audio_name("안녕", provider="qwen3", language="KR", style="bright|t=0.40")
        self.assertEqual(base, same)
        self.assertNotEqual(styled, other)

    def test_effective_style_is_empty_for_supertonic_and_set_for_qwen3(self):
        import os
        from topik_sim.tts import DEFAULT_QWEN3_INSTRUCT, DEFAULT_QWEN3_TEMPERATURE, TTSConfig, effective_style

        self.assertEqual(effective_style(TTSConfig(provider="supertonic")), "")
        with patch.dict(os.environ, {"TOPIK_QWEN3_INSTRUCT": "", "TOPIK_QWEN3_TEMPERATURE": ""}):
            default = effective_style(TTSConfig(provider="qwen3"))
        self.assertIn(DEFAULT_QWEN3_INSTRUCT, default)
        self.assertIn(f"t={DEFAULT_QWEN3_TEMPERATURE:.2f}", default)
        custom = effective_style(TTSConfig(provider="qwen3", style="whisper it", temperature=0.2))
        self.assertEqual(custom, "whisper it|t=0.20")

    def test_env_override_beats_default_but_not_explicit_config(self):
        import os
        from topik_sim.tts import TTSConfig, qwen3_instruct, qwen3_temperature

        with patch.dict(os.environ, {"TOPIK_QWEN3_INSTRUCT": "from env", "TOPIK_QWEN3_TEMPERATURE": "0.7"}):
            self.assertEqual(qwen3_instruct(TTSConfig(provider="qwen3")), "from env")
            self.assertEqual(qwen3_temperature(TTSConfig(provider="qwen3")), 0.7)
            self.assertEqual(qwen3_instruct(TTSConfig(provider="qwen3", style="explicit")), "explicit")
            self.assertEqual(qwen3_temperature(TTSConfig(provider="qwen3", temperature=0.1)), 0.1)

    def test_provider_passes_style_temperature_and_a_deterministic_seed(self):
        import os
        import tempfile
        from topik_sim.tts import Qwen3TTSProvider, TTSConfig

        seen = {}

        def fake_run(command, **kwargs):
            seen["cmd"] = command
            Path(command[command.index("--output") + 1]).write_bytes(b"RIFFfake")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as temp:
            python = Path(temp) / "python"; python.write_text("")
            with patch("topik_sim.tts.subprocess.run", side_effect=fake_run), \
                 patch.dict(os.environ, {"TOPIK_QWEN3_INSTRUCT": "", "TOPIK_QWEN3_TEMPERATURE": ""}):
                Qwen3TTSProvider().synthesize_to_file(
                    "x", Path(temp) / "o.wav", TTSConfig(tts_python=python, style="steady", temperature=0.35))
        cmd = seen["cmd"]
        self.assertEqual(cmd[cmd.index("--instruct") + 1], "steady")
        self.assertEqual(cmd[cmd.index("--temperature") + 1], "0.35")
        self.assertEqual(cmd[cmd.index("--seed") + 1], "auto")

    def test_cli_flags_reach_the_config(self):
        import argparse
        from topik_sim.tts_cli import add_tts_arguments, build_tts_config

        parser = argparse.ArgumentParser(); add_tts_arguments(parser, config={})
        cfg = build_tts_config(parser.parse_args(["--tts-style", "gentle", "--tts-temperature", "0.5"]))
        self.assertEqual(cfg.style, "gentle")
        self.assertEqual(cfg.temperature, 0.5)
        cfg = build_tts_config(parser.parse_args([]))
        self.assertEqual(cfg.style, "")
        self.assertIsNone(cfg.temperature)


class SpeakerTurnTests(unittest.TestCase):
    """Transcripts tag turns 남자:/여자:; each turn gets its own voice and the tag is never spoken."""

    def test_dialogue_splits_into_role_tagged_turns_without_tags(self):
        from topik_sim.tts import split_speaker_turns

        turns = split_speaker_turns("남자: 학생이에요? 여자: 네, 학생이에요.")
        self.assertEqual(turns, [{"text": "학생이에요?", "role": "male"},
                                 {"text": "네, 학생이에요.", "role": "female"}])
        for turn in turns:
            self.assertNotIn("남자", turn["text"]); self.assertNotIn("여자", turn["text"])

    def test_untagged_text_is_one_narration_turn_and_lead_in_is_narration(self):
        from topik_sim.tts import split_speaker_turns

        self.assertEqual(split_speaker_turns("오늘은 날씨가 좋습니다."), [{"text": "오늘은 날씨가 좋습니다.", "role": None}])
        turns = split_speaker_turns("안내 방송입니다. 여자： 문이 닫힙니다.")
        self.assertEqual([t["role"] for t in turns], [None, "female"])
        self.assertEqual(split_speaker_turns("   "), [])

    def test_question_segments_keep_prompt_as_narration_and_dedupe(self):
        from topik_sim.tts import collect_speech_segments

        question = {"skill": "listening", "passage": "Transcript: 남자: 안녕하세요. 여자: 안녕하세요.",
                    "prompt": "무엇을 하고 있습니까?", "audio_ref": "transcript-only:x"}
        segments = collect_speech_segments(question)
        self.assertEqual([s["role"] for s in segments], ["male", "female", None])
        self.assertEqual(segments[-1]["text"], "무엇을 하고 있습니까?")
        # the string view is tag-free and per turn
        self.assertEqual(collect_question_speech_texts(question, include_prompt=False), ["안녕하세요."])

    def test_role_voices_default_per_engine_and_can_be_overridden(self):
        from topik_sim.tts import TTSConfig, voice_for_role

        qwen = TTSConfig(provider="qwen3")
        self.assertEqual((voice_for_role("male", qwen), voice_for_role("female", qwen)), ("ryan", "sohee"))
        super_ = TTSConfig(provider="supertonic", speaker_id="F2")
        self.assertEqual((voice_for_role("male", super_), voice_for_role("female", super_), voice_for_role(None, super_)),
                         ("M1", "F1", "F2"))
        custom = TTSConfig(provider="qwen3", male_speaker_id="dylan", female_speaker_id="serena")
        self.assertEqual((voice_for_role("male", custom), voice_for_role("female", custom)), ("dylan", "serena"))
        unknown = TTSConfig(provider="melo", speaker_id="KR")
        self.assertEqual(voice_for_role("male", unknown), "KR")  # no presets: narration voice

    def test_synthesize_segments_uses_a_voice_per_turn(self):
        import tempfile
        from topik_sim.tts import TTSConfig, synthesize_segments

        spoken = []

        class FakeProvider:
            def synthesize_to_file(self, text, output_path, config):
                spoken.append((text, config.speaker_id)); output_path.write_bytes(b"RIFF")
            def list_speakers(self, config): return {}

        with tempfile.TemporaryDirectory() as temp, patch("topik_sim.tts.build_provider", return_value=FakeProvider()):
            paths = synthesize_segments(
                [{"text": "학생이에요?", "role": "male"}, {"text": "네.", "role": "female"}, {"text": "질문", "role": None}],
                TTSConfig(provider="qwen3", output_dir=Path(temp)))
        self.assertEqual(len(paths), 3)
        self.assertEqual(spoken, [("학생이에요?", "ryan"), ("네.", "sohee"), ("질문", None)])
        self.assertEqual(len({p.name for p in paths}), 3)  # distinct cache entries per voice

    def test_cli_role_voice_flags_reach_the_config(self):
        import argparse
        from topik_sim.tts_cli import add_tts_arguments, build_tts_config

        parser = argparse.ArgumentParser(); add_tts_arguments(parser, config={})
        cfg = build_tts_config(parser.parse_args(["--tts-male-voice", "eric", "--tts-female-voice", "vivian"]))
        self.assertEqual((cfg.male_speaker_id, cfg.female_speaker_id), ("eric", "vivian"))
        self.assertIsNone(build_tts_config(parser.parse_args([])).male_speaker_id)
