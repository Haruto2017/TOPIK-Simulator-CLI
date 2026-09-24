#!/bin/sh
# Install the Qwen3-TTS speech engine for macOS (Apple Silicon) into .venv-qwen3.
#
# Qwen3-TTS runs through mlx-audio on the Apple GPU. The venv is separate from
# the simulator's own environment so its heavier dependencies never touch the
# stdlib-only core. Requires Python 3.11+ (older scipy wheels do not load on
# current macOS) — Homebrew's python3.12 is used when present.
set -eu
cd "$(dirname "$0")"
PY="${TOPIK_QWEN3_BASE_PYTHON:-}"
for candidate in "$PY" /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.13 /usr/local/bin/python3.12 python3.12 python3; do
  [ -n "$candidate" ] || continue
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then PY="$candidate"; break; fi
done
[ -n "$PY" ] || { echo "Need Python 3.11+ (brew install python@3.12)"; exit 1; }
echo "Using $($PY --version) at $PY"
"$PY" -m venv .venv-qwen3
.venv-qwen3/bin/pip install --quiet --upgrade pip
.venv-qwen3/bin/pip install --quiet mlx-audio
.venv-qwen3/bin/python tools/qwen3_synth.py --check && echo "Qwen3-TTS is ready: run with --tts-provider qwen3"
