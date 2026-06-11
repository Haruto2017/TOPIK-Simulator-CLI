from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace

from .tts import TTSConfig, synthesize_many


class AudioPrefetcher:
    """Synthesizes upcoming audio on one background thread.

    The interactive flow schedules the next question's audio while the
    learner answers the current one, so playback is a cache hit by the time
    it is needed. Failures disable further prefetching; the foreground path
    still synthesizes on demand and reports the real error.
    """

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts-prefetch")
        self._disabled = False
        self._pending: Future | None = None

    def schedule(self, texts: list[str], config: TTSConfig) -> None:
        if self._disabled or not texts:
            return
        prefetch_config = replace(config, playback=False)
        self._pending = self._executor.submit(self._synthesize, texts, prefetch_config)

    def wait(self, timeout: float | None = None) -> None:
        """Block until the last scheduled prefetch finishes. Used by tests and shutdown."""
        if self._pending is not None:
            try:
                self._pending.result(timeout=timeout)
            except Exception:
                pass

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _synthesize(self, texts: list[str], config: TTSConfig) -> None:
        try:
            synthesize_many(texts, config)
        except Exception:
            self._disabled = True
