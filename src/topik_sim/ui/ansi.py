from __future__ import annotations

import os
import sys


RESET = "0"
BOLD = "1"
DIM = "2"
RED = "31"
GREEN = "32"
YELLOW = "33"
BLUE = "34"
MAGENTA = "35"
CYAN = "36"
GREY = "90"

_color_enabled: bool | None = None


def supports_color() -> bool:
    global _color_enabled
    if _color_enabled is None:
        if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
            _color_enabled = False
        elif not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
            _color_enabled = False
        elif sys.platform.startswith("win"):
            _color_enabled = _enable_windows_vt()
        else:
            _color_enabled = True
    return _color_enabled


def set_color_enabled(enabled: bool | None) -> None:
    """Override color detection; tests and non-tty captures pass False."""
    global _color_enabled
    _color_enabled = enabled


def style(text: str, *codes: str) -> str:
    if not codes or not supports_color():
        return text
    return f"\x1b[{';'.join(codes)}m{text}\x1b[0m"


def _enable_windows_vt() -> bool:
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        return bool(kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING))
    except Exception:
        return False
