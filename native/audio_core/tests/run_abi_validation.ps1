param(
    [Parameter(Mandatory = $true)]
    [string]$DllPath,
    [string]$Python = "D:\Python312\python.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $DllPath)) {
    throw "Audio-core DLL was not found: $DllPath"
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python runtime was not found: $Python"
}

$validationCode = @'
import ctypes
import math
import os
import statistics
import time

dll_path = os.environ["SBW_AUDIO_CORE_DLL"]
dll = ctypes.WinDLL(dll_path)


class PatchV1(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("program", ctypes.c_uint32),
        ("waveform_a", ctypes.c_uint32),
        ("waveform_b", ctypes.c_uint32),
        ("filter_type", ctypes.c_uint32),
        ("unison_voices", ctypes.c_uint32),
        ("waveform_mix", ctypes.c_float),
        ("attack_ms", ctypes.c_float),
        ("decay_ms", ctypes.c_float),
        ("sustain", ctypes.c_float),
        ("release_ms", ctypes.c_float),
        ("filter_cutoff_hz", ctypes.c_float),
        ("filter_resonance", ctypes.c_float),
        ("filter_envelope", ctypes.c_float),
        ("detune_cents", ctypes.c_float),
        ("vibrato_rate_hz", ctypes.c_float),
        ("vibrato_depth_semitones", ctypes.c_float),
        ("reverb_mix", ctypes.c_float),
        ("delay_mix", ctypes.c_float),
        ("delay_time_ms", ctypes.c_float),
        ("chorus_mix", ctypes.c_float),
        ("master_gain", ctypes.c_float),
        ("brightness", ctypes.c_float),
    ]


dll.sbw_audio_core_abi_version.restype = ctypes.c_uint32
dll.sbw_audio_core_create.argtypes = [ctypes.c_double, ctypes.c_uint32]
dll.sbw_audio_core_create.restype = ctypes.c_void_p
dll.sbw_audio_core_destroy.argtypes = [ctypes.c_void_p]
dll.sbw_audio_core_note_on.argtypes = [
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.c_float,
]
dll.sbw_audio_core_note_off.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
dll.sbw_audio_core_control_change.argtypes = [
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.c_uint32,
]
dll.sbw_audio_core_program_change.argtypes = [
    ctypes.c_void_p,
    ctypes.c_uint32,
]
dll.sbw_audio_core_apply_patch.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(PatchV1),
]
dll.sbw_audio_core_render_interleaved.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_float),
    ctypes.c_uint32,
]
dll.sbw_audio_core_panic.argtypes = [ctypes.c_void_p]
dll.sbw_audio_core_active_voice_count.argtypes = [ctypes.c_void_p]
dll.sbw_audio_core_active_voice_count.restype = ctypes.c_uint32
dll.sbw_audio_core_nonfinite_recovery_count.argtypes = [ctypes.c_void_p]
dll.sbw_audio_core_nonfinite_recovery_count.restype = ctypes.c_uint64


def heavy_patch():
    return PatchV1(
        96,
        1,
        107,
        6,
        9,
        0,
        16,
        0.5,
        0.0,
        1.0,
        1.0,
        1000.0,
        6500.0,
        0.55,
        0.3,
        36.0,
        5.2,
        0.35,
        0.8,
        0.7,
        380.0,
        0.8,
        0.75,
        0.8,
    )


def create(rate=48000.0):
    core = dll.sbw_audio_core_create(rate, 256)
    assert core, f"create failed at {rate} Hz"
    return core


assert ctypes.sizeof(PatchV1) == 96
assert PatchV1.waveform_mix.offset == 28
assert PatchV1.brightness.offset == 92
assert dll.sbw_audio_core_abi_version() == 1
assert not dll.sbw_audio_core_create(7999.0, 256)
assert not dll.sbw_audio_core_create(48000.0, 0)

left_core = create()
right_core = create()
patch = heavy_patch()
assert dll.sbw_audio_core_apply_patch(left_core, ctypes.byref(patch)) == 0
assert dll.sbw_audio_core_apply_patch(right_core, ctypes.byref(patch)) == 0
for note in range(36, 60):
    assert dll.sbw_audio_core_note_on(left_core, note, 0.8) == 0
    assert dll.sbw_audio_core_note_on(right_core, note, 0.8) == 0
left_output = (ctypes.c_float * 512)()
right_output = (ctypes.c_float * 512)()
for _ in range(32):
    assert dll.sbw_audio_core_render_interleaved(left_core, left_output, 256) == 0
    assert dll.sbw_audio_core_render_interleaved(right_core, right_output, 256) == 0
    assert bytes(left_output) == bytes(right_output)
