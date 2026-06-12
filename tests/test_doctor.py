import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from topik_sim import doctor
from topik_sim.cli import main
from topik_sim.library import import_pack


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


class DoctorTestCase(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        # Isolate config checks from any real topik.config.json in the workspace.
        self._old_config_env = os.environ.get("TOPIK_CONFIG")
        os.environ["TOPIK_CONFIG"] = str(self.temp_dir / "missing.config.json")

    def tearDown(self):
        if self._old_config_env is None:
            os.environ.pop("TOPIK_CONFIG", None)
        else:
            os.environ["TOPIK_CONFIG"] = self._old_config_env
        self._temp.cleanup()


class CheckFunctionTests(DoctorTestCase):
    def test_python_version_pass_and_fail(self):
        status, label, detail = doctor.check_python((3, 12, 1))
        self.assertEqual((status, label), (doctor.PASS, "Python"))
        self.assertIn("3.12.1", detail)

        status, _, detail = doctor.check_python((3, 8, 10))
        self.assertEqual(status, doctor.FAIL)
        self.assertIn("3.8.10", detail)
        self.assertIn("3.9", detail)

    def test_running_python_passes(self):
        status, _, detail = doctor.check_python()
        self.assertEqual(status, doctor.PASS)
        self.assertIn(str(sys.version_info[0]), detail)

    def test_prompt_toolkit_warn_when_missing(self):
        with patch("topik_sim.doctor.importlib.util.find_spec", return_value=None):
            status, _, detail = doctor.check_prompt_toolkit()
        self.assertEqual(status, doctor.WARN)
        self.assertIn("plain prompt", detail)

        with patch("topik_sim.doctor.importlib.util.find_spec", return_value=object()):
            status, _, _ = doctor.check_prompt_toolkit()
        self.assertEqual(status, doctor.PASS)

    def test_tts_runtime_warns_without_resolving_runtime(self):
        with patch("topik_sim.doctor.resolve_supertonic_python", side_effect=RuntimeError("no runtime")):
            status, _, detail = doctor.check_tts_runtime()
        self.assertEqual(status, doctor.WARN)
        self.assertIn("soundless", detail)

    def test_tts_runtime_warns_when_helper_missing(self):
        with patch("topik_sim.doctor.resolve_supertonic_python", return_value=Path(sys.executable)), patch(
            "topik_sim.doctor.supertonic_helper_path", return_value=self.temp_dir / "missing_helper.py"
        ):
            status, _, detail = doctor.check_tts_runtime()
        self.assertEqual(status, doctor.WARN)
        self.assertIn("helper missing", detail)
        self.assertIn("soundless", detail)

    def test_tts_runtime_warns_when_engine_not_importable(self):
        # The resolver can fall back to a Python that exists but has no
        # supertonic installed; doctor must not call that a PASS.
        with patch("topik_sim.doctor.resolve_supertonic_python", return_value=Path(sys.executable)), patch(
            "topik_sim.doctor._tts_engine_importable", return_value=False
        ):
            status, _, detail = doctor.check_tts_runtime()
        self.assertEqual(status, doctor.WARN)
        self.assertIn("setup-tts.ps1", detail)
        self.assertIn("soundless", detail)

    def test_tts_runtime_passes_when_engine_imports(self):
        with patch("topik_sim.doctor.resolve_supertonic_python", return_value=Path(sys.executable)), patch(
            "topik_sim.doctor._tts_engine_importable", return_value=True
        ):
            status, _, detail = doctor.check_tts_runtime()
        self.assertEqual(status, doctor.PASS)
        self.assertIn("supertonic_synth.py", detail)

    def test_ffmpeg_warn_and_pass(self):
        with patch("topik_sim.doctor.shutil.which", return_value=None):
            status, _, detail = doctor.check_ffmpeg()
        self.assertEqual(status, doctor.WARN)
        self.assertIn("compress", detail)

        with patch("topik_sim.doctor.shutil.which", return_value="C:/tools/ffmpeg.exe"):
            status, _, detail = doctor.check_ffmpeg()
        self.assertEqual(status, doctor.PASS)
        self.assertIn("ffmpeg.exe", detail)

    def test_config_missing_malformed_and_valid(self):
        status, _, detail = doctor.check_config()
        self.assertEqual(status, doctor.PASS)
        self.assertIn("no config file", detail)

        config_file = self.temp_dir / "topik.config.json"
        os.environ["TOPIK_CONFIG"] = str(config_file)
        config_file.write_text("{broken", encoding="utf-8")
        status, _, detail = doctor.check_config()
        self.assertEqual(status, doctor.FAIL)
        self.assertIn("Could not read config", detail)

        config_file.write_text(json.dumps({"shell": {"audio": False}}), encoding="utf-8")
        status, _, detail = doctor.check_config()
        self.assertEqual(status, doctor.PASS)
        self.assertIn("parsed", detail)

    def test_library_warn_empty_pass_with_packs_fail_on_errors(self):
        library_dir = self.temp_dir / "library"
        status, _, detail = doctor.check_library(library_dir)
        self.assertEqual(status, doctor.WARN)
        self.assertIn("topik-sim setup", detail)

        import_pack(SAMPLE_PACK, library_dir)
        status, _, detail = doctor.check_library(library_dir)
        self.assertEqual(status, doctor.PASS)
        self.assertIn("1 pack(s)", detail)

        (library_dir / "manifest.json").write_text(
            json.dumps({"schema_version": "bogus", "packs": []}), encoding="utf-8"
        )
        status, _, detail = doctor.check_library(library_dir)
        self.assertEqual(status, doctor.FAIL)
        self.assertIn("schema_version", detail)

    def test_library_fail_on_unreadable_manifest(self):
        library_dir = self.temp_dir / "library"
        library_dir.mkdir()
        (library_dir / "manifest.json").write_text("{broken", encoding="utf-8")
        status, _, detail = doctor.check_library(library_dir)
        self.assertEqual(status, doctor.FAIL)
        self.assertIn("could not read", detail)

    def test_data_dir_writable_and_not(self):
        data_dir = self.temp_dir / "data"
        status, _, detail = doctor.check_data_dir(data_dir)
        self.assertEqual(status, doctor.PASS)
        self.assertIn("writable", detail)
        self.assertEqual(list(data_dir.iterdir()), [])  # probe file cleaned up

        blocker = self.temp_dir / "blocker"
        blocker.write_text("a file, not a directory", encoding="utf-8")
        status, _, detail = doctor.check_data_dir(blocker)
        self.assertEqual(status, doctor.FAIL)
        self.assertIn("not writable", detail)


class RunChecksTests(DoctorTestCase):
    def test_labels_in_stable_order(self):
        checks = doctor.run_checks(library_dir=self.temp_dir / "library", data_dir=self.temp_dir / "data")
        self.assertEqual(
            [label for _, label, _ in checks],
            ["Python", "prompt_toolkit", "TTS runtime", "ffmpeg", "Config", "Library", "Data directory"],
        )
        for status, _, _ in checks:
            self.assertIn(status, {doctor.PASS, doctor.WARN, doctor.FAIL})

    def test_format_checks_aligns_columns_and_summarizes(self):
        checks = [
            (doctor.PASS, "Python", "3.12.1"),
            (doctor.WARN, "ffmpeg", "not on PATH"),
            (doctor.FAIL, "Data directory", "denied"),
        ]
        lines = doctor.format_checks(checks)
        self.assertEqual(lines[0], "PASS  Python          3.12.1")
        self.assertEqual(lines[1], "WARN  ffmpeg          not on PATH")
        self.assertEqual(lines[2], "FAIL  Data directory  denied")
        self.assertEqual(lines[-1], "1 passed, 1 warning(s), 1 failure(s).")
        self.assertTrue(doctor.has_failure(checks))
        self.assertFalse(doctor.has_failure(checks[:2]))


class DoctorCommandTests(DoctorTestCase):
    def run_doctor(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main([
                "doctor",
                "--library",
                str(self.temp_dir / "library"),
                "--data-dir",
                str(self.temp_dir / "data"),
            ])
        return code, buffer.getvalue()

    def test_exit_zero_without_failures(self):
        code, out = self.run_doctor()
        self.assertEqual(code, 0)
        self.assertIn("Python", out)
        self.assertIn("Library", out)
        self.assertIn("passed,", out)

    def test_exit_one_when_a_check_fails(self):
        library_dir = self.temp_dir / "library"
        library_dir.mkdir()
        (library_dir / "manifest.json").write_text("{broken", encoding="utf-8")
        code, out = self.run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)


if __name__ == "__main__":
    unittest.main()
