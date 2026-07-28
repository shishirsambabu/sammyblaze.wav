param(
    [string]$Python = "python",
    [string]$OutputRoot = "artifacts\windows",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$modelPath = Join-Path $repoRoot "models\hand_landmarker.task"
if (-not (Test-Path -LiteralPath $modelPath -PathType Leaf)) {
    throw "Missing $modelPath. Download the MediaPipe hand_landmarker.task model before packaging."
}

if (-not $SkipInstall) {
    & $Python -m pip install -e ".[package,vision,midi-native,ui]"
    if ($LASTEXITCODE -ne 0) { throw "Runtime dependency installation failed." }
}

$distPath = Join-Path $repoRoot $OutputRoot
$workPath = Join-Path $distPath "build"
$specPath = Join-Path $distPath "spec"
New-Item -ItemType Directory -Force -Path $distPath,$workPath,$specPath | Out-Null

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "SammyBlaze" `
    --distpath $distPath `
    --workpath $workPath `
    --specpath $specPath `
    --paths "src" `
    --add-data "$modelPath;models" `
    --collect-all PySide6 `
    --collect-all mediapipe `
    --hidden-import mido.backends.rtmidi `
    "src\handmusic\desktop_entry.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller bundle failed." }

Write-Host "Windows bundle written to $(Join-Path $distPath 'SammyBlaze')"
