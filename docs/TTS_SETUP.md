# Local Korean TTS Setup

The simulator supports optional local GPU text-to-speech for Korean vocabulary and sentences during CLI usage.

## Default Provider

Default provider: `melo`

Why:

- MeloTTS supports Korean and provides a simple Python API with `language='KR'` and `device='cuda:0'`.
- It has a built-in Korean speaker, so the simulator can pronounce vocabulary and sentences without a reference voice file.
- It can also run on CPU if GPU setup is unavailable, although GPU is preferred here.

Alternate provider: `xtts-v2`

Use XTTS-v2 when voice cloning or cross-language voice transfer is needed. XTTS-v2 supports Korean, but it requires a reference speaker WAV file.

## GPU Check

This machine already exposes an NVIDIA GPU through `nvidia-smi`. The app defaults to:

```powershell
--tts-device cuda:0
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
python -m topik_sim speak "안녕하세요. 오늘은 날씨가 좋습니다." --tts-play
```

With the project-local full CPython runtime:

```powershell
$env:PYTHONPATH = "src"
.\tools\runtime\python311-full\tools\python.exe -m topik_sim speak "안녕하세요. 오늘은 날씨가 좋습니다." --tts-play
```

Speak question passages while taking a test:

```powershell
.\tools\runtime\python311-full\tools\python.exe -m topik_sim take examples/content/topik_i_mini_pack.json --speak-question --tts-play
```

Speak vocabulary and grammar examples in teaching notes:

```powershell
.\tools\runtime\python311-full\tools\python.exe -m topik_sim take examples/content/topik_i_mini_pack.json --speak-question --speak-teaching --tts-play
```

Listening questions in `take` mode automatically play audio and hide transcript text. Use this for the full sample exam:

```powershell
.\tools\runtime\python311-full\tools\python.exe -m topik_sim take topik-i-level-1-full-sample@0.1.0
```

At the answer prompt, enter `/replay`, `/r`, or `replay` to hear the current question audio again.

Show transcript text only when debugging content:

```powershell
.\tools\runtime\python311-full\tools\python.exe -m topik_sim take topik-i-level-1-full-sample@0.1.0 --show-transcript --no-listening-audio
```

Adjust generated WAV volume:

```powershell
.\tools\runtime\python311-full\tools\python.exe -m topik_sim take topik-i-level-1-full-sample@0.1.0 --tts-volume 0.8
.\tools\runtime\python311-full\tools\python.exe -m topik_sim speak "안녕하세요." --tts-volume 1.2 --tts-play
```

Volume is part of the audio cache key, so different volume settings create separate cached WAV files.

List built-in provider speakers:

```powershell
.\tools\runtime\python311-full\tools\python.exe -m topik_sim list-tts-speakers --tts-provider melo --tts-language KR
```

Choose a printed speaker name or numeric ID:

```powershell
.\tools\runtime\python311-full\tools\python.exe -m topik_sim speak "안녕하세요." --tts-speaker-id KR --tts-play
```

Use CPU fallback:

```powershell
python -m topik_sim speak "도서관에서 책을 읽습니다." --tts-device cpu
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
