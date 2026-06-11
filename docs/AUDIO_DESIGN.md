# Audio Design

Generated speech is the most expensive artifact the simulator produces. This document defines how audio is stored, reused, and generated so listening tests feel instant without unbounded disk growth.

## Goals

1. Never synthesize the same sentence twice.
2. Never make the learner wait for synthesis during a test when it can be avoided.
3. Keep the cache bounded and inspectable.
4. Keep cached waveforms canonical so playback settings never multiply storage.

## Content-Addressed Cache

Every synthesized WAV lives in one flat cache directory (default `data/audio_cache`). The filename is derived from the inputs that change the waveform:

```
<provider>-<language>-<sha256(provider|language|speed|volume=1.000|speaker|steps|text)[:24]>.wav
```

Key properties:

- **Volume is not part of the identity.** Gain is applied at playback time to a temporary copy (`play_audio(path, volume)`), so one cached waveform serves every `--tts-volume` setting. The literal `volume=1.000` token is kept in the hash input so files cached before this design keep their names.
- **Speed, speaker, and steps are part of the identity** because they change the synthesized waveform itself.
- The raw text never appears in the filename, so arbitrary sentences are safe on every filesystem.

## Cache Lifecycle

- **Hit tracking:** every cache hit refreshes the file's mtime, so mtime order is least-recently-used order.
- **Atomic writes:** synthesis writes to a temp file and `os.replace`s it into place. A background prefetch and a foreground request can race on the same sentence without corrupting the cache; the worst case is one redundant synthesis.
- **Inspection:** `topik-sim audio stats` reports file count, total size, and the least-recently-used timestamp.
- **Eviction:** `topik-sim audio prune --max-mb <n>` evicts LRU files until the cache fits the budget; `--older-than-days <n>` drops audio unused for that long; `--dry-run` previews. Pruning is always safe — evicted audio regenerates on demand.

## Real-Time Strategy

Two complementary mechanisms keep playback instant:

1. **Warming (ahead of the session):** `topik-sim audio warm <pack_ref>` pre-generates all listening audio for a pack (add `--all-questions` and `--teaching` for full coverage). Run it once after importing a pack; the test session then runs entirely from cache, even offline.
2. **Prefetching (during the session):** the interactive shell schedules the *next* question's audio on a single background thread while the learner answers the current question (`topik_sim.prefetch.AudioPrefetcher`). Prefetch failures disable further prefetching silently; the foreground path still synthesizes on demand and surfaces the real error.

## Future Options

- **Compression:** transcode cached WAVs to Opus/OGG (~10x smaller) when `ffmpeg` is available, keeping WAV as the universal fallback for `Media.SoundPlayer`.
- **Pack audio bundles:** export a pack's warmed audio as a single archive for sharing or offline devices.
- **Sample-rate normalization:** downmix to 16-bit mono at a fixed rate to cut size further when providers emit higher fidelity than speech needs.
