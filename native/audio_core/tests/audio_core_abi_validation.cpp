#include "sammyblaze/audio_core/audio_core_c.h"

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <type_traits>

static_assert (std::is_standard_layout_v<sbw_audio_core_patch_v1>);
static_assert (sizeof (sbw_audio_core_patch_v1) == 96);
static_assert (offsetof (sbw_audio_core_patch_v1, waveform_mix) == 28);
static_assert (offsetof (sbw_audio_core_patch_v1, brightness) == 92);

namespace {

sbw_audio_core_patch_v1 validPatch ()
{
    return {
        sizeof (sbw_audio_core_patch_v1),
        SBW_AUDIO_CORE_ABI_VERSION,
        60,
        2,
        3,
        0,
        8,
        0.4f,
        5.0f,
        300.0f,
        0.7f,
        450.0f,
        4200.0f,
        0.4f,
        0.2f,
        17.0f,
        5.2f,
        0.25f,
        0.35f,
        0.22f,
        380.0f,
        0.18f,
        0.8f,
        0.65f,
    };
}

bool finiteOutput (const std::array<float, 512>& output)
{
    for (const auto sample : output)
    {
        if (!std::isfinite (sample))
            return false;
    }
    return true;
}

bool validateNullAndRangeContracts ()
{
    std::array<float, 512> output {};
    auto patch = validPatch ();
    if (sbw_audio_core_create (7999.0, 256) != nullptr ||
        sbw_audio_core_create (48000.0, 0) != nullptr ||
        sbw_audio_core_note_on (nullptr, 60, 1.0f) !=
            SBW_AUDIO_CORE_INVALID_ARGUMENT ||
        sbw_audio_core_note_off (nullptr, 60) !=
            SBW_AUDIO_CORE_INVALID_ARGUMENT ||
        sbw_audio_core_control_change (nullptr, 64, 127) !=
            SBW_AUDIO_CORE_INVALID_ARGUMENT ||
        sbw_audio_core_program_change (nullptr, 0) !=
            SBW_AUDIO_CORE_INVALID_ARGUMENT ||
        sbw_audio_core_apply_patch (nullptr, &patch) !=
            SBW_AUDIO_CORE_INVALID_ARGUMENT ||
        sbw_audio_core_render_interleaved (
            nullptr,
            output.data (),
            256) != SBW_AUDIO_CORE_INVALID_ARGUMENT ||
        sbw_audio_core_panic (nullptr) !=
            SBW_AUDIO_CORE_INVALID_ARGUMENT ||
        sbw_audio_core_active_voice_count (nullptr) != 0 ||
        sbw_audio_core_nonfinite_recovery_count (nullptr) != 0)
        return false;

    auto* core = sbw_audio_core_create (48000.0, 256);
    if (!core)
        return false;
    const auto valid =
        sbw_audio_core_note_on (core, 128, 1.0f) ==
            SBW_AUDIO_CORE_INVALID_ARGUMENT &&
        sbw_audio_core_note_on (
            core,
            60,
            std::numeric_limits<float>::quiet_NaN ()) ==
            SBW_AUDIO_CORE_INVALID_ARGUMENT &&
        sbw_audio_core_control_change (core, 128, 0) ==
            SBW_AUDIO_CORE_INVALID_ARGUMENT &&
        sbw_audio_core_control_change (core, 64, 128) ==
            SBW_AUDIO_CORE_INVALID_ARGUMENT &&
        sbw_audio_core_program_change (core, 120) ==
            SBW_AUDIO_CORE_INVALID_ARGUMENT &&
        sbw_audio_core_render_interleaved (core, nullptr, 256) ==
            SBW_AUDIO_CORE_INVALID_ARGUMENT &&
        sbw_audio_core_render_interleaved (
            core,
            output.data (),
            0) == SBW_AUDIO_CORE_INVALID_ARGUMENT &&
        sbw_audio_core_render_interleaved (
            core,
            output.data (),
            257) == SBW_AUDIO_CORE_INVALID_ARGUMENT;
    sbw_audio_core_destroy (core);
    sbw_audio_core_destroy (nullptr);
    return valid;
}

bool validatePatchContract ()
{
    auto* core = sbw_audio_core_create (48000.0, 256);
    if (!core)
        return false;
    auto patch = validPatch ();
    if (sbw_audio_core_apply_patch (core, &patch) != SBW_AUDIO_CORE_OK)
        return false;

    auto invalid = patch;
    invalid.struct_size -= 4;
    if (sbw_audio_core_apply_patch (core, &invalid) !=
        SBW_AUDIO_CORE_INVALID_ARGUMENT)
        return false;
    invalid = patch;
    invalid.abi_version = 2;
    if (sbw_audio_core_apply_patch (core, &invalid) !=
        SBW_AUDIO_CORE_INVALID_ARGUMENT)
        return false;
    invalid = patch;
    invalid.waveform_a = 10;
    if (sbw_audio_core_apply_patch (core, &invalid) !=
        SBW_AUDIO_CORE_INVALID_ARGUMENT)
        return false;
    invalid = patch;
    invalid.master_gain =
        std::numeric_limits<float>::quiet_NaN ();
    if (sbw_audio_core_apply_patch (core, &invalid) !=
        SBW_AUDIO_CORE_INVALID_ARGUMENT)
        return false;
    sbw_audio_core_destroy (core);
    return true;
}

bool validatePerformanceControls ()
{
    std::array<float, 512> output {};
    auto* core = sbw_audio_core_create (48000.0, 256);
    if (!core || sbw_audio_core_abi_version () != 1)
        return false;
    auto patch = validPatch ();
    if (sbw_audio_core_apply_patch (core, &patch) != SBW_AUDIO_CORE_OK ||
        sbw_audio_core_program_change (core, 119) != SBW_AUDIO_CORE_OK ||
        sbw_audio_core_note_on (core, 60, 1.0f) != SBW_AUDIO_CORE_OK ||
        sbw_audio_core_active_voice_count (core) != 1 ||
        sbw_audio_core_control_change (core, 64, 127) !=
            SBW_AUDIO_CORE_OK ||
        sbw_audio_core_note_off (core, 60) != SBW_AUDIO_CORE_OK ||
        sbw_audio_core_render_interleaved (
            core,
            output.data (),
            256) != SBW_AUDIO_CORE_OK ||
        !finiteOutput (output) ||
        sbw_audio_core_active_voice_count (core) != 1 ||
        sbw_audio_core_nonfinite_recovery_count (core) != 0 ||
        sbw_audio_core_panic (core) != SBW_AUDIO_CORE_OK ||
        sbw_audio_core_active_voice_count (core) != 0)
    {
        sbw_audio_core_destroy (core);
        return false;
    }
    sbw_audio_core_destroy (core);
    return true;
}

} // namespace

int main ()
{
    if (!validateNullAndRangeContracts () ||
        !validatePatchContract () ||
        !validatePerformanceControls ())
    {
        std::cerr << "C ABI v1 validation failed\n";
        return 1;
    }
    std::cout << "PASS: C ABI v1 layout, validation, patch, note, "
                 "sustain, render and panic\n";
    return 0;
}
