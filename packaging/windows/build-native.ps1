param(
    [string]$Vst3SdkRoot = "D:\SammyBlazeDeps\vst3sdk",
    [string]$Configuration = "Release",
    [string]$BuildDirectory = "D:\SammyBlazeBuild\native",
    [switch]$Validate
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$cmake = "D:\VisualStudio\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
$ninja = "D:\VisualStudio\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
$vcvars = "D:\VisualStudio\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
$buildDirectory = $BuildDirectory

if (-not (Test-Path -LiteralPath $cmake)) {
    throw "Visual Studio CMake was not found at $cmake"
}
if (-not (Test-Path -LiteralPath $ninja)) {
    throw "Visual Studio Ninja was not found at $ninja"
}
if (-not (Test-Path -LiteralPath $vcvars)) {
    throw "Visual Studio x64 compiler environment was not found at $vcvars"
}
if (-not (Test-Path -LiteralPath (Join-Path $Vst3SdkRoot "CMakeLists.txt"))) {
    throw "VST3 SDK was not found at $Vst3SdkRoot"
}

$developerEnvironment = & cmd.exe /d /s /c "`"$vcvars`" >nul && set"
if ($LASTEXITCODE -ne 0) {
    throw "Visual Studio x64 compiler environment failed to initialize"
}
foreach ($line in $developerEnvironment) {
    if ($line -match "^([^=]+)=(.*)$") {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}
$env:PATH = "$(Split-Path -Parent $ninja);$env:PATH"

& $cmake --fresh -S $repoRoot -B $buildDirectory -G "Ninja Multi-Config" `
    "-DCMAKE_CONFIGURATION_TYPES=$Configuration" `
    "-DCMAKE_MAKE_PROGRAM=$ninja" `
    "-DVST3_SDK_ROOT=$Vst3SdkRoot"
if ($LASTEXITCODE -ne 0) {
    throw "Native CMake configure failed"
}

& $cmake --build $buildDirectory --config $Configuration --target SammyBlazeVST3
if ($LASTEXITCODE -ne 0) {
    throw "Native VST3 build failed"
}

$bundle = Join-Path $buildDirectory "VST3\$Configuration\SammyBlaze.vst3"
$binary = Join-Path $bundle "Contents\x86_64-win\SammyBlaze.vst3"
if (-not (Test-Path -LiteralPath $binary)) {
    throw "Native VST3 bundle is incomplete: $binary"
}

if ($Validate) {
    & $cmake --build $buildDirectory --config $Configuration --target validator
    if ($LASTEXITCODE -ne 0) {
        throw "Steinberg validator build failed"
    }
    $validator = Join-Path $buildDirectory "bin\$Configuration\validator.exe"
    & $validator -selftest
    if ($LASTEXITCODE -ne 0) {
        throw "Steinberg validator self-test failed"
    }
    & $validator $bundle
    if ($LASTEXITCODE -ne 0) {
        throw "SammyBlaze VST3 validation failed"
    }
}

Get-Item -LiteralPath $bundle, $binary |
    Select-Object FullName, Length, LastWriteTime
