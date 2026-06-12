import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from topik_sim.content import validate_pack_data
from topik_sim.library import import_pack
from topik_sim.tts import _play_audio_file


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


def _pack_data(pack_id="safe-pack", version="0.1.0"):
    data = json.loads(SAMPLE_PACK.read_text(encoding="utf-8"))
    data["pack_id"] = pack_id
    data["pack_version"] = version
    return data


class PackSlugValidationTests(unittest.TestCase):
    def test_traversal_pack_ids_are_rejected(self):
        for bad in ("../escape", "..\\escape", "a/b", "a\\b", "..", "UPPER", "spa ce", ""):
            errors = validate_pack_data(_pack_data(pack_id=bad))
            self.assertTrue(
                any("pack_id" in error for error in errors),
                f"pack_id {bad!r} should be rejected",
            )

    def test_traversal_versions_are_rejected(self):
        for bad in ("../1", "..", "0.1/0", "0.1\\0", ".hidden"):
            errors = validate_pack_data(_pack_data(version=bad))
            self.assertTrue(
                any("pack_version" in error for error in errors),
                f"pack_version {bad!r} should be rejected",
            )

    def test_normal_slugs_still_pass(self):
        self.assertEqual(validate_pack_data(_pack_data()), [])
        self.assertEqual(validate_pack_data(_pack_data("topik-i-mock_01", "0.1.1-rc1")), [])

    def test_import_refuses_to_escape_the_library(self):
        # Bypass contract validation to prove the import's own guard holds.
        with tempfile.TemporaryDirectory() as temp_dir:
            library = Path(temp_dir) / "library"
            pack_path = Path(temp_dir) / "hostile.json"
            pack_path.write_text(json.dumps(_pack_data()), encoding="utf-8")
            with patch("topik_sim.library.load_pack") as fake_load:
                pack = type(
                    "FakePack",
                    (),
                    {
                        "pack_id": "../..",
                        "data": {"pack_version": "0.1.0", "topik_level": "TOPIK_I", "title": "x"},
                        "path": pack_path,
                        "title": "x",
                        "questions": lambda self: [],
                    },
                )()
                fake_load.return_value = pack
                with self.assertRaisesRegex(ValueError, "escapes the library"):
                    import_pack(pack_path, library)
            self.assertFalse((Path(temp_dir) / "0.1.0.json").exists())


@unittest.skipUnless(sys.platform.startswith("win"), "Windows playback path")
class PlaybackQuotingTests(unittest.TestCase):
    def test_quotes_in_paths_cannot_escape_the_command_string(self):
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command

            class Result:
                returncode = 0

            return Result()

        hostile = Path("C:/tmp/evil'); Start-Process calc; ('.wav")
        with patch("topik_sim.tts.subprocess.run", side_effect=fake_run):
            _play_audio_file(hostile)
        script = captured["command"][-1]
        # The doubled quote keeps the whole path inside the string literal.
        self.assertIn("evil''); Start-Process calc; (''", script)
        self.assertEqual(script.count("SoundPlayer '"), 1)


if __name__ == "__main__":
    unittest.main()
