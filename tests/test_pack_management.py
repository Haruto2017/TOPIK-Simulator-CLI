import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from topik_sim.cli import main
from topik_sim.content import validate_pack_data
from topik_sim.library import import_pack, latest_packs, list_packs, load_pack_ref, set_pack_hidden
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import PICK_PACK, Shell

try:
    from test_shell import StubPrefetcher
except ImportError:
    from tests.test_shell import StubPrefetcher


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


def _write_pack(directory, pack_id, version, level="TOPIK_I", difficulty=None, title=None):
    data = json.loads(SAMPLE_PACK.read_text(encoding="utf-8"))
    data["pack_id"] = pack_id
    data["pack_version"] = version
    data["topik_level"] = level
    data["title"] = title or pack_id
    if difficulty is not None:
        data["difficulty"] = difficulty
    path = Path(directory) / f"{pack_id}-{version}.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


class PackMetadataTests(unittest.TestCase):
    def test_difficulty_must_be_a_string_when_present(self):
        data = json.loads(SAMPLE_PACK.read_text(encoding="utf-8"))
        data["difficulty"] = "authentic"
        self.assertEqual(validate_pack_data(data), [])
        data["difficulty"] = 3
        errors = validate_pack_data(data)
        self.assertTrue(any("difficulty" in error for error in errors))

    def test_import_records_difficulty_in_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            library = Path(temp_dir) / "library"
            pack = _write_pack(temp_dir, "labeled", "0.1.0", difficulty="starter")
            entry = import_pack(pack, library)
            self.assertEqual(entry["difficulty"], "starter")
            plain = _write_pack(temp_dir, "plain", "0.1.0")
            entry = import_pack(plain, library)
            self.assertNotIn("difficulty", entry)


class PackVisibilityTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        self.library = self.temp_dir / "library"
        import_pack(_write_pack(self.temp_dir, "pack-a", "0.1.0"), self.library)
        import_pack(_write_pack(self.temp_dir, "pack-a", "0.2.0"), self.library)
        import_pack(_write_pack(self.temp_dir, "pack-b", "0.1.0", level="TOPIK_II"), self.library)

    def tearDown(self):
        self._temp.cleanup()

    def test_latest_packs_dedupes_versions(self):
        latest = latest_packs(self.library)
        self.assertEqual(
            [(entry["pack_id"], entry["pack_version"]) for entry in latest],
            [("pack-a", "0.2.0"), ("pack-b", "0.1.0")],
        )

    def test_hidden_packs_leave_listings_but_stay_loadable(self):
        changed = set_pack_hidden("pack-a", True, self.library)
        self.assertEqual(changed, 2)
        self.assertEqual([entry["pack_id"] for entry in list_packs(self.library)], ["pack-b"])
        self.assertEqual(len(list_packs(self.library, include_hidden=True)), 3)
        self.assertEqual([entry["pack_id"] for entry in latest_packs(self.library)], ["pack-b"])
        # Pinned and bare refs still resolve so old attempts keep working.
        self.assertEqual(load_pack_ref("pack-a@0.1.0", self.library).pack_id, "pack-a")
        self.assertEqual(load_pack_ref("pack-a", self.library).pack_id, "pack-a")

        set_pack_hidden("pack-a", False, self.library)
        self.assertEqual(len(list_packs(self.library)), 3)

        with self.assertRaisesRegex(ValueError, "not found"):
            set_pack_hidden("missing", True, self.library)

    def test_hide_and_show_pack_cli(self):
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["hide-pack", "pack-a", "--library", str(self.library)])
        self.assertEqual(exit_code, 0)
        self.assertIn("Hidden 2 version(s)", output.getvalue())

        output = StringIO()
        with redirect_stdout(output):
            main(["list-packs", "--library", str(self.library)])
        text = output.getvalue()
        self.assertNotIn("pack-a", text)
        self.assertIn("hidden pack version(s)", text)

        output = StringIO()
        with redirect_stdout(output):
            main(["list-packs", "--library", str(self.library), "--all"])
        text = output.getvalue()
        self.assertIn("pack-a", text)
        self.assertIn("[hidden]", text)

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["show-pack", "pack-a", "--library", str(self.library)])
        self.assertEqual(exit_code, 0)

    def test_list_packs_groups_by_level(self):
        output = StringIO()
        with redirect_stdout(output):
            main(["list-packs", "--library", str(self.library)])
        text = output.getvalue()
        self.assertIn("TOPIK_I:", text)
        self.assertIn("TOPIK_II:", text)
        self.assertLess(text.index("TOPIK_I:"), text.index("pack-a@"))


