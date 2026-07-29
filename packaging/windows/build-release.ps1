[CmdletBinding()]
param(
    [string]$Python = "D:\Python312\python.exe",
    [string]$Vst3SdkRoot = "D:\SammyBlazeDeps\vst3sdk",
    [ValidateSet("Debug", "Release", "RelWithDebInfo", "MinSizeRel")]
    [string]$Configuration = "Release",
    [string]$NativeBuildDirectory = "D:\SammyBlazeBuild\native",
    [string]$CMakePath = "D:\VisualStudio\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe",
    [string]$NinjaPath = "D:\VisualStudio\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe",
    [string]$VcVarsPath = "D:\VisualStudio\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
    [string]$AudioCoreTarget = "SammyBlazeAudioCore",
    [string]$AudioCoreDllPath = "",
    [string]$Vst3Target = "SammyBlazeVST3",
    [string]$Vst3BundlePath = "",
    [string]$ModelPath = "models\hand_landmarker.task",
    [string]$StandaloneOutputRoot = "artifacts\windows",
    [string]$StageRoot = "artifacts\release\windows",
    [Parameter(Mandatory = $true)]
    [string]$ProductVersion,
    [switch]$SkipInstall,
    [switch]$ValidateNative,
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

function Invoke-ReleaseScript {
    param(
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][hashtable]$Arguments
    )

    & $ScriptPath @Arguments
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resolvedNativeBuildDirectory = Resolve-AbsolutePath `
    -Path $NativeBuildDirectory `
    -BasePath $repoRoot
if ([string]::IsNullOrWhiteSpace($AudioCoreDllPath)) {
    $resolvedAudioCoreDllPath = Join-Path `
        $resolvedNativeBuildDirectory `
        "bin\$Configuration\SammyBlazeAudioCore.dll"
}
else {
    $resolvedAudioCoreDllPath = Resolve-AbsolutePath `
        -Path $AudioCoreDllPath `
        -BasePath $resolvedNativeBuildDirectory
}
if ([string]::IsNullOrWhiteSpace($Vst3BundlePath)) {
    $resolvedVst3BundlePath = Join-Path `
        $resolvedNativeBuildDirectory `
        "VST3\$Configuration\SammyBlaze.vst3"
}
else {
    $resolvedVst3BundlePath = Resolve-AbsolutePath `
        -Path $Vst3BundlePath `
        -BasePath $resolvedNativeBuildDirectory
}
$resolvedStandaloneOutputRoot = Resolve-AbsolutePath `
    -Path $StandaloneOutputRoot `
    -BasePath $repoRoot
$resolvedStandaloneBundle = Join-Path $resolvedStandaloneOutputRoot "SammyBlaze"

$nativeArguments = @{
    Vst3SdkRoot = $Vst3SdkRoot
    Configuration = $Configuration
    BuildDirectory = $resolvedNativeBuildDirectory
    CMakePath = $CMakePath
    NinjaPath = $NinjaPath
    VcVarsPath = $VcVarsPath
    AudioCoreTarget = $AudioCoreTarget
    AudioCoreDllPath = $resolvedAudioCoreDllPath
    Vst3Target = $Vst3Target
    Vst3BundlePath = $resolvedVst3BundlePath
    Validate = $ValidateNative
    DryRun = $DryRun
}
$standaloneArguments = @{
    Python = $Python
    OutputRoot = $StandaloneOutputRoot
    ModelPath = $ModelPath
    AudioCoreDllPath = $resolvedAudioCoreDllPath
    SkipInstall = $SkipInstall
    DryRun = $false
}
$stageArguments = @{
    StandaloneBundlePath = $resolvedStandaloneBundle
    Vst3BundlePath = $resolvedVst3BundlePath
    StageRoot = $StageRoot
    ProductVersion = $ProductVersion
    DryRun = $false
}

if ($DryRun) {
    Write-Host "DRY RUN: Phase 9.2 release pipeline"
    Invoke-ReleaseScript `
        -ScriptPath (Join-Path $PSScriptRoot "build-native.ps1") `
        -Arguments $nativeArguments
    Write-Host "DRY RUN: after native build, package the standalone with:"
    Write-Host "  DLL:        $resolvedAudioCoreDllPath"
    Write-Host "  model:      $(Resolve-AbsolutePath -Path $ModelPath -BasePath $repoRoot)"
    Write-Host "  output:     $resolvedStandaloneBundle"
    Write-Host "DRY RUN: then stage the standalone and separate VST3 at:"
    Write-Host "  VST3:       $resolvedVst3BundlePath"
    Write-Host "  stage root: $(Resolve-AbsolutePath -Path $StageRoot -BasePath $repoRoot)"
    return
}

Invoke-ReleaseScript `
    -ScriptPath (Join-Path $PSScriptRoot "build-native.ps1") `
    -Arguments $nativeArguments
Invoke-ReleaseScript `
    -ScriptPath (Join-Path $PSScriptRoot "build.ps1") `
    -Arguments $standaloneArguments
Invoke-ReleaseScript `
    -ScriptPath (Join-Path $PSScriptRoot "stage-release.ps1") `
    -Arguments $stageArguments

Write-Host "Phase 9.2 build and staging pipeline completed successfully."
