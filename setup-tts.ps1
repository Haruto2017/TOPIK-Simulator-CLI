# setup-tts.ps1 - one-command Korean speech setup (Windows PowerShell 5.1 compatible).
#
# Creates a private Python environment at .venv-tts and installs the default
# Supertonic TTS engine into it. The simulator finds .venv-tts automatically;
# no configuration is needed afterwards. Safe to re-run.
#
# Without TTS the simulator still works: listening questions show their
# transcripts instead of playing audio.

$ErrorActionPreference = 'Continue'

$workspaceRoot = $PSScriptRoot
if (-not $workspaceRoot) {
    $workspaceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$venvPython = Join-Path $workspaceRoot '.venv-tts\Scripts\python.exe'

function Test-PythonCandidate {
    param(
        [string]$Exe,
        [string[]]$BaseArgs = @()
    )
    try {
        $null = & $Exe @BaseArgs -c "import sys" 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

$pythonExe = $null
$pythonBaseArgs = @()
if (Test-PythonCandidate -Exe 'python') {
    $pythonExe = 'python'
} elseif (Test-PythonCandidate -Exe 'py' -BaseArgs @('-3')) {
    $pythonExe = 'py'
    $pythonBaseArgs = @('-3')
}
if (-not $pythonExe) {
    Write-Host 'Python was not found. Install Python 3.9+ from https://www.python.org/downloads/ first.'
    exit 1
}

if (-not (Test-Path $venvPython)) {
    Write-Host 'Creating the TTS environment at .venv-tts ...'
    & $pythonExe @pythonBaseArgs -m venv (Join-Path $workspaceRoot '.venv-tts')
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
        Write-Host 'Could not create the virtual environment.'
        exit 1
    }
} else {
    Write-Host 'Reusing the existing .venv-tts environment.'
}

Write-Host 'Installing the Supertonic speech engine (a few minutes on first run) ...'
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r (Join-Path $workspaceRoot 'requirements-tts.txt')
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installation failed. Check your network connection and re-run .\setup-tts.ps1'
    exit 1
}

& $venvPython -c "import supertonic, onnxruntime" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'The engine did not import cleanly. Re-run .\setup-tts.ps1 or see docs/TTS_SETUP.md'
    exit 1
}

Write-Host ''
Write-Host 'Speech is ready. The voice model downloads automatically the first time'
Write-Host 'audio plays (one-time, needs internet). Try it:'
Write-Host ''
Write-Host '    .\topik.cmd            then type:  /say ' -NoNewline
Write-Host ([char]0xC548 + [char]0xB155 + [char]0xD558 + [char]0xC138 + [char]0xC694)
Write-Host ''
Write-Host 'Check the whole setup anytime with: .\topik.cmd doctor'
exit 0
