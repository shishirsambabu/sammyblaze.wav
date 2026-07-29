[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [string]$QaRoot = "D:\SammyBlazeInstallerQA",
    [string]$EvidenceRoot = "D:\SammyBlazeValidation\phase-9.5",
    [ValidateRange(30, 600)]
    [int]$ProcessTimeoutSeconds = 180,
    [switch]$AllowMachineMutation
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-AbsolutePath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not [System.IO.Path]::IsPathRooted($Path)) {
        throw "Acceptance paths must be absolute: $Path"
    }
    return [System.IO.Path]::GetFullPath($Path)
}

function Assert-SafeQaRoot {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = Resolve-AbsolutePath -Path $Path
    $trimmed = $fullPath.TrimEnd("\", "/")
    $driveRoot = [System.IO.Path]::GetPathRoot($trimmed).TrimEnd("\", "/")
    $forbidden = @(
        $driveRoot,
        [Environment]::GetFolderPath("ProgramFiles").TrimEnd("\", "/"),
        [Environment]::GetFolderPath("CommonProgramFiles").TrimEnd("\", "/"),
        "D:\VST3"
    )
    foreach ($candidate in $forbidden) {
        if ([string]::IsNullOrWhiteSpace($candidate)) {
            continue
        }
        if ($trimmed.Equals($candidate, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "QA root is forbidden because it may contain real product data: $fullPath"
        }
    }
    if ((Split-Path -Leaf $trimmed) -ne "SammyBlazeInstallerQA") {
        throw "QA root must end in the product-owned folder SammyBlazeInstallerQA: $fullPath"
    }
    return $fullPath
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Get-FileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Invoke-BoundedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Description
    )

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WindowStyle Hidden `
        -PassThru
    try {
        $finished = $process.WaitForExit($ProcessTimeoutSeconds * 1000)
        if (-not $finished) {
            Stop-Process -Id $process.Id -Force
            throw "$Description timed out after $ProcessTimeoutSeconds seconds."
        }
        $process.Refresh()
        if ($process.ExitCode -ne 0) {
            throw "$Description failed with exit code $($process.ExitCode)."
        }
        return [ordered]@{
            exitCode = $process.ExitCode
            durationSeconds = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 3)
        }
    }
    finally {
        $stopwatch.Stop()
        $process.Dispose()
    }
}

function Get-SammyBlazeArpEntries {
    return @(
        Get-ItemProperty `
            -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*" `
            -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like "SammyBlaze*" }
    )
}

function Assert-InstalledPayload {
    param(
        [Parameter(Mandatory = $true)][string]$AppRoot,
        [Parameter(Mandatory = $true)][string]$Vst3Root
    )

    $installedManifestPath = Join-Path $AppRoot "release-metadata\manifest.json"
    if (-not (Test-Path -LiteralPath $installedManifestPath -PathType Leaf)) {
        throw "Installed release manifest is missing: $installedManifestPath"
    }
    $manifest = Get-Content -LiteralPath $installedManifestPath -Raw | ConvertFrom-Json
    $verified = 0
    foreach ($entry in $manifest.files) {
        $relative = [string]$entry.path
        if ($relative.StartsWith("standalone/SammyBlaze/")) {
            $suffix = $relative.Substring("standalone/SammyBlaze/".Length)
            $installedPath = Join-Path $AppRoot ($suffix.Replace("/", "\"))
        }
        elseif ($relative.StartsWith("VST3/SammyBlaze.vst3/")) {
            $suffix = $relative.Substring("VST3/SammyBlaze.vst3/".Length)
            $installedPath = Join-Path `
                (Join-Path $Vst3Root "SammyBlaze.vst3") `
                ($suffix.Replace("/", "\"))
        }
        else {
            throw "Manifest path is outside the installer mapping: $relative"
        }
        if (-not (Test-Path -LiteralPath $installedPath -PathType Leaf)) {
            throw "Installed payload file is missing: $installedPath"
        }
        $file = Get-Item -LiteralPath $installedPath
        if ($file.Length -ne [long]$entry.size) {
            throw "Installed payload size mismatch: $installedPath"
        }
        if ((Get-FileSha256 -Path $installedPath) -ne [string]$entry.sha256) {
            throw "Installed payload hash mismatch: $installedPath"
        }
        $verified += 1
    }
    return [ordered]@{
        filesVerified = $verified
        payloadRevision = [string]$manifest.sourceRevision
        productVersion = [string]$manifest.version
    }
}

function Invoke-InstalledDependencyProbe {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string]$ProbePath
    )

    $priorQtPlatform = $env:QT_QPA_PLATFORM
    $priorProbePath = $env:SAMMYBLAZE_PACKAGE_PROBE
    $process = $null
    try {
        $env:QT_QPA_PLATFORM = "offscreen"
        $env:SAMMYBLAZE_PACKAGE_PROBE = $ProbePath
        $process = Start-Process -FilePath $Executable -WindowStyle Hidden -PassThru
        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        while (
            -not (Test-Path -LiteralPath $ProbePath -PathType Leaf) -and
            [DateTime]::UtcNow -lt $deadline
        ) {
            Start-Sleep -Milliseconds 200
            $process.Refresh()
            if ($process.HasExited) {
                throw "Installed dependency probe exited before creating evidence."
            }
        }
        if (-not (Test-Path -LiteralPath $ProbePath -PathType Leaf)) {
            throw "Installed dependency probe timed out."
        }
        $probe = Get-Content -LiteralPath $ProbePath -Raw | ConvertFrom-Json
        if ($probe.status -ne "ok" -or [int]$probe.nativeAudioAbi -ne 1) {
            throw "Installed dependency probe did not report status=ok and ABI=1."
        }
        return $probe
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

if (-not $AllowMachineMutation) {
    throw "Pass -AllowMachineMutation to run the isolated install/reinstall/uninstall scenarios."
}

$resolvedInstaller = Resolve-AbsolutePath -Path $InstallerPath
$resolvedQaRoot = Assert-SafeQaRoot -Path $QaRoot
$resolvedEvidenceRoot = Resolve-AbsolutePath -Path $EvidenceRoot
if (-not (Test-Path -LiteralPath $resolvedInstaller -PathType Leaf)) {
    throw "Installer is missing: $resolvedInstaller"
}
if (@(Get-SammyBlazeArpEntries).Count -gt 0) {
    throw "A current-user SammyBlaze installation already exists; refusing to overlap it."
}

$runId = "{0}-{1}" -f (
    [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
), ([guid]::NewGuid().ToString("N").Substring(0, 8))
$runRoot = Join-Path $resolvedQaRoot $runId
$appRoot = Join-Path $runRoot "app"
$vst3Root = Join-Path $runRoot "VST3"
$foreignPlugin = Join-Path $vst3Root "ForeignPlugin.vst3\foreign.txt"
$installLog = Join-Path $resolvedEvidenceRoot "$runId-install.log"
$repairLog = Join-Path $resolvedEvidenceRoot "$runId-repair.log"
$uninstallLog = Join-Path $resolvedEvidenceRoot "$runId-uninstall.log"
$probePath = Join-Path $resolvedEvidenceRoot "$runId-package-probe.json"
$evidencePath = Join-Path $resolvedEvidenceRoot "$runId-installer-acceptance.json"
New-Item -ItemType Directory -Force -Path $runRoot, $resolvedEvidenceRoot | Out-Null

$signature = Get-AuthenticodeSignature -LiteralPath $resolvedInstaller
$scenarios = [System.Collections.Generic.List[object]]::new()
$releaseDecision = "development-pass-release-blocked"
$cleanupSucceeded = $false
$uninstaller = Join-Path $appRoot "unins000.exe"
$payload = $null

try {
    $installArguments = @(
        "/CURRENTUSER",
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        "/DIR=$appRoot",
        "/VST3DIR=$vst3Root",
        "/TASKS=vst3",
        "/LOG=$installLog"
    )
    $installRun = Invoke-BoundedProcess `
        -FilePath $resolvedInstaller `
        -Arguments $installArguments `
        -Description "Silent custom-path installation"
    $payload = Assert-InstalledPayload -AppRoot $appRoot -Vst3Root $vst3Root
    $arpEntries = @(Get-SammyBlazeArpEntries)
    if ($arpEntries.Count -ne 1) {
        throw "Expected one current-user ARP entry after install; found $($arpEntries.Count)."
    }
    $scenarios.Add([ordered]@{
        id = "I01"
        name = "silent-custom-install"
        status = "passed"
        exitCode = $installRun.exitCode
        durationSeconds = $installRun.durationSeconds
        payloadFilesVerified = $payload.filesVerified
        arpEntries = $arpEntries.Count
        logPath = $installLog
    })

    $installedExecutable = Join-Path $appRoot "SammyBlaze.exe"
    $probe = Invoke-InstalledDependencyProbe `
        -Executable $installedExecutable `
        -ProbePath $probePath
    $priorRequireNative = $env:SAMMYBLAZE_REQUIRE_NATIVE_AUDIO
    try {
        $env:SAMMYBLAZE_REQUIRE_NATIVE_AUDIO = "1"
        $hardwareRun = Invoke-BoundedProcess `
            -FilePath $installedExecutable `
            -Arguments @(
                "--camera", "0",
                "--output", "synth",
                "--sound-program", "40",
                "--max-frames", "8",
                "--headless"
            ) `
            -Description "Installed camera/native-audio smoke"
    }
    finally {
        $env:SAMMYBLAZE_REQUIRE_NATIVE_AUDIO = $priorRequireNative
    }
    $scenarios.Add([ordered]@{
        id = "R01"
        name = "installed-runtime-smoke"
        status = "passed"
        dependencyProbe = [ordered]@{
            status = [string]$probe.status
            nativeAudioAbi = [int]$probe.nativeAudioAbi
        }
        hardwareSmokeExitCode = $hardwareRun.exitCode
        hardwareSmokeDurationSeconds = $hardwareRun.durationSeconds
    })

    $managedDll = Join-Path $appRoot "_internal\SammyBlazeAudioCore.dll"
    Remove-Item -LiteralPath $managedDll -Force
    $repairArguments = @(
        "/CURRENTUSER",
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        "/DIR=$appRoot",
        "/VST3DIR=$vst3Root",
        "/TASKS=vst3",
        "/LOG=$repairLog"
    )
    $repairRun = Invoke-BoundedProcess `
        -FilePath $resolvedInstaller `
        -Arguments $repairArguments `
        -Description "Same-version repair"
    $repairPayload = Assert-InstalledPayload -AppRoot $appRoot -Vst3Root $vst3Root
    $repairArpEntries = @(Get-SammyBlazeArpEntries)
    if ($repairArpEntries.Count -ne 1) {
        throw "Expected one ARP entry after repair; found $($repairArpEntries.Count)."
    }
    $scenarios.Add([ordered]@{
        id = "U02"
        name = "same-version-repair"
        status = "passed"
        exitCode = $repairRun.exitCode
        durationSeconds = $repairRun.durationSeconds
        payloadFilesVerified = $repairPayload.filesVerified
        arpEntries = $repairArpEntries.Count
    })

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $foreignPlugin) |
        Out-Null
    Write-Utf8NoBom -Path $foreignPlugin -Content "foreign QA sentinel`n"
    if (-not (Test-Path -LiteralPath $uninstaller -PathType Leaf)) {
        throw "Installed uninstaller is missing: $uninstaller"
    }
    $uninstallRun = Invoke-BoundedProcess `
        -FilePath $uninstaller `
        -Arguments @(
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/LOG=$uninstallLog"
        ) `
        -Description "Silent uninstall"
    $cleanupDeadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
        $remainingAppFiles = if (Test-Path -LiteralPath $appRoot) {
            @(
                Get-ChildItem `
                    -LiteralPath $appRoot `
                    -Recurse `
                    -File `
                    -ErrorAction SilentlyContinue
            )
        }
        else {
            @()
        }
        $managedVstStillExists = Test-Path -LiteralPath (
            Join-Path $vst3Root "SammyBlaze.vst3"
        )
        $arpStillExists = @(Get-SammyBlazeArpEntries).Count -ne 0
        if (
            $remainingAppFiles.Count -eq 0 -and
            -not $managedVstStillExists -and
            -not $arpStillExists
        ) {
            break
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $cleanupDeadline)

    if (Test-Path -LiteralPath $appRoot) {
        $remainingAppFiles = @(
            Get-ChildItem -LiteralPath $appRoot -Recurse -File -ErrorAction SilentlyContinue
        )
        if ($remainingAppFiles.Count -gt 0) {
            throw "Uninstall left managed application files under $appRoot."
        }
    }
    if (Test-Path -LiteralPath (Join-Path $vst3Root "SammyBlaze.vst3")) {
        throw "Uninstall left the managed VST3 bundle."
    }
    if (-not (Test-Path -LiteralPath $foreignPlugin -PathType Leaf)) {
        throw "Uninstall removed an unrelated neighboring VST sentinel."
    }
    if (@(Get-SammyBlazeArpEntries).Count -ne 0) {
        throw "Uninstall left a current-user ARP entry."
    }
    $scenarios.Add([ordered]@{
        id = "X01"
        name = "silent-uninstall-and-neighbor-preservation"
        status = "passed"
        exitCode = $uninstallRun.exitCode
        durationSeconds = $uninstallRun.durationSeconds
        managedVstRemoved = $true
        foreignVstPreserved = $true
        arpEntries = 0
    })
    $cleanupSucceeded = $true
}
catch {
    $releaseDecision = "development-fail"
    $scenarios.Add([ordered]@{
        id = "FAIL"
        name = "acceptance-run"
        status = "failed"
        error = $_.Exception.Message
    })
    throw
}
finally {
    if (
        -not $cleanupSucceeded -and
        (Test-Path -LiteralPath $uninstaller -PathType Leaf)
    ) {
        try {
            Invoke-BoundedProcess `
                -FilePath $uninstaller `
                -Arguments @(
                    "/VERYSILENT",
                    "/SUPPRESSMSGBOXES",
                    "/NORESTART",
                    "/LOG=$uninstallLog"
                ) `
                -Description "Failure cleanup uninstall" |
                Out-Null
        }
        catch {
            $scenarios.Add([ordered]@{
                id = "CLEANUP"
                name = "failure-cleanup"
                status = "failed"
                error = $_.Exception.Message
            })
        }
    }

    $installerRevision = (& git -C (Join-Path $PSScriptRoot "..\..") rev-parse HEAD).Trim()
    $evidence = [ordered]@{
        schema = "sammyblaze.installer-acceptance"
        schemaVersion = 1
        runId = $runId
        profile = "workstation-current-user-isolated"
        payloadRevision = if ($null -ne $payload) {
            $payload.payloadRevision
        }
        else {
            $null
        }
        installerRevision = $installerRevision
        installer = [ordered]@{
            path = $resolvedInstaller
            bytes = (Get-Item -LiteralPath $resolvedInstaller).Length
            sha256 = Get-FileSha256 -Path $resolvedInstaller
            authenticodeStatus = [string]$signature.Status
            signed = $signature.Status -eq "Valid"
        }
        host = [ordered]@{
            windowsVersion = [Environment]::OSVersion.VersionString
            architecture = [Environment]::GetEnvironmentVariable(
                "PROCESSOR_ARCHITECTURE"
            )
            elevated = (
                [Security.Principal.WindowsPrincipal]::new(
                    [Security.Principal.WindowsIdentity]::GetCurrent()
                )
            ).IsInRole(
                [Security.Principal.WindowsBuiltInRole]::Administrator
            )
        }
        paths = [ordered]@{
            runRoot = $runRoot
            appRoot = $appRoot
            vst3Root = $vst3Root
        }
        scenarios = $scenarios
        blocked = @(
            "standard Program Files/Common Files install requires an elevated clean VM",
            "forward upgrade and rollback require a genuine previous signed installer",
            "Authenticode release signing requires the production certificate",
            "FL Studio host discovery requires FL Studio"
        )
        releaseDecision = $releaseDecision
    }
    $temporaryEvidence = "$evidencePath.tmp"
    Write-Utf8NoBom `
        -Path $temporaryEvidence `
        -Content (($evidence | ConvertTo-Json -Depth 10) + "`n")
    Move-Item -LiteralPath $temporaryEvidence -Destination $evidencePath -Force
}

if ($cleanupSucceeded -and (Test-Path -LiteralPath $runRoot)) {
    $resolvedRunRoot = (Resolve-Path -LiteralPath $runRoot).Path
    if ($resolvedRunRoot.StartsWith(
        $resolvedQaRoot.TrimEnd("\", "/") + "\",
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        Remove-Item -LiteralPath $resolvedRunRoot -Recurse -Force
    }
}

Write-Host "Installer acceptance: PASS"
Write-Host "Evidence: $evidencePath"
