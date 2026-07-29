[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$OutputRoot = "artifacts\windows",
    [string]$ModelPath = "models\hand_landmarker.task",
    [string]$AudioCoreDllPath = "D:\SammyBlazeBuild\native\bin\Release\SammyBlazeAudioCore.dll",
    [long]$BaselineBundleBytes = 1047945803,
    [long]$MaximumBundleBytes = 450000000,
    [ValidateRange(1, 100000)]
    [int]$MaximumBundleFiles = 1500,
    [switch]$SmokeTest,
    [ValidateRange(1, 60)]
    [int]$SmokeSeconds = 10,
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
$hooksPath = Join-Path $PSScriptRoot "hooks"
$runtimeHooksPath = Join-Path $PSScriptRoot "runtime_hooks"
$mediaPipeRuntimeHook = Join-Path $runtimeHooksPath "pyi_rth_mediapipe_minimal.py"
$packageProbeRuntimeHook = Join-Path $runtimeHooksPath "pyi_rth_sammyblaze_package_probe.py"
$bundleVerifier = Join-Path $PSScriptRoot "verify_bundle.py"

# Validate release-critical inputs before installing dependencies or changing output folders.
if (-not (Test-Path -LiteralPath $resolvedModelPath -PathType Leaf)) {
    throw "MediaPipe model is missing: $resolvedModelPath"
}
if (-not (Test-Path -LiteralPath $resolvedAudioCoreDllPath -PathType Leaf)) {
    throw "Native audio core DLL is missing: $resolvedAudioCoreDllPath"
}
foreach ($requiredPackagingFile in @(
    $hooksPath,
    $mediaPipeRuntimeHook,
    $packageProbeRuntimeHook,
    $bundleVerifier
)) {
    if (-not (Test-Path -LiteralPath $requiredPackagingFile)) {
        throw "Packaging helper is missing: $requiredPackagingFile"
    }
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
    "--additional-hooks-dir", $hooksPath,
    "--runtime-hook", $mediaPipeRuntimeHook,
    "--runtime-hook", $packageProbeRuntimeHook,
    "--hidden-import", "mido.backends.rtmidi",
    "--exclude-module", "matplotlib",
    "--exclude-module", "mpl_toolkits",
    "--exclude-module", "scipy",
    "--exclude-module", "PIL",
    "--exclude-module", "IPython",
    "--exclude-module", "jupyter",
    "--exclude-module", "notebook",
    "--exclude-module", "pytest",
    "--exclude-module", "tensorflow",
    "--exclude-module", "torch",
    "--exclude-module", "jax",
    (Join-Path $repoRoot "src\handmusic\desktop_entry.py")
)

if ($DryRun) {
    Write-Host "DRY RUN: standalone build inputs are valid."
    if (-not $SkipInstall) {
        Write-Host ("DRY RUN: " + (Format-Command -Executable $resolvedPython -Arguments $installArguments))
    }
    Write-Host ("DRY RUN: " + (Format-Command -Executable $resolvedPython -Arguments $pyInstallerArguments))
    Write-Host "DRY RUN: expected standalone bundle: $bundlePath"
    Write-Host "DRY RUN: post-build verifier: $bundleVerifier"
    if ($SmokeTest) {
        Write-Host "DRY RUN: offscreen package smoke duration: $SmokeSeconds seconds"
    }
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

$analysisTocPath = Join-Path $workPath "SammyBlaze\Analysis-00.toc"
$verifyArguments = @(
    $bundleVerifier,
    "--bundle", $bundlePath,
    "--analysis-toc", $analysisTocPath,
    "--baseline-bytes", $BaselineBundleBytes,
    "--max-bytes", $MaximumBundleBytes,
    "--max-files", $MaximumBundleFiles
)
& $resolvedPython @verifyArguments
if ($LASTEXITCODE -ne 0) {
    throw "Standalone bundle verification failed with exit code $LASTEXITCODE."
}

if ($SmokeTest) {
    $probeResultPath = Join-Path $distPath "package-smoke-result.json"
    if (Test-Path -LiteralPath $probeResultPath) {
        Remove-Item -LiteralPath $probeResultPath -Force
    }

    $priorQtPlatform = $env:QT_QPA_PLATFORM
    $priorProbePath = $env:SAMMYBLAZE_PACKAGE_PROBE
    $process = $null
    try {
        $env:QT_QPA_PLATFORM = "offscreen"
        $env:SAMMYBLAZE_PACKAGE_PROBE = $probeResultPath
        $process = Start-Process `
            -FilePath $executablePath `
            -PassThru `
            -WindowStyle Hidden
        Start-Sleep -Seconds $SmokeSeconds
        $process.Refresh()
        if ($process.HasExited) {
            throw "Packaged executable exited during the $SmokeSeconds-second smoke test with code $($process.ExitCode)."
        }
        if (-not (Test-Path -LiteralPath $probeResultPath -PathType Leaf)) {
            throw "Packaged runtime probe did not create its result: $probeResultPath"
        }
        $probeResult = Get-Content -LiteralPath $probeResultPath -Raw | ConvertFrom-Json
        if ($probeResult.status -ne "ok") {
            throw "Packaged runtime probe failed: $($probeResult.error)"
        }
        Write-Host "Offscreen package smoke: PASS ($SmokeSeconds seconds, PID $($process.Id))"
        Write-Host "Runtime probe: PySide6=$($probeResult.pyside6), OpenCV=$($probeResult.opencv), MediaPipe=$($probeResult.mediapipe), SoundDevice=$($probeResult.sounddevice), MIDI=$($probeResult.midi), NativeAudioABI=$($probeResult.nativeAudioAbi)"
    }
    finally {
        if ($null -ne $process) {
            $process.Refresh()
            if (-not $process.HasExited) {
                Stop-Process -Id $process.Id -Force
                $process.WaitForExit()
            }
            $process.Dispose()
        }
        $env:QT_QPA_PLATFORM = $priorQtPlatform
        $env:SAMMYBLAZE_PACKAGE_PROBE = $priorProbePath
    }
}

Write-Host "Windows standalone bundle: $bundlePath"
Write-Host "Bundled audio core: $bundledDll"
Write-Host "Bundled hand model: $bundledModel"
