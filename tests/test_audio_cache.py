import os
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from topik_sim.audio_cache import (
    cache_stats,
    pack_speech_texts,
    prune_cache,
    warm_pack,
)
from topik_sim.cli import main
from topik_sim.content import load_pack
from topik_sim.prefetch import AudioPrefetcher
from topik_sim.tts import TTSConfig, stable_audio_name


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PACK = ROOT / "examples" / "content" / "topik_i_mini_pack.json"


def _write_wav(directory: Path, name: str, size: int, age_seconds: float = 0.0) -> Path:
    path = directory / name
    path.write_bytes(b"0" * size)
    if age_seconds:
        stamp = time.time() - age_seconds
        os.utime(path, (stamp, stamp))
    return path


class AudioCacheTests(unittest.TestCase):
    def test_cache_stats_counts_wav_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            _write_wav(directory, "a.wav", 100)
            _write_wav(directory, "b.wav", 200)
            (directory / "ignored.txt").write_text("x")
            stats = cache_stats(directory)
            self.assertEqual(stats.file_count, 2)
            self.assertEqual(stats.total_bytes, 300)

    def test_prune_requires_a_constraint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "prune"):
                prune_cache(temp_dir)

    def test_prune_removes_least_recently_used_until_under_budget(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            old = _write_wav(directory, "old.wav", 600, age_seconds=3600)
            new = _write_wav(directory, "new.wav", 600, age_seconds=60)
            result = prune_cache(directory, max_bytes=1000)
            self.assertEqual(result.removed, [old])
            self.assertEqual(result.bytes_removed, 600)
            self.assertFalse(old.exists())
            self.assertTrue(new.exists())

    def test_prune_by_age_and_dry_run_keeps_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            stale = _write_wav(directory, "stale.wav", 100, age_seconds=10 * 86400)
            fresh = _write_wav(directory, "fresh.wav", 100, age_seconds=3600)
            result = prune_cache(directory, older_than_days=7, dry_run=True)
            self.assertEqual(result.removed, [stale])
            self.assertTrue(stale.exists())
            self.assertTrue(fresh.exists())

    def test_cache_hit_refreshes_mtime_for_lru(self):
        from topik_sim.tts import synthesize_many

        with tempfile.TemporaryDirectory() as temp_dir:
            config = TTSConfig(output_dir=Path(temp_dir), provider="melo")
            cached = Path(temp_dir) / stable_audio_name("안녕", provider="melo", language="KR")
            cached.write_bytes(b"fake")
            stamp = time.time() - 3600
            os.utime(cached, (stamp, stamp))
            with patch("topik_sim.tts.build_provider") as build_provider:
                synthesize_many(["안녕"], config)
            build_provider.assert_not_called()
            self.assertGreater(cached.stat().st_mtime, stamp + 1800)

    def test_pack_speech_texts_listening_only_by_default(self):
        pack = load_pack(SAMPLE_PACK)
        # The mini pack has no listening questions, so the default is empty.
        self.assertEqual(pack_speech_texts(pack), [])
        texts = pack_speech_texts(pack, include_all_questions=True)
        self.assertTrue(any("날씨" in text for text in texts))
        teaching = pack_speech_texts(pack, include_all_questions=True, include_teaching=True)
        self.assertGreater(len(teaching), len(texts))

    def test_warm_pack_reports_generated_and_cached(self):
        pack = load_pack(SAMPLE_PACK)
        with tempfile.TemporaryDirectory() as temp_dir:
            config = TTSConfig(output_dir=Path(temp_dir), provider="melo")

            def fake_synthesize(texts, cfg):
                self.assertFalse(cfg.playback)
                paths = []
                for text in texts:
                    path = cfg.output_dir / stable_audio_name(text, provider=cfg.provider, language=cfg.language)
                    path.write_bytes(b"fake")
                    paths.append(path)
                return paths

            with patch("topik_sim.audio_cache.synthesize_many", side_effect=fake_synthesize):
                generated, cached = warm_pack(pack, config, include_all_questions=True)
                self.assertGreater(generated, 0)
                self.assertEqual(cached, 0)
                generated_again, cached_again = warm_pack(pack, config, include_all_questions=True)
                self.assertEqual(generated_again, 0)
                self.assertEqual(cached_again, generated)

    def test_audio_stats_and_prune_cli(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            _write_wav(directory, "a.wav", 2048, age_seconds=3600)

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["audio", "stats", "--audio-dir", str(directory)])
            self.assertEqual(exit_code, 0)
            self.assertIn("Files: 1", output.getvalue())

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["audio", "prune", "--audio-dir", str(directory), "--max-mb", "0"])
            self.assertEqual(exit_code, 0)
            self.assertIn("Removed 1 file(s)", output.getvalue())
            self.assertEqual(list(directory.glob("*.wav")), [])

    def test_prefetcher_synthesizes_in_background_and_disables_on_error(self):
        calls = []

        def fake_synthesize(texts, config):
            calls.append(texts)
            if texts == ["boom"]:
                raise RuntimeError("no tts")
            return []

        with patch("topik_sim.prefetch.synthesize_many", side_effect=fake_synthesize):
            prefetcher = AudioPrefetcher()
            try:
                prefetcher.schedule(["안녕"], TTSConfig(playback=True))
                prefetcher.wait()
                self.assertEqual(calls, [["안녕"]])

                prefetcher.schedule(["boom"], TTSConfig())
                prefetcher.wait()
                prefetcher.schedule(["after failure"], TTSConfig())
                prefetcher.wait()
                self.assertEqual(calls, [["안녕"], ["boom"]])
            finally:
                prefetcher.close()


if __name__ == "__main__":
    unittest.main()
