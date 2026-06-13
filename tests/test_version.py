import contextlib
import io
import unittest

import topik_sim
from topik_sim.cli import main


class VersionTests(unittest.TestCase):
    def test_package_version_is_set(self):
        self.assertEqual(topik_sim.__version__, "1.1.0")

    def test_version_flag_prints_and_exits_zero(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), self.assertRaises(SystemExit) as ctx:
            main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(buffer.getvalue().strip(), f"topik-sim {topik_sim.__version__}")


if __name__ == "__main__":
    unittest.main()
