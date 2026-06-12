# topik.ps1 - TOPIK simulator launcher (Windows PowerShell 5.1 compatible).
#
# Starts the simulator from any current directory: the script anchors to its
# own folder, points PYTHONPATH at the bundled sources, and forwards every
# argument to the application unchanged. Examples:
#
#   .\topik.ps1              interactive shell (press Enter for the menu)
#   .\topik.ps1 doctor       environment self-check with remedies
#   .\topik.ps1 stats        any other subcommand works the same way
#
# Double-click or cmd.exe users: run topik.cmd instead; it wraps this script.

$ErrorActionPreference = 'Continue'

# --- Anchor to the workspace root (the folder containing this script). -----
$workspaceRoot = $PSScriptRoot
if (-not $workspaceRoot) {
    $workspaceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

# --- Find a usable Python. --------------------------------------------------
# "python" on PATH is preferred. Machines without Python ship a Microsoft
# Store stub also named python.exe that only prints an install nag and fails,
# so every candidate is probed with a real interpreter call instead of
# trusting Get-Command. "py -3" (the python.org launcher) is the fallback for
# installs that skipped the "Add python.exe to PATH" checkbox.
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
    Write-Host ''
    Write-Host 'Python was not found on this computer.'
    Write-Host ''
    Write-Host 'The TOPIK simulator needs Python 3.9 or newer. Two easy ways to install it:'
    Write-Host '  1. Download it from https://www.python.org/downloads/'
    Write-Host '     (during setup, tick "Add python.exe to PATH")'
    Write-Host '  2. Or open the Microsoft Store and install the latest "Python 3".'
    Write-Host ''
    Write-Host 'Then run this launcher again.'
    exit 1
}

# --- Run the simulator from the workspace root. -----------------------------
# The working directory matters: data/, content/library, and
# topik.config.json are all resolved relative to the workspace root.
$savedPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $workspaceRoot 'src'
Push-Location $workspaceRoot
$exitCode = 1
try {
    & $pythonExe @pythonBaseArgs -m topik_sim @args
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
    $env:PYTHONPATH = $savedPythonPath
}
exit $exitCode