class PackPickerTests(unittest.TestCase):
    def setUp(self):
        ansi.set_color_enabled(False)
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        self.library = self.temp_dir / "library"
        import_pack(
            _write_pack(self.temp_dir, "mock-easy", "0.1.0", difficulty="starter", title="Starter Pack"),
            self.library,
        )
        import_pack(
            _write_pack(self.temp_dir, "mock-real", "0.1.0", difficulty="authentic", title="Real Pack"),
            self.library,
        )
        import_pack(
            _write_pack(self.temp_dir, "mock-two", "0.1.0", level="TOPIK_II", title="Level Two Pack"),
            self.library,
        )

    def tearDown(self):
        ansi.set_color_enabled(None)
        self._temp.cleanup()

    def make_shell(self):
        output = []
        shell = Shell(
            library_dir=self.library,
            attempt_dir=self.temp_dir / "attempts",
            tts_config=TTSConfig(output_dir=self.temp_dir / "audio"),
            output=output.append,
            prefetcher=StubPrefetcher(),
        )
        return shell, output

    def test_picker_groups_levels_and_shows_difficulty_and_progress(self):
        shell, output = self.make_shell()
        shell.handle_line("/take")
        text = "\n".join(output)
        self.assertEqual(shell.state, PICK_PACK)
        self.assertIn("TOPIK I", text)
        self.assertIn("TOPIK II", text)
        self.assertIn("starter", text)
        self.assertIn("authentic", text)
        self.assertIn("untaken", text)
        self.assertLess(text.index("TOPIK I"), text.index("TOPIK II"))

    def test_picker_text_input_filters(self):
        shell, output = self.make_shell()
        shell.handle_line("/take")
        output.clear()
        shell.handle_line("authentic")
        text = "\n".join(output)
        self.assertEqual(shell.state, PICK_PACK)
        self.assertIn("filter: authentic", text)
        self.assertIn("Real Pack", text)
        self.assertNotIn("Starter Pack", text)

        output.clear()
        shell.handle_line("1")  # only Real Pack is listed
        self.assertIn("Real Pack", "\n".join(output))

    def test_picker_level_filter_and_no_match_fallback(self):
        shell, output = self.make_shell()
        shell.handle_line("/take")
        output.clear()
        shell.handle_line("ii")
        text = "\n".join(output)
        self.assertIn("Level Two Pack", text)
        self.assertNotIn("Real Pack", text)

        output.clear()
        shell.handle_line("zzz")
        text = "\n".join(output)
        self.assertIn("No pack matches 'zzz'", text)
        self.assertIn("Real Pack", text)  # falls back to everything

    def test_packs_command_filters_and_shows_progress(self):
        shell, output = self.make_shell()
        # Complete one run of mock-easy so it shows progress.
        shell.handle_line("/take mock-easy")
        shell.handle_line("B")
        shell.handle_line("")
        shell.handle_line("A")
        shell.handle_line("")
        output.clear()
        shell.handle_line("/packs")
        text = "\n".join(output)
        self.assertIn("best 2/2 · 1 attempt(s)", text)
        self.assertIn("untaken", text)

        output.clear()
        shell.handle_line("/packs starter")
        text = "\n".join(output)
        self.assertIn("Starter Pack", text)
        self.assertNotIn("Level Two Pack", text)


if __name__ == "__main__":
    unittest.main()
