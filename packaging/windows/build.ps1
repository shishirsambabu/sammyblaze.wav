[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$OutputRoot = "artifacts\windows",
    [string]$ModelPath = "models\hand_landmarker.task",
    [string]$AudioCoreDllPath = "D:\SammyBlazeBuild\native\bin\Release\SammyBlazeAudioCore.dll",
    [switch]$SkipInstall,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-AbsolutePath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$BasePath
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $BasePath $Path))
}

function Resolve-Executable {
    param([Parameter(Mandatory = $true)][string]$Command)

    if ([System.IO.Path]::IsPathRooted($Command)) {
        $candidate = [System.IO.Path]::GetFullPath($Command)
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw "Python executable was not found: $candidate"
        }
        return $candidate
    }

    $resolved = Get-Command $Command -CommandType Application -ErrorAction SilentlyContinue
    if ($null -eq $resolved) {
        throw "Python executable was not found on PATH: $Command"
    }
    return $resolved.Source
}

function Format-Command {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $quoted = foreach ($argument in $Arguments) {
        if ($argument -match '[\s"]') {
            '"' + $argument.Replace('"', '\"') + '"'
        }
        else {
            $argument
        }
    }
    return ('"{0}" {1}' -f $Executable, ($quoted -join " "))
}

function Assert-SingleBundledFile {
    param(
        [Parameter(Mandatory = $true)][string]$BundlePath,
        [Parameter(Mandatory = $true)][string]$FileName,
        [Parameter(Mandatory = $true)][string]$Description
    )

    $matches = @(Get-ChildItem -LiteralPath $BundlePath -Recurse -File |
        Where-Object { $_.Name -eq $FileName })
    if ($matches.Count -ne 1) {
        throw "Expected exactly one $Description named '$FileName' in $BundlePath; found $($matches.Count)."
    }
    return $matches[0].FullName
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resolvedPython = Resolve-Executable -Command $Python
$resolvedModelPath = Resolve-AbsolutePath -Path $ModelPath -BasePath $repoRoot
$resolvedAudioCoreDllPath = Resolve-AbsolutePath -Path $AudioCoreDllPath -BasePath $repoRoot
$distPath = Resolve-AbsolutePath -Path $OutputRoot -BasePath $repoRoot
$workPath = Join-Path $distPath "build"
$specPath = Join-Path $distPath "spec"
$bundlePath = Join-Path $distPath "SammyBlaze"

# Validate release-critical inputs before installing dependencies or changing output folders.
if (-not (Test-Path -LiteralPath $resolvedModelPath -PathType Leaf)) {
    throw "MediaPipe model is missing: $resolvedModelPath"
}
if (-not (Test-Path -LiteralPath $resolvedAudioCoreDllPath -PathType Leaf)) {
    throw "Native audio core DLL is missing: $resolvedAudioCoreDllPath"
}

$installArguments = @("-m", "pip", "install", "-e", ".[package,vision,midi-native,ui]")
$pyInstallerArguments = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", "SammyBlaze",
    "--contents-directory", "_internal",
    "--distpath", $distPath,
    "--workpath", $workPath,
    "--specpath", $specPath,
    "--paths", (Join-Path $repoRoot "src"),
    "--add-data", "$resolvedModelPath;models",
    "--add-binary", "$resolvedAudioCoreDllPath;.",
    "--collect-all", "PySide6",
    "--collect-all", "mediapipe",
    "--hidden-import", "mido.backends.rtmidi",
    (Join-Path $repoRoot "src\handmusic\desktop_entry.py")
)

if ($DryRun) {
    Write-Host "DRY RUN: standalone build inputs are valid."
    if (-not $SkipInstall) {
        Write-Host ("DRY RUN: " + (Format-Command -Executable $resolvedPython -Arguments $installArguments))
    }
    Write-Host ("DRY RUN: " + (Format-Command -Executable $resolvedPython -Arguments $pyInstallerArguments))
    Write-Host "DRY RUN: expected standalone bundle: $bundlePath"
    return
}

Set-Location $repoRoot
if (-not $SkipInstall) {
    & $resolvedPython @installArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Runtime dependency installation failed with exit code $LASTEXITCODE."
    }
}

New-Item -ItemType Directory -Force -Path $distPath | Out-Null
foreach ($cleanPath in @($bundlePath, $workPath, $specPath)) {
    if (Test-Path -LiteralPath $cleanPath) {
        Remove-Item -LiteralPath $cleanPath -Recurse -Force
    }
}
New-Item -ItemType Directory -Force -Path $workPath, $specPath | Out-Null

& $resolvedPython @pyInstallerArguments
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller bundle failed with exit code $LASTEXITCODE."
}

$executablePath = Join-Path $bundlePath "SammyBlaze.exe"
if (-not (Test-Path -LiteralPath $executablePath -PathType Leaf)) {
    throw "Standalone bundle is incomplete; executable is missing: $executablePath"
}
$bundledDll = Assert-SingleBundledFile `
    -BundlePath $bundlePath `
    -FileName "SammyBlazeAudioCore.dll" `
    -Description "native audio core DLL"
$bundledModel = Assert-SingleBundledFile `
    -BundlePath $bundlePath `
    -FileName "hand_landmarker.task" `
    -Description "MediaPipe model"

Write-Host "Windows standalone bundle: $bundlePath"
Write-Host "Bundled audio core: $bundledDll"
Write-Host "Bundled hand model: $bundledModel"
