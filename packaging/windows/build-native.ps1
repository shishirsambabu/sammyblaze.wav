[CmdletBinding()]
param(
    [string]$Vst3SdkRoot = "D:\SammyBlazeDeps\vst3sdk",
    [ValidateSet("Debug", "Release", "RelWithDebInfo", "MinSizeRel")]
    [string]$Configuration = "Release",
    [string]$BuildDirectory = "D:\SammyBlazeBuild\native",
    [string]$CMakePath = "D:\VisualStudio\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe",
    [string]$NinjaPath = "D:\VisualStudio\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe",
    [string]$VcVarsPath = "D:\VisualStudio\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
    [string]$AudioCoreTarget = "SammyBlazeAudioCore",
    [string]$AudioCoreDllPath = "",
    [string]$Vst3Target = "SammyBlazeVST3",
    [string]$Vst3BundlePath = "",
    [switch]$Validate,
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

function Resolve-ToolPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Description
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        $candidate = [System.IO.Path]::GetFullPath($Path)
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw "$Description was not found: $candidate"
        }
        return $candidate
    }

    $resolved = Get-Command $Path -CommandType Application -ErrorAction SilentlyContinue
    if ($null -eq $resolved) {
        throw "$Description was not found on PATH: $Path"
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

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage,
        [switch]$PlanOnly
    )

    if ($PlanOnly) {
        Write-Host ("DRY RUN: " + (Format-Command -Executable $Executable -Arguments $Arguments))
        return
    }

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage Exit code: $LASTEXITCODE."
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resolvedBuildDirectory = Resolve-AbsolutePath -Path $BuildDirectory -BasePath $repoRoot
$resolvedVst3SdkRoot = Resolve-AbsolutePath -Path $Vst3SdkRoot -BasePath $repoRoot

if ([string]::IsNullOrWhiteSpace($AudioCoreDllPath)) {
    $resolvedAudioCoreDllPath = Join-Path $resolvedBuildDirectory "bin\$Configuration\SammyBlazeAudioCore.dll"
}
else {
    $resolvedAudioCoreDllPath = Resolve-AbsolutePath `
        -Path $AudioCoreDllPath `
        -BasePath $resolvedBuildDirectory
}
if ([string]::IsNullOrWhiteSpace($Vst3BundlePath)) {
    $resolvedVst3BundlePath = Join-Path $resolvedBuildDirectory "VST3\$Configuration\SammyBlaze.vst3"
}
else {
    $resolvedVst3BundlePath = Resolve-AbsolutePath `
        -Path $Vst3BundlePath `
        -BasePath $resolvedBuildDirectory
}
$vst3Binary = Join-Path $resolvedVst3BundlePath "Contents\x86_64-win\SammyBlaze.vst3"

if ($DryRun) {
    $resolvedCMake = Resolve-AbsolutePath -Path $CMakePath -BasePath $repoRoot
    $resolvedNinja = Resolve-AbsolutePath -Path $NinjaPath -BasePath $repoRoot
    $resolvedVcVars = Resolve-AbsolutePath -Path $VcVarsPath -BasePath $repoRoot
}
else {
    $resolvedCMake = Resolve-ToolPath -Path $CMakePath -Description "CMake"
    $resolvedNinja = Resolve-ToolPath -Path $NinjaPath -Description "Ninja"
    $resolvedVcVars = Resolve-ToolPath -Path $VcVarsPath -Description "Visual Studio x64 environment"
    if (-not (Test-Path -LiteralPath (Join-Path $resolvedVst3SdkRoot "CMakeLists.txt") -PathType Leaf)) {
        throw "VST3 SDK was not found: $resolvedVst3SdkRoot"
    }
}

$configureArguments = @(
    "--fresh",
    "-S", $repoRoot,
    "-B", $resolvedBuildDirectory,
    "-G", "Ninja Multi-Config",
    "-DCMAKE_CONFIGURATION_TYPES=$Configuration",
    "-DCMAKE_MAKE_PROGRAM=$resolvedNinja",
    "-DVST3_SDK_ROOT=$resolvedVst3SdkRoot"
)
$audioCoreBuildArguments = @(
    "--build", $resolvedBuildDirectory,
    "--config", $Configuration,
    "--target", $AudioCoreTarget
)
$vst3BuildArguments = @(
    "--build", $resolvedBuildDirectory,
    "--config", $Configuration,
    "--target", $Vst3Target
)

