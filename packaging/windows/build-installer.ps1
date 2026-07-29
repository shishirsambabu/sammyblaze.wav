[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$StageRoot,
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^\d+\.\d+\.\d+([-.][0-9A-Za-z.-]+)?$")]
    [string]$ProductVersion,
    [ValidatePattern("^\d+\.\d+\.\d+\.\d+$")]
    [string]$InstallerFileVersion = "0.4.0.0",
    [string]$OutputRoot = "artifacts\release\windows\installer",
    [string]$Python = "D:\Python312\python.exe",
    [string]$IsccPath = "D:\SammyBlazeTools\InnoSetup6\ISCC.exe",
    [string]$InstallerSourceRevision = "",
    [string]$SignToolCommand = "",
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

function Assert-SafeOutputRoot {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd("\", "/")
    $driveRoot = [System.IO.Path]::GetPathRoot($fullPath).TrimEnd("\", "/")
    if ($fullPath -eq $driveRoot) {
        throw "OutputRoot cannot be a drive root: $Path"
    }
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resolvedStageRoot = Resolve-AbsolutePath -Path $StageRoot -BasePath $repoRoot
$resolvedOutputRoot = Resolve-AbsolutePath -Path $OutputRoot -BasePath $repoRoot
$resolvedPython = Resolve-AbsolutePath -Path $Python -BasePath $repoRoot
$resolvedIsccPath = Resolve-AbsolutePath -Path $IsccPath -BasePath $repoRoot
$installerSource = Join-Path $PSScriptRoot "installer\SammyBlaze.iss"
$stageVerifier = Join-Path $PSScriptRoot "verify_release_stage.py"
Assert-SafeOutputRoot -Path $resolvedOutputRoot

foreach ($requiredFile in @(
    $resolvedPython,
    $resolvedIsccPath,
    $installerSource,
    $stageVerifier
)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required installer build input is missing: $requiredFile"
    }
}
if (-not (Test-Path -LiteralPath $resolvedStageRoot -PathType Container)) {
    throw "Release stage is missing: $resolvedStageRoot"
}

$verificationOutput = @(
    & $resolvedPython $stageVerifier `
        --stage $resolvedStageRoot `
        --expected-version $ProductVersion
)
if ($LASTEXITCODE -ne 0) {
    throw "Release stage verification failed: $($verificationOutput -join [Environment]::NewLine)"
}
$verification = ($verificationOutput -join [Environment]::NewLine) | ConvertFrom-Json
if (-not $verification.passed) {
    throw "Release stage verification did not report a pass."
}
if ([string]::IsNullOrWhiteSpace($InstallerSourceRevision)) {
    $InstallerSourceRevision = (& git -C $repoRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to resolve the installer-source Git revision."
    }
}
if ($InstallerSourceRevision -notmatch "^[0-9a-fA-F]{40}$") {
    throw "InstallerSourceRevision must be a 40-character Git SHA."
}
$InstallerSourceRevision = $InstallerSourceRevision.ToLowerInvariant()

$installerFileName = "SammyBlaze-Setup-$ProductVersion-windows-x64.exe"
$installerPath = Join-Path $resolvedOutputRoot $installerFileName
$manifestPath = Join-Path $resolvedOutputRoot "installer-manifest.json"
$checksumsPath = Join-Path $resolvedOutputRoot "SHA256SUMS.txt"
$isccArguments = @(
    "/DStageRoot=$resolvedStageRoot",
    "/DProductVersion=$ProductVersion",
    "/DInstallerFileVersion=$InstallerFileVersion",
    "/DOutputRoot=$resolvedOutputRoot"
)
if (-not [string]::IsNullOrWhiteSpace($SignToolCommand)) {
    $isccArguments += "/DSignInstaller=1"
    $isccArguments += "/Ssammyblaze=$SignToolCommand"
}
$isccArguments += $installerSource

if ($DryRun) {
    Write-Host "DRY RUN: release stage verification passed."
    Write-Host "  Stage:           $resolvedStageRoot"
    Write-Host "  Product version: $ProductVersion"
    Write-Host "  Payload revision:   $($verification.sourceRevision)"
    Write-Host "  Installer revision: $InstallerSourceRevision"
    Write-Host "  Manifest files:  $($verification.manifestFiles)"
    Write-Host "  Checksums:       $($verification.verifiedChecksums)"
    Write-Host "  Compiler:        $resolvedIsccPath"
    Write-Host "  Installer:       $installerPath"
    Write-Host "  Signing:         $(-not [string]::IsNullOrWhiteSpace($SignToolCommand))"
    return
}

New-Item -ItemType Directory -Force -Path $resolvedOutputRoot | Out-Null
foreach ($generatedFile in @($installerPath, $manifestPath, $checksumsPath)) {
    if (Test-Path -LiteralPath $generatedFile -PathType Leaf) {
        Remove-Item -LiteralPath $generatedFile -Force
    }
}

& $resolvedIsccPath @isccArguments
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
}
if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf)) {
    throw "Installer compilation completed without the expected executable: $installerPath"
}

$signature = Get-AuthenticodeSignature -LiteralPath $installerPath
$isSigned = $signature.Status -eq [System.Management.Automation.SignatureStatus]::Valid
if (-not [string]::IsNullOrWhiteSpace($SignToolCommand) -and -not $isSigned) {
    throw "A signing command was supplied, but the installer signature is not valid."
}

$stageManifestPath = Join-Path $resolvedStageRoot "manifest.json"
$stageChecksumsPath = Join-Path $resolvedStageRoot "SHA256SUMS.txt"
$installerHash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
$compilerVersion = (Get-Item -LiteralPath $resolvedIsccPath).VersionInfo.FileVersion
$installerManifest = [ordered]@{
    schema = "sammyblaze.windows-installer"
    schemaVersion = 1
    product = "SammyBlaze"
    version = $ProductVersion
    fileVersion = $InstallerFileVersion
    platform = "windows-x86_64"
    payloadSourceRevision = $verification.sourceRevision
    installerSourceRevision = $InstallerSourceRevision
    installer = [ordered]@{
        file = $installerFileName
        bytes = (Get-Item -LiteralPath $installerPath).Length
        sha256 = $installerHash
        authenticodeStatus = [string]$signature.Status
        signed = $isSigned
    }
    compiler = [ordered]@{
        product = "Inno Setup"
        version = $compilerVersion
    }
    input = [ordered]@{
        stageManifestSha256 = (
            Get-FileHash -LiteralPath $stageManifestPath -Algorithm SHA256
        ).Hash.ToLowerInvariant()
        stageChecksumsSha256 = (
            Get-FileHash -LiteralPath $stageChecksumsPath -Algorithm SHA256
        ).Hash.ToLowerInvariant()
        manifestFiles = [int]$verification.manifestFiles
        verifiedChecksums = [int]$verification.verifiedChecksums
    }
    acceptance = [ordered]@{
        stageVerified = $true
        installUninstallTested = $false
        cleanMachineTested = $false
        dawHostTested = $false
    }
}
$manifestJson = ($installerManifest | ConvertTo-Json -Depth 8) + "`n"
Write-Utf8NoBom -Path $manifestPath -Content $manifestJson
Write-Utf8NoBom `
    -Path $checksumsPath `
    -Content "$installerHash *$installerFileName`n"

Write-Host "Windows installer build complete: $installerPath"
Write-Host "Installer manifest: $manifestPath"
Write-Host "Installer checksum: $checksumsPath"
Write-Host "Authenticode status: $($signature.Status)"
