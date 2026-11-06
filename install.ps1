# =============================================================================
# swap-fase installer  —  Windows (PowerShell)
# -----------------------------------------------------------------------------
# Creates an ISOLATED project-local .venv, installs the cross-platform base deps
# + exactly onnxruntime-directml (DmlExecutionProvider runs on Windows GPUs with
# a built-in CPU fallback). Model downloads happen in the app with visible status.
#
# Usage:
#   Double-click "Start Swap-Fase.bat" for guided setup and launch.
#   .\install.ps1                # prepare dependencies, then fetch models
#   .\install.ps1 -NoModels      # defer model downloads to the app
#
# If you get "running scripts is disabled on this system", allow this session:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# then re-run .\install.ps1
#
# Safe to re-run (idempotent): reuses an existing .venv and upgrades in place.
# =============================================================================

[CmdletBinding()]
param(
    [switch]$NoModels
)

$ErrorActionPreference = 'Stop'

function Write-Banner($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Info($msg)   { Write-Host "    $msg" }
function Write-Warn($msg)   { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Invoke-PipUninstall($Packages) {
    $previousPreference = $ErrorActionPreference
    try {
        # Older Windows PowerShell promotes native stderr to a terminating
        # NativeCommandError when Stop is active, even for pip's harmless
        # "Skipping package not installed" warnings.
        $ErrorActionPreference = 'Continue'
        & $VPy -m pip uninstall -y $Packages 2>&1 | ForEach-Object {
            Write-Info "$_"
        }
        $pipExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($pipExitCode -ne 0) {
        throw "pip uninstall failed with exit code $pipExitCode"
    }
}

# Resolve the project root (this script's directory) and key paths.
$Here = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Venv = Join-Path $Here '.venv'
$VPy  = Join-Path $Venv 'Scripts\python.exe'

Write-Banner 'swap-fase installer (Windows)'

# ----- find a Python 3.12 launcher -----
# Prefer the py launcher (`py -3.12`); fall back to a `python` that reports 3.12.
$PyCmd = $null
$PyArgs = @()

if (Get-Command py -ErrorAction SilentlyContinue) {
    try {
        & py -3.12 -c "import sys; assert sys.version_info[:2]==(3,12)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $PyCmd = 'py'
            $PyArgs = @('-3.12')
        }
    } catch { }
}

if (-not $PyCmd -and (Get-Command python -ErrorAction SilentlyContinue)) {
    try {
        & python -c "import sys; assert sys.version_info[:2]==(3,12)" 2>$null
        if ($LASTEXITCODE -eq 0) { $PyCmd = 'python' }
    } catch { }
}

if (-not $PyCmd) {
    Write-Warn 'Python 3.12 was not found.'
    Write-Info 'Install Python 3.12 from https://www.python.org/downloads/ (check'
    Write-Info '"Add python.exe to PATH"), or via: winget install Python.Python.3.12'
    Write-Info 'Then re-run .\install.ps1'
    exit 1
}
$verShown = & $PyCmd @PyArgs --version 2>&1
Write-Info "Python interpreter: $PyCmd $($PyArgs -join ' ') ($verShown)"

# ----- create the isolated project-local venv -----
Write-Banner 'Creating isolated project-local venv at .venv'
if (Test-Path $VPy) {
    Write-Info 'Reusing existing .venv (idempotent).'
} else {
    & $PyCmd @PyArgs -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the .venv' }
}

# ----- upgrade pip, install base deps -----
Write-Banner 'Upgrading pip in the venv'
& $VPy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed' }

Write-Banner 'Installing cross-platform base dependencies'
& $VPy -m pip install -r (Join-Path $Here 'requirements\base.txt')
if ($LASTEXITCODE -ne 0) { throw 'base dependency install failed' }

# ----- ONNX Runtime for Windows = DirectML -----
# insightface can install the CPU runtime. Remove every provider distribution
# first, including stale variants from a previous install, before adding DirectML.
Write-Banner 'Installing ONNX Runtime (DirectML) for Windows'
Invoke-PipUninstall @('onnxruntime', 'onnxruntime-gpu', 'onnxruntime-directml', 'onnxruntime-silicon', 'onnxruntime-rocm')
& $VPy -m pip install onnxruntime-directml
if ($LASTEXITCODE -ne 0) { throw 'onnxruntime-directml install failed' }
$runtimeCheck = @'
from importlib.metadata import distributions
names = {d.metadata.get("Name", "").lower().replace("_", "-") for d in distributions()}
choices = {"onnxruntime", "onnxruntime-gpu", "onnxruntime-directml", "onnxruntime-silicon", "onnxruntime-rocm"}
installed = names & choices
expected = {__import__("sys").argv[1]}
assert installed == expected, f"Expected only {expected}, found: {sorted(installed)}"
'@
$runtimeCheck | & $VPy -c "import sys; exec(sys.stdin.read())" 'onnxruntime-directml'
if ($LASTEXITCODE -ne 0) { throw 'ONNX Runtime packages conflict; expected only onnxruntime-directml' }
Write-Info 'Verified exactly one ONNX Runtime: onnxruntime-directml (DirectML with CPU fallback).'

# ----- model fetch is deferred to the app for visible progress -----
if ($NoModels) {
    Write-Banner 'Model downloads will start in the app'
} else {
    Write-Banner 'Fetching model weights (one-time, ~880 MB: buffalo_l + inswapper_128)'
    Write-Info 'Downloads into project-local models\ (gitignored); offline thereafter.'
    & $VPy -c "import sys; sys.path.insert(0, 'src'); from swapfase.bootstrap import ensure_models; print('inswapper:', ensure_models())"
    if ($LASTEXITCODE -ne 0) { throw 'model fetch failed' }
}

$marker = Join-Path $Venv 'swapfase-install.complete'
Set-Content -Path $marker -Value '1' -NoNewline

# ----- virtual camera note (Windows) -----
Write-Banner 'Virtual camera (for Zoom / Meet / Discord)'
Write-Info 'On Windows the --vcam output uses the "OBS Virtual Camera" backend.'
Write-Info 'You MUST install OBS Studio (https://obsproject.com) once — it'
Write-Info 'registers the OBS Virtual Camera that pyvirtualcam writes to.'
Write-Info '(Alternatively install Unity Capture.) No need to keep OBS open.'

# ----- next steps -----
Write-Banner 'Done. Next steps:'
Write-Info 'Run the app:'
Write-Info '    .\.venv\Scripts\python run.py'
Write-Info 'Choose the target photo in the app window.'
Write-Info ''
Write-Info 'Output to the virtual camera for video calls:'
Write-Info '    .\.venv\Scripts\python run.py --target path\to\face.jpg --vcam'
Write-Info '  Then pick "OBS Virtual Camera" as your webcam in Zoom/Meet/Discord.'
Write-Host "`nInstall complete." -ForegroundColor Green
