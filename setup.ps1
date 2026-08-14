#Requires -Version 5.1
<#
.SYNOPSIS
    Setup script for mak-attatch on Windows (GUI only).
.DESCRIPTION
    Checks for Python, ffmpeg, mkvtoolnix. Installs missing deps via winget.
    Creates a virtual environment and installs Python packages.
    Prints launch instructions.
.NOTES
    Run with: powershell -ExecutionPolicy Bypass -File setup.ps1
#>

$ErrorActionPreference = "Stop"

function Test-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Write-Info  { param([string]$Msg) Write-Host "[*] $Msg" -ForegroundColor Cyan }
function Write-Ok    { param([string]$Msg) Write-Host "[+] $Msg" -ForegroundColor Green }
function Write-Warn  { param([string]$Msg) Write-Host "[!] $Msg" -ForegroundColor Yellow }
function Write-Err   { param([string]$Msg) Write-Host "[-] $Msg" -ForegroundColor Red }

# --- Check OS ---
if (-not $IsWindows -and -not ($env:OS -match "Windows")) {
    Write-Err "This script is for Windows only. Use ./setup.sh on Linux/macOS."
    exit 1
}

# --- Check winget ---
$hasWinget = Test-Command "winget"
if (-not $hasWinget) {
    Write-Warn "winget not found. Manual install required for system deps."
}

# --- Check Python ---
$pythonCmd = $null
if (Test-Command "python") { $pythonCmd = "python" }
elseif (Test-Command "py") { $pythonCmd = "py" }
elseif (Test-Command "python3") { $pythonCmd = "python3" }

if (-not $pythonCmd) {
    Write-Err "Python not found in PATH."
    if ($hasWinget) {
        Write-Info "Install with: winget install Python.Python.3.11"
    } else {
        Write-Info "Download from https://python.org/downloads/"
    }
    exit 1
}

# Verify Python version >= 3.10
$pyVer = & $pythonCmd --version 2>&1
if ($pyVer -match "Python (\d+)\.(\d+)") {
    $maj = [int]$Matches[1]; $min = [int]$Matches[2]
    if ($maj -lt 3 -or ($maj -eq 3 -and $min -lt 10)) {
        Write-Err "Python 3.10+ required. Found: $pyVer"
        exit 1
    }
}
Write-Ok "Python: $pyVer"

# --- Check ffmpeg ---
if (-not (Test-Command "ffmpeg")) {
    Write-Warn "ffmpeg not found."
    if ($hasWinget) {
        Write-Info "Installing ffmpeg via winget..."
        winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
    } else {
        Write-Info "Install manually: https://ffmpeg.org/download.html#build-windows"
    }
} else {
    Write-Ok "ffmpeg found"
}

# --- Check mkvpropedit (mkvtoolnix) ---
if (-not (Test-Command "mkvpropedit")) {
    Write-Warn "mkvtoolnix (mkvpropedit) not found."
    if ($hasWinget) {
        Write-Info "Installing MKVToolNix via winget..."
        winget install --id MoritzBunkus.MKVToolNix -e --accept-package-agreements --accept-source-agreements
    } else {
        Write-Info "Install manually: https://mkvtoolnix.download/downloads.html#windows"
    }
} else {
    Write-Ok "mkvtoolnix found"
}

# --- Refresh PATH from registry after winget installs ---
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

# --- Re-verify tools after PATH refresh ---
if (-not (Test-Command "ffmpeg")) {
    Write-Warn "ffmpeg installed but not in current PATH."
    Write-Info "Close this terminal, open a new one, and re-run this script."
} else {
    Write-Ok "ffmpeg now on PATH"
}
if (-not (Test-Command "mkvpropedit")) {
    Write-Warn "mkvtoolnix installed but not in current PATH."
    Write-Info "Close this terminal, open a new one, and re-run this script."
} else {
    Write-Ok "mkvpropedit now on PATH"
}

# --- Create venv ---
if (Test-Path ".venv") {
    Write-Warn "Existing .venv found. Removing..."
    Remove-Item -Recurse -Force ".venv"
}

Write-Info "Creating virtual environment..."
& $pythonCmd -m venv .venv
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Err "Failed to create virtual environment."
    exit 1
}

# --- Install pip deps (GUI only) ---
$venvPython = ".\.venv\Scripts\python.exe"
Write-Info "Installing Python packages (GUI mode)..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install PyQt6 requests guessit

# --- Done ---
Write-Ok "Setup complete."
Write-Host ""
Write-Host "Launch the GUI:" -ForegroundColor Cyan
Write-Host "    $venvPython main.py" -ForegroundColor White
Write-Host ""
Write-Host "Or activate the venv first:" -ForegroundColor Cyan
Write-Host "    .venv\Scripts\activate" -ForegroundColor White
Write-Host "    python main.py" -ForegroundColor White
Write-Host ""
Write-Host "NOTE: Get a free TMDB API key at https://www.themoviedb.org/settings/api" -ForegroundColor Yellow
