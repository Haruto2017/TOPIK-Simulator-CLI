import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from topik_sim.config import config_value, load_config
from topik_sim.cli import build_parser
from topik_sim.tts_cli import build_tts_config


class ConfigTests(unittest.TestCase):
    def test_missing_config_means_builtin_defaults(self):
        self.assertEqual(load_config("does/not/exist.json"), {})

    def test_malformed_config_raises_with_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broken.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "broken.json"):
                load_config(path)
            path.write_text('["list"]', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON object"):
                load_config(path)

    def test_config_value_walks_sections(self):
        config = {"tts": {"volume": 0.5}}
        self.assertEqual(config_value(config, "tts", "volume", 1.0), 0.5)
        self.assertEqual(config_value(config, "tts", "speed", 1.0), 1.0)
        self.assertEqual(config_value(config, "paths", "library", "x"), "x")

    def test_config_file_changes_cli_defaults_but_flags_win(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "topik.config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "tts": {"volume": 0.5, "voice": "M1"},
                        "paths": {"attempts": "custom/attempts", "library": "custom/library"},
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"TOPIK_CONFIG": str(config_path)}):
                parser = build_parser()
                args = parser.parse_args(["take", "some-pack"])
                self.assertEqual(args.tts_volume, 0.5)
                self.assertEqual(args.tts_speaker_id, "M1")
                self.assertEqual(args.attempt_dir, "custom/attempts")
                self.assertEqual(args.library, "custom/library")
                config = build_tts_config(args)
                self.assertEqual(config.volume, 0.5)

                overridden = parser.parse_args(["take", "some-pack", "--tts-volume", "1.2"])
                self.assertEqual(overridden.tts_volume, 1.2)


if __name__ == "__main__":
    unittest.main()