if ($DryRun) {
    Write-Host "DRY RUN: native target and artifact contract"
    Write-Host "  Audio core target: $AudioCoreTarget"
    Write-Host "  Audio core DLL:    $resolvedAudioCoreDllPath"
    Write-Host "  VST3 target:       $Vst3Target"
    Write-Host "  VST3 bundle:       $resolvedVst3BundlePath"
    Write-Host "DRY RUN: initialize compiler environment with $resolvedVcVars"
}
else {
    $developerEnvironment = & cmd.exe /d /s /c "`"$resolvedVcVars`" >nul && set"
    if ($LASTEXITCODE -ne 0) {
        throw "Visual Studio x64 compiler environment failed to initialize."
    }
    foreach ($line in $developerEnvironment) {
        if ($line -match "^([^=]+)=(.*)$") {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
    $env:PATH = "$(Split-Path -Parent $resolvedNinja);$env:PATH"
}

Invoke-NativeCommand `
    -Executable $resolvedCMake `
    -Arguments $configureArguments `
    -FailureMessage "Native CMake configure failed." `
    -PlanOnly:$DryRun
Invoke-NativeCommand `
    -Executable $resolvedCMake `
    -Arguments $audioCoreBuildArguments `
    -FailureMessage "Native audio core target '$AudioCoreTarget' failed to build." `
    -PlanOnly:$DryRun
Invoke-NativeCommand `
    -Executable $resolvedCMake `
    -Arguments $vst3BuildArguments `
    -FailureMessage "Native VST3 target '$Vst3Target' failed to build." `
    -PlanOnly:$DryRun

if ($DryRun) {
    if ($Validate) {
        Write-Host "DRY RUN: build and execute shared-core, C ABI, DSP, benchmark, and Steinberg validation."
    }
    return
}

if (-not (Test-Path -LiteralPath $resolvedAudioCoreDllPath -PathType Leaf)) {
    throw "Native audio core target completed but DLL is missing: $resolvedAudioCoreDllPath"
}
if (-not (Test-Path -LiteralPath $resolvedVst3BundlePath -PathType Container)) {
    throw "Native VST3 target completed but bundle is missing: $resolvedVst3BundlePath"
}
if (-not (Test-Path -LiteralPath $vst3Binary -PathType Leaf)) {
    throw "Native VST3 bundle is incomplete; binary is missing: $vst3Binary"
}

if ($Validate) {
    Invoke-NativeCommand `
        -Executable $resolvedCMake `
        -Arguments @(
            "--build", $resolvedBuildDirectory,
            "--config", $Configuration,
            "--target",
            "SammyBlazeAudioCoreValidation",
            "SammyBlazeAudioCoreAbiValidation"
        ) `
        -FailureMessage "Shared audio-core validation build failed."

    $audioCoreValidationDirectory = Join-Path `
        $resolvedBuildDirectory `
        "native\audio_core\$Configuration"
    $audioCoreValidator = Join-Path `
        $audioCoreValidationDirectory `
        "SammyBlazeAudioCoreValidation.exe"
    $audioCoreAbiValidator = Join-Path `
        $audioCoreValidationDirectory `
        "SammyBlazeAudioCoreAbiValidation.exe"
    $env:PATH = "$(Split-Path -Parent $resolvedAudioCoreDllPath);$env:PATH"
    foreach ($validationExecutable in @(
        $audioCoreValidator,
        $audioCoreAbiValidator
    )) {
        if (-not (Test-Path -LiteralPath $validationExecutable -PathType Leaf)) {
            throw "Shared audio-core validator is missing: $validationExecutable"
        }
        & $validationExecutable
        if ($LASTEXITCODE -ne 0) {
            throw "Shared audio-core validation failed with exit code $LASTEXITCODE."
        }
    }

    $abiRuntimeValidation = Join-Path `
        $repoRoot `
        "native\audio_core\tests\run_abi_validation.ps1"
    if (-not (Test-Path -LiteralPath $abiRuntimeValidation -PathType Leaf)) {
        throw "C ABI runtime validation script is missing: $abiRuntimeValidation"
    }
    & powershell.exe `
        -NoProfile `
        -ExecutionPolicy Bypass `
        -File $abiRuntimeValidation `
        -DllPath $resolvedAudioCoreDllPath
    if ($LASTEXITCODE -ne 0) {
        throw "C ABI runtime validation failed with exit code $LASTEXITCODE."
    }

    Invoke-NativeCommand `
        -Executable $resolvedCMake `
        -Arguments @(
            "--build", $resolvedBuildDirectory,
            "--config", $Configuration,
            "--target", "validator"
        ) `
        -FailureMessage "Steinberg validator build failed."

    $validator = Join-Path $resolvedBuildDirectory "bin\$Configuration\validator.exe"
    if (-not (Test-Path -LiteralPath $validator -PathType Leaf)) {
        throw "Steinberg validator executable is missing: $validator"
    }
    & $validator -selftest
    if ($LASTEXITCODE -ne 0) {
        throw "Steinberg validator self-test failed with exit code $LASTEXITCODE."
    }
    & $validator $resolvedVst3BundlePath
    if ($LASTEXITCODE -ne 0) {
        throw "SammyBlaze VST3 validation failed with exit code $LASTEXITCODE."
    }
}

Get-Item -LiteralPath $resolvedAudioCoreDllPath, $resolvedVst3BundlePath, $vst3Binary |
    Select-Object FullName, Length, LastWriteTime
