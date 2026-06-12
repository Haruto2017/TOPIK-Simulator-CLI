import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from topik_sim.cli import main
from topik_sim.library import import_pack, list_packs
from topik_sim.tts import TTSConfig
from topik_sim.ui import ansi
from topik_sim.ui.shell import run_shell
from topik_sim.workspace import bundled_pack_paths, format_setup_summary, setup_workspace


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


def write_pack(directory: Path, name: str, pack_id: str, version: str = "0.1.0") -> Path:
    data = json.loads(SAMPLE_PACK.read_text(encoding="utf-8"))
    data["pack_id"] = pack_id
    data["pack_version"] = version
    path = directory / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


class WorkspaceTestCase(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        self.library_dir = self.temp_dir / "library"
        self.source_dir = self.temp_dir / "source"
        self.source_dir.mkdir()

    def tearDown(self):
        self._temp.cleanup()


class BundledPackPathsTests(WorkspaceTestCase):
    def test_sorted_json_files_only(self):
        write_pack(self.source_dir, "b_pack.json", "pack-b")
        write_pack(self.source_dir, "a_pack.json", "pack-a")
        (self.source_dir / "notes.txt").write_text("not a pack", encoding="utf-8")
        paths = bundled_pack_paths(self.source_dir)
        self.assertEqual([path.name for path in paths], ["a_pack.json", "b_pack.json"])

    def test_missing_directory_is_empty(self):
        self.assertEqual(bundled_pack_paths(self.temp_dir / "nope"), [])


class SetupWorkspaceTests(WorkspaceTestCase):
    def test_imports_every_bundled_pack(self):
        write_pack(self.source_dir, "a_pack.json", "pack-a")
        write_pack(self.source_dir, "b_pack.json", "pack-b")
        result = setup_workspace(self.library_dir, source_dir=self.source_dir)
        self.assertEqual(result["imported"], ["pack-a@0.1.0", "pack-b@0.1.0"])
        self.assertEqual(result["skipped"], [])
        self.assertEqual(result["failed"], [])
        self.assertEqual(result["counts"], {"imported": 2, "skipped": 0, "failed": 0, "total": 2})
        self.assertEqual(len(list_packs(self.library_dir)), 2)

    def test_second_run_skips_without_clobbering(self):
        write_pack(self.source_dir, "a_pack.json", "pack-a")
        setup_workspace(self.library_dir, source_dir=self.source_dir)
        result = setup_workspace(self.library_dir, source_dir=self.source_dir)
        self.assertEqual(result["imported"], [])
        self.assertEqual(result["skipped"], ["pack-a@0.1.0"])
        self.assertEqual(len(list_packs(self.library_dir)), 1)

    def test_failures_are_collected_not_raised(self):
        write_pack(self.source_dir, "a_pack.json", "pack-a")
        (self.source_dir / "broken.json").write_text("{not json", encoding="utf-8")
        (self.source_dir / "invalid.json").write_text(
            json.dumps({"schema_version": "topik-sim.content.v1"}), encoding="utf-8"
        )
        result = setup_workspace(self.library_dir, source_dir=self.source_dir)
        self.assertEqual(result["imported"], ["pack-a@0.1.0"])
        self.assertEqual(result["counts"]["failed"], 2)
        failed_paths = [failure["path"] for failure in result["failed"]]
        self.assertTrue(any("broken.json" in path for path in failed_paths))
        self.assertTrue(any("invalid.json" in path for path in failed_paths))
        for failure in result["failed"]:
            self.assertTrue(failure["errors"])

    def test_summary_lines_cover_every_outcome(self):
        write_pack(self.source_dir, "a_pack.json", "pack-a")
        (self.source_dir / "broken.json").write_text("{not json", encoding="utf-8")
        setup_workspace(self.library_dir, source_dir=self.source_dir)
        result = setup_workspace(self.library_dir, source_dir=self.source_dir)
        text = "\n".join(format_setup_summary(result))
        self.assertIn("Skipped pack-a@0.1.0 (already imported)", text)
        self.assertIn("Failed", text)
        self.assertIn("broken.json", text)
        self.assertIn("Setup: 0 imported, 1 skipped, 1 failed", text)

    def test_summary_for_empty_source_dir(self):
        result = setup_workspace(self.library_dir, source_dir=self.source_dir)
        lines = format_setup_summary(result)
        self.assertEqual(len(lines), 1)
        self.assertIn("No bundled packs found under", lines[0])


class SetupCommandTests(WorkspaceTestCase):
    def run_setup(self, source_dir=None):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main([
                "setup",
                "--library",
                str(self.library_dir),
                "--source-dir",
                str(source_dir if source_dir is not None else self.source_dir),
            ])
        return code, buffer.getvalue()

    def test_setup_imports_then_is_idempotent(self):
        write_pack(self.source_dir, "a_pack.json", "pack-a")
        code, out = self.run_setup()
        self.assertEqual(code, 0)
        self.assertIn("Imported pack-a@0.1.0", out)
        self.assertIn("1 imported, 0 skipped, 0 failed", out)

        code, out = self.run_setup()
        self.assertEqual(code, 0)
        self.assertIn("Skipped pack-a@0.1.0 (already imported)", out)
        self.assertEqual(len(list_packs(self.library_dir)), 1)

    def test_exit_code_1_only_when_every_pack_fails(self):
        (self.source_dir / "broken.json").write_text("{not json", encoding="utf-8")
        code, out = self.run_setup()
        self.assertEqual(code, 1)
        self.assertIn("Failed", out)

        write_pack(self.source_dir, "a_pack.json", "pack-a")
        code, out = self.run_setup()
        self.assertEqual(code, 0)  # one failure, one success
        self.assertIn("Imported pack-a@0.1.0", out)

    def test_empty_source_dir_exits_zero_with_pointer(self):
        code, out = self.run_setup()
        self.assertEqual(code, 0)
        self.assertIn("No bundled packs found under", out)


class FirstRunOnboardingTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        ansi.set_color_enabled(False)

    def tearDown(self):
        ansi.set_color_enabled(None)
        super().tearDown()

    def run_shell_scripted(self, lines):
        queue = list(lines)

        def input_fn(prompt):
            if not queue:
                raise EOFError
            return queue.pop(0)

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            run_shell(
                library_dir=self.library_dir,
                attempt_dir=self.temp_dir / "attempts",
                tts_config=TTSConfig(output_dir=self.temp_dir / "audio"),
                input_fn=input_fn,
                source_dir=self.source_dir,
            )
        return buffer.getvalue()

    def test_enter_imports_bundled_packs(self):
        write_pack(self.source_dir, "a_pack.json", "pack-a")
        write_pack(self.source_dir, "b_pack.json", "pack-b")
        out = self.run_shell_scripted([""])
        self.assertIn("No exams are imported yet. Import 2 bundled exam pack(s) now? [Y/n]", out)
        self.assertIn("Imported pack-a@0.1.0", out)
        self.assertIn("Imported pack-b@0.1.0", out)
        self.assertIn("Press Enter to open the menu.", out)
        self.assertEqual(len(list_packs(self.library_dir)), 2)

    def test_y_imports_too(self):
        write_pack(self.source_dir, "a_pack.json", "pack-a")
        out = self.run_shell_scripted(["y"])
        self.assertIn("Imported pack-a@0.1.0", out)
        self.assertEqual(len(list_packs(self.library_dir)), 1)

    def test_n_skips_and_points_at_setup(self):
        write_pack(self.source_dir, "a_pack.json", "pack-a")
        out = self.run_shell_scripted(["n"])
        self.assertIn("topik-sim setup", out)
        self.assertNotIn("Imported pack-a@0.1.0", out)
        self.assertEqual(list_packs(self.library_dir), [])

    def test_no_prompt_when_packs_already_imported(self):
        write_pack(self.source_dir, "a_pack.json", "pack-a")
        import_pack(write_pack(self.temp_dir, "existing.json", "pack-existing"), self.library_dir)
        out = self.run_shell_scripted([])
        self.assertNotIn("No exams are imported yet", out)

    def test_no_prompt_without_bundled_sources(self):
        out = self.run_shell_scripted([])
        self.assertNotIn("No exams are imported yet", out)


if __name__ == "__main__":
    unittest.main()
