# Local Korean TTS Setup

The simulator supports optional local GPU text-to-speech for Korean vocabulary and sentences during CLI usage.

## Default Provider

Default provider: `supertonic`

Why:

- The Anki workspace at `H:\software\anki` already has a working Supertonic TTS environment and cached model files.
- Supertonic can run locally through DirectML on Windows with `--tts-onnx-provider dml`.
- The TOPIK CLI can call that environment automatically when `H:\software\anki\.tts-venv\Scripts\python.exe` exists.

MeloTTS remains available as an explicit CUDA provider:

- MeloTTS supports Korean and provides a simple Python API with `language='KR'` and `device='cuda:0'`.
- It has a built-in Korean speaker, so the simulator can pronounce vocabulary and sentences without a reference voice file.
- It can also run on CPU if GPU setup is unavailable, although GPU is preferred here.

Alternate provider: `xtts-v2`

Use XTTS-v2 when voice cloning or cross-language voice transfer is needed. XTTS-v2 supports Korean, but it requires a reference speaker WAV file.

## GPU Check

This machine already exposes an NVIDIA GPU through `nvidia-smi`. For MeloTTS CUDA, use:

```powershell
--tts-provider melo --tts-device cuda:0
```

## Recommended Install

Use a standard Windows CPython installation from python.org, the official NuGet CPython package, or a Conda environment. The MSYS/MINGW Python build does not receive the normal Windows PyTorch CUDA wheels, so GPU PyTorch installation can fail with "No matching distribution found for torch".

This workspace has been verified with a project-local full CPython runtime at:

```powershell
.\tools\runtime\python311-full\tools\python.exe
```

The `tools/runtime/` folder is ignored by Git because it contains the local Python runtime and large installed packages.

Create an isolated environment before installing model dependencies:

```powershell
py -3.9 -m venv .venv-tts
.\.venv-tts\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Install a CUDA-enabled PyTorch build using the current command from the official PyTorch selector:

[PyTorch Get Started](https://pytorch.org/get-started/)

Then install MeloTTS:

```powershell
python -m pip install -r requirements-tts.txt
python -m pip install eunjeon
```

The first synthesis run may download model weights.

## Verify

```powershell
$env:PYTHONPATH = "src"
.\tools\runtime\python311-full\tools\python.exe tools/check_tts_setup.py
.\tools\runtime\python311-full\tools\python.exe tools/check_tts_setup.py --synthesize
```

The synthesis check writes a WAV file under `data/audio_cache/`.

## CLI Usage

Generate audio for direct text:

```powershell
$env:PYTHONPATH = "src"
python -m topik_sim speak "안녕하세요. 오늘은 날씨가 좋습니다." --tts-provider supertonic --tts-play
```

The default Supertonic provider will try to use:

```powershell
H:\software\anki\.tts-venv\Scripts\python.exe
```

Override that runtime when needed:

```powershell
$env:PYTHONPATH = "src"
python -m topik_sim speak "안녕하세요." --tts-provider supertonic --tts-python H:\software\anki\.tts-venv\Scripts\python.exe --tts-play
```

With the project-local full CPython runtime and MeloTTS CUDA:

```powershell
$env:PYTHONPATH = "src"
.\tools\runtime\python311-full\tools\python.exe -m topik_sim speak "안녕하세요. 오늘은 날씨가 좋습니다." --tts-provider melo --tts-play
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
python -m topik_sim speak "안녕하세요." --tts-volume 1.2 --tts-play
```

Volume is part of the audio cache key, so different volume settings create separate cached WAV files.

List built-in provider speakers:

```powershell
python -m topik_sim list-tts-speakers --tts-provider supertonic
```

Choose a printed speaker name or numeric ID:

```powershell
python -m topik_sim speak "안녕하세요." --tts-speaker-id F1 --tts-play
```

For Supertonic, `--tts-speaker-id` selects a voice preset such as `F1`, `F2`, or `M1`:

```powershell
python -m topik_sim speak "안녕하세요." --tts-provider supertonic --tts-speaker-id F1 --tts-play
```

Use CPU fallback:

```powershell
python -m topik_sim speak "도서관에서 책을 읽습니다." --tts-provider supertonic --tts-onnx-provider cpu
```

## XTTS-v2 Alternate

Install Coqui TTS if you want XTTS-v2:

```powershell
python -m pip install TTS
```

Use a reference voice file:

```powershell
python -m topik_sim speak "안녕하세요." --tts-provider xtts-v2 --tts-speaker-wav path\to\reference.wav --tts-play
```

Check the XTTS-v2 model license before distributing generated voices or bundled model files.