assert dll.sbw_audio_core_active_voice_count(left_core) == 24
assert dll.sbw_audio_core_nonfinite_recovery_count(left_core) == 0
dll.sbw_audio_core_destroy(left_core)
dll.sbw_audio_core_destroy(right_core)
print("PASS: C ABI deterministic parity across twin 24-voice engines")

render_count = 0
for sample_rate in (32000.0, 44100.0, 48000.0, 96000.0, 192000.0):
    core = create(sample_rate)
    output = (ctypes.c_float * 512)()
    for program in range(120):
        assert dll.sbw_audio_core_program_change(core, program) == 0
        assert dll.sbw_audio_core_note_on(core, 60, 1.0) == 0
        for _ in range(6):
            assert dll.sbw_audio_core_render_interleaved(core, output, 256) == 0
            assert all(math.isfinite(value) for value in output)
            render_count += 1
        assert dll.sbw_audio_core_note_off(core, 60) == 0
        assert dll.sbw_audio_core_panic(core) == 0
    assert dll.sbw_audio_core_nonfinite_recovery_count(core) == 0
    dll.sbw_audio_core_destroy(core)
assert render_count == 3600
print("PASS: C ABI factory render 3600/3600 finite at five sample rates")

core = create()
output = (ctypes.c_float * 512)()
assert dll.sbw_audio_core_note_on(core, 60, 1.0) == 0
assert dll.sbw_audio_core_control_change(core, 64, 127) == 0
assert dll.sbw_audio_core_note_off(core, 60) == 0
for _ in range(12):
    assert dll.sbw_audio_core_render_interleaved(core, output, 256) == 0
assert dll.sbw_audio_core_active_voice_count(core) == 1
assert dll.sbw_audio_core_panic(core) == 0
assert dll.sbw_audio_core_active_voice_count(core) == 0
dll.sbw_audio_core_destroy(core)
print("PASS: C ABI note, sustain, release and panic semantics")

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x80)
kernel32.SetThreadPriority(kernel32.GetCurrentThread(), 2)
core = create()
patch = heavy_patch()
assert dll.sbw_audio_core_apply_patch(core, ctypes.byref(patch)) == 0
for note in range(36, 60):
    assert dll.sbw_audio_core_note_on(core, note, 0.8) == 0
output = (ctypes.c_float * 512)()
for _ in range(500):
    assert dll.sbw_audio_core_render_interleaved(core, output, 256) == 0
durations_ms = []
for _ in range(5000):
    started = time.perf_counter_ns()
    assert dll.sbw_audio_core_render_interleaved(core, output, 256) == 0
    durations_ms.append((time.perf_counter_ns() - started) / 1_000_000)
durations_ms.sort()


def percentile(quantile):
    return durations_ms[math.ceil(quantile * (len(durations_ms) - 1))]


mean = statistics.fmean(durations_ms)
p50 = percentile(0.50)
p95 = percentile(0.95)
p99 = percentile(0.99)
maximum = durations_ms[-1]
deadline = 256 / 48000 * 1000
headroom = deadline / p95
outcome = "PASS" if p95 <= 2.67 else "FAIL"
print(
    "BENCHMARK: "
    f"voices=24 blocks=5000 frames=256 rate=48000 "
    f"mean={mean:.4f}ms p50={p50:.4f}ms p95={p95:.4f}ms "
    f"p99={p99:.4f}ms max={maximum:.4f}ms "
    f"deadline={deadline:.4f}ms headroom={headroom:.2f}x "
    f"target=2.6700ms result={outcome}"
)
dll.sbw_audio_core_destroy(core)
assert p95 <= 2.67, f"p95 target missed: {p95:.4f} ms"
'@

$env:SBW_AUDIO_CORE_DLL = (Resolve-Path -LiteralPath $DllPath).Path
$temporaryScript = Join-Path `
    ([System.IO.Path]::GetTempPath()) `
    ("sammyblaze-audio-core-validation-{0}.py" -f [guid]::NewGuid().ToString("N"))
try {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($temporaryScript, $validationCode, $encoding)
    & $Python $temporaryScript
    if ($LASTEXITCODE -ne 0) {
        throw "C ABI runtime validation failed with exit code $LASTEXITCODE"
    }
}
finally {
    if (Test-Path -LiteralPath $temporaryScript -PathType Leaf) {
        Remove-Item -LiteralPath $temporaryScript -Force
    }
}
