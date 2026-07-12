import contextlib
import io
import re
import unittest
from pathlib import Path

import topik_sim
from topik_sim.cli import main

ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_package_version_is_set(self):
        self.assertEqual(topik_sim.__version__, "1.2.0")

    def test_version_matches_pyproject_and_changelog(self):
        # Release hygiene: the three version sources cannot drift apart.
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'version = "{topik_sim.__version__}"', pyproject)
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertRegex(changelog, rf"## \[{re.escape(topik_sim.__version__)}\] - \d{{4}}-\d{{2}}-\d{{2}}")

    def test_version_flag_prints_and_exits_zero(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), self.assertRaises(SystemExit) as ctx:
            main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(buffer.getvalue().strip(), f"topik-sim {topik_sim.__version__}")


if __name__ == "__main__":
    unittest.main()
