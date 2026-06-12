# Local Korean TTS Setup

The simulator speaks listening questions, vocabulary, and example sentences through a local text-to-speech engine. TTS is optional: without it, exams stay fully usable and transcripts are shown in place of audio.

## Standard setup (recommended)

```powershell
.\setup-tts.ps1
```

That is the whole setup. The script creates a private environment at `.venv-tts`, installs the default `supertonic` engine from `requirements-tts.txt` (with `onnxruntime-directml`, which runs on any DirectX 12 GPU on Windows — CUDA is not required), and the simulator finds `.venv-tts` automatically. The Korean voice model downloads once, the first time audio plays (internet needed for that one download).

Verify with:

```powershell
.\topik.cmd doctor          # the "TTS runtime" line should be PASS
.\topik.cmd                 # then type: /say 안녕하세요
```

CPU-only machines: pass `--tts-onnx-provider cpu` (or set `"onnx_provider": "cpu"` under `tts` in `topik.config.json`).

## How the runtime is found

The Supertonic provider runs in a separate Python environment, located in this order:

1. `--tts-python <python.exe>` on any command.
2. The `TOPIK_SUPERTONIC_PYTHON` environment variable — point this at an existing Supertonic environment if you already have one from another project.
3. The workspace `.venv-tts` created by `setup-tts.ps1`.
4. The Python running the simulator itself (works if you installed `requirements-tts.txt` straight into it).

## Alternative providers

- `melo` (MeloTTS, CUDA): `pip install git+https://github.com/myshell-ai/MeloTTS.git` plus a CUDA PyTorch build from [pytorch.org](https://pytorch.org/get-started/) into the environment of your choice; use `--tts-provider melo --tts-device cuda:0`. Use a standard python.org CPython — MSYS/MINGW builds do not receive Windows PyTorch wheels.
- `xtts-v2` (Coqui, voice cloning): see the section at the end; requires a reference speaker WAV.

## CLI Usage

From a source checkout, use `python -m topik_sim.tts_cli` for standalone speech commands. After package installation, the same interface is available as `topik-tts`. The standalone `speak` command plays directly by default and cleans up its temporary WAV; add `--save` to keep the generated file in `data/audio_cache`.

Generate audio for direct text:

```powershell
$env:PYTHONPATH = "src"
python -m topik_sim.tts_cli speak "안녕하세요. 오늘은 날씨가 좋습니다." --tts-provider supertonic
```

Override the runtime explicitly when needed:

```powershell
$env:PYTHONPATH = "src"
python -m topik_sim.tts_cli speak "안녕하세요." --tts-provider supertonic --tts-python .\.venv-tts\Scripts\python.exe
```

Speak question passages while taking a test:

```powershell
python -m topik_sim take examples/content/topik_i_mini_pack.json --speak-question --tts-play
```

Speak vocabulary and grammar examples in teaching notes:

```powershell
python -m topik_sim take examples/content/topik_i_mini_pack.json --speak-question --speak-teaching --tts-play
```

Listening questions in `take` mode automatically play audio, hide transcript text before answering, and reveal the transcript after answering. Use this for the full sample exam:

```powershell
python -m topik_sim take topik-i-level-1-full-sample@0.1.0
```

At the answer prompt, enter `/replay`, `/r`, or `replay` to hear the current question audio again. After answering, the app pauses on the transcript and explanation; press Enter for the next question or enter `/replay` again to hear the just-answered question audio.

Show transcript text only when debugging content:

```powershell
python -m topik_sim take topik-i-level-1-full-sample@0.1.0 --show-transcript --no-listening-audio
```

Adjust generated WAV volume:

```powershell
python -m topik_sim take topik-i-level-1-full-sample@0.1.0 --tts-volume 0.8
python -m topik_sim.tts_cli speak "안녕하세요." --tts-volume 1.2
```

Volume is applied at playback time, so changing it never regenerates or duplicates cached audio (see `docs/AUDIO_DESIGN.md`).

List built-in provider speakers:

```powershell
python -m topik_sim.tts_cli list-speakers --tts-provider supertonic
```

Choose a printed speaker name or numeric ID:

```powershell
python -m topik_sim.tts_cli speak "안녕하세요." --tts-speaker-id F1
```

For Supertonic, `--tts-speaker-id` selects a voice preset such as `F1`, `F2`, or `M1`:

```powershell
python -m topik_sim.tts_cli speak "안녕하세요." --tts-provider supertonic --tts-speaker-id F1
```

Use CPU fallback:

```powershell
python -m topik_sim.tts_cli speak "도서관에서 책을 읽습니다." --tts-provider supertonic --tts-onnx-provider cpu
```

## XTTS-v2 Alternate

Install Coqui TTS if you want XTTS-v2:

```powershell
python -m pip install TTS
```

Use a reference voice file:

```powershell
python -m topik_sim.tts_cli speak "안녕하세요." --tts-provider xtts-v2 --tts-speaker-wav path\to\reference.wav
```

Check the XTTS-v2 model license before distributing generated voices or bundled model files.
