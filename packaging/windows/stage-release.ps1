[CmdletBinding()]
param(
    [string]$StandaloneBundlePath = "artifacts\windows\SammyBlaze",
    [string]$Vst3BundlePath = "D:\SammyBlazeBuild\native\VST3\Release\SammyBlaze.vst3",
    [string]$StageRoot = "artifacts\release\windows",
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^\d+\.\d+\.\d+([-.][0-9A-Za-z.-]+)?$")]
    [string]$ProductVersion,
    [string]$SourceRevision = "",
    [string]$AudioCoreFileName = "SammyBlazeAudioCore.dll",
    [string]$ModelFileName = "hand_landmarker.task",
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

function Find-SingleFile {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$FileName,
        [Parameter(Mandatory = $true)][string]$Description
    )

    $matches = @(Get-ChildItem -LiteralPath $Root -Recurse -File |
        Where-Object { $_.Name -eq $FileName })
    if ($matches.Count -ne 1) {
        throw "Expected exactly one $Description named '$FileName' under $Root; found $($matches.Count)."
    }
    return $matches[0].FullName
}

function Get-RelativeReleasePath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $rootWithSeparator = $Root.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    $rootUri = New-Object System.Uri($rootWithSeparator)
    $pathUri = New-Object System.Uri($Path)
    return [System.Uri]::UnescapeDataString($rootUri.MakeRelativeUri($pathUri).ToString())
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Assert-SafeStageRoot {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd("\", "/")
    $root = [System.IO.Path]::GetPathRoot($fullPath).TrimEnd("\", "/")
    if ($fullPath -eq $root) {
        throw "StageRoot cannot be a drive root: $Path"
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resolvedStandaloneBundle = Resolve-AbsolutePath -Path $StandaloneBundlePath -BasePath $repoRoot
$resolvedVst3Bundle = Resolve-AbsolutePath -Path $Vst3BundlePath -BasePath $repoRoot
$resolvedStageRoot = Resolve-AbsolutePath -Path $StageRoot -BasePath $repoRoot
Assert-SafeStageRoot -Path $resolvedStageRoot

# Validate every required input before creating or replacing the staging directory.
if (-not (Test-Path -LiteralPath $resolvedStandaloneBundle -PathType Container)) {
    throw "Standalone bundle is missing: $resolvedStandaloneBundle"
}
$standaloneExecutable = Join-Path $resolvedStandaloneBundle "SammyBlaze.exe"
if (-not (Test-Path -LiteralPath $standaloneExecutable -PathType Leaf)) {
    throw "Standalone executable is missing: $standaloneExecutable"
}
$audioCoreDll = Find-SingleFile `
    -Root $resolvedStandaloneBundle `
    -FileName $AudioCoreFileName `
    -Description "native audio core DLL"
$handModel = Find-SingleFile `
    -Root $resolvedStandaloneBundle `
    -FileName $ModelFileName `
    -Description "MediaPipe model"
if (-not (Test-Path -LiteralPath $resolvedVst3Bundle -PathType Container)) {
    throw "VST3 bundle is missing: $resolvedVst3Bundle"
}
$vst3Binary = Join-Path $resolvedVst3Bundle "Contents\x86_64-win\SammyBlaze.vst3"
if (-not (Test-Path -LiteralPath $vst3Binary -PathType Leaf)) {
    throw "VST3 binary is missing: $vst3Binary"
}

if ([string]::IsNullOrWhiteSpace($SourceRevision)) {
    $SourceRevision = (& git -C $repoRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($SourceRevision)) {
        throw "Unable to resolve the source Git revision. Pass -SourceRevision explicitly."
    }
}

if ($DryRun) {
    Write-Host "DRY RUN: release staging inputs are valid."
    Write-Host "  Standalone:       $resolvedStandaloneBundle"
    Write-Host "  Audio core DLL:   $audioCoreDll"
    Write-Host "  Hand model:       $handModel"
    Write-Host "  VST3:             $resolvedVst3Bundle"
    Write-Host "  VST3 binary:      $vst3Binary"
    Write-Host "  Stage root:       $resolvedStageRoot"
    Write-Host "  Product version:  $ProductVersion"
    Write-Host "  Source revision:  $SourceRevision"
    return
}

$stageParent = Split-Path -Parent $resolvedStageRoot
$stageLeaf = Split-Path -Leaf $resolvedStageRoot
New-Item -ItemType Directory -Force -Path $stageParent | Out-Null
$temporaryStage = Join-Path $stageParent (".$stageLeaf.staging-$PID")

if (Test-Path -LiteralPath $temporaryStage) {
    Remove-Item -LiteralPath $temporaryStage -Recurse -Force
}

try {
    $standaloneDestination = Join-Path $temporaryStage "standalone\SammyBlaze"
    $vst3DestinationRoot = Join-Path $temporaryStage "VST3"
    New-Item -ItemType Directory -Force -Path $standaloneDestination, $vst3DestinationRoot |
        Out-Null

    Get-ChildItem -LiteralPath $resolvedStandaloneBundle -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName `
            -Destination $standaloneDestination `
            -Recurse `
            -Force
    }
    Copy-Item -LiteralPath $resolvedVst3Bundle `
        -Destination $vst3DestinationRoot `
        -Recurse `
        -Force

    $payloadFiles = @(Get-ChildItem -LiteralPath $temporaryStage -Recurse -File |
        Sort-Object FullName)
    $manifestFiles = @(
        foreach ($file in $payloadFiles) {
            [ordered]@{
                path = Get-RelativeReleasePath -Root $temporaryStage -Path $file.FullName
                size = $file.Length
                sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
    )
    $manifest = [ordered]@{
        schemaVersion = 1
        product = "SammyBlaze"
        version = $ProductVersion
        platform = "windows-x86_64"
        configuration = "Release"
        sourceRevision = $SourceRevision
        artifacts = [ordered]@{
            standalone = "standalone/SammyBlaze/SammyBlaze.exe"
            audioCore = "standalone/SammyBlaze/_internal/SammyBlazeAudioCore.dll"
            handModel = "standalone/SammyBlaze/_internal/models/hand_landmarker.task"
            vst3 = "VST3/SammyBlaze.vst3"
        }
        files = $manifestFiles
    }
    $manifestJson = ($manifest | ConvertTo-Json -Depth 8) + "`n"
    $manifestPath = Join-Path $temporaryStage "manifest.json"
    Write-Utf8NoBom -Path $manifestPath -Content $manifestJson

    $checksumLines = @(
        Get-ChildItem -LiteralPath $temporaryStage -Recurse -File |
            Where-Object { $_.Name -ne "SHA256SUMS.txt" } |
            Sort-Object FullName |
            ForEach-Object {
                $relativePath = Get-RelativeReleasePath -Root $temporaryStage -Path $_.FullName
                $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
                "$hash *$relativePath"
            }
    )
    $checksumsPath = Join-Path $temporaryStage "SHA256SUMS.txt"
    Write-Utf8NoBom -Path $checksumsPath -Content (($checksumLines -join "`n") + "`n")

    if (Test-Path -LiteralPath $resolvedStageRoot) {
        Remove-Item -LiteralPath $resolvedStageRoot -Recurse -Force
    }
    Move-Item -LiteralPath $temporaryStage -Destination $resolvedStageRoot
}
catch {
    if (Test-Path -LiteralPath $temporaryStage) {
        Remove-Item -LiteralPath $temporaryStage -Recurse -Force
    }
    throw
}

Write-Host "Release staging complete: $resolvedStageRoot"
Write-Host "Standalone artifact: $(Join-Path $resolvedStageRoot 'standalone\SammyBlaze')"
Write-Host "Separately installable VST3: $(Join-Path $resolvedStageRoot 'VST3\SammyBlaze.vst3')"
Write-Host "Manifest: $(Join-Path $resolvedStageRoot 'manifest.json')"
Write-Host "Checksums: $(Join-Path $resolvedStageRoot 'SHA256SUMS.txt')"
