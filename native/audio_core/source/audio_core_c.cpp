#include "sammyblaze/audio_core/audio_core_c.h"

#include "sammyblaze/audio_core/presets.h"
#include "sammyblaze/audio_core/synth_engine.h"

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <new>
#include <type_traits>

using SammyBlaze::AudioCore::FilterType;
using SammyBlaze::AudioCore::SynthEngine;
using SammyBlaze::AudioCore::Waveform;
using SammyBlaze::AudioCore::kPresetCount;
using SammyBlaze::AudioCore::presetForProgram;

struct sbw_audio_core
{
    SynthEngine engine;
};

static_assert (std::is_standard_layout_v<sbw_audio_core_patch_v1>);
static_assert (sizeof (sbw_audio_core_patch_v1) == 96);
static_assert (offsetof (sbw_audio_core_patch_v1, struct_size) == 0);
static_assert (offsetof (sbw_audio_core_patch_v1, abi_version) == 4);
static_assert (offsetof (sbw_audio_core_patch_v1, program) == 8);
static_assert (offsetof (sbw_audio_core_patch_v1, waveform_a) == 12);
static_assert (offsetof (sbw_audio_core_patch_v1, waveform_b) == 16);
static_assert (offsetof (sbw_audio_core_patch_v1, filter_type) == 20);
static_assert (offsetof (sbw_audio_core_patch_v1, unison_voices) == 24);
static_assert (offsetof (sbw_audio_core_patch_v1, waveform_mix) == 28);
static_assert (offsetof (sbw_audio_core_patch_v1, brightness) == 92);

namespace {

bool validPatch (const sbw_audio_core_patch_v1& patch) noexcept
{
    const auto finiteInRange = [] (float value, float minimum, float maximum) {
        return std::isfinite (value) && value >= minimum && value <= maximum;
    };
    return patch.struct_size == sizeof (sbw_audio_core_patch_v1) &&
           patch.abi_version == SBW_AUDIO_CORE_ABI_VERSION &&
           patch.program < kPresetCount && patch.waveform_a <= 9 &&
           patch.waveform_b <= 9 && patch.filter_type <= 3 &&
           patch.unison_voices >= 1 && patch.unison_voices <= 16 &&
           finiteInRange (patch.waveform_mix, 0.0f, 1.0f) &&
           finiteInRange (patch.attack_ms, 0.0f, 20000.0f) &&
           finiteInRange (patch.decay_ms, 0.0f, 20000.0f) &&
           finiteInRange (patch.sustain, 0.0f, 1.0f) &&
           finiteInRange (patch.release_ms, 0.0f, 30000.0f) &&
           finiteInRange (patch.filter_cutoff_hz, 20.0f, 20000.0f) &&
           finiteInRange (patch.filter_resonance, 0.0f, 1.0f) &&
           finiteInRange (patch.filter_envelope, -1.0f, 1.0f) &&
           finiteInRange (patch.detune_cents, 0.0f, 100.0f) &&
           finiteInRange (patch.vibrato_rate_hz, 0.0f, 15.0f) &&
           finiteInRange (
               patch.vibrato_depth_semitones,
               0.0f,
               2.0f) &&
           finiteInRange (patch.reverb_mix, 0.0f, 1.0f) &&
           finiteInRange (patch.delay_mix, 0.0f, 1.0f) &&
           finiteInRange (patch.delay_time_ms, 1.0f, 2500.0f) &&
           finiteInRange (patch.chorus_mix, 0.0f, 1.0f) &&
           finiteInRange (patch.master_gain, 0.0f, 1.0f) &&
           finiteInRange (patch.brightness, 0.0f, 1.0f);
}

} // namespace

extern "C" {

uint32_t sbw_audio_core_abi_version (void)
{
    return SBW_AUDIO_CORE_ABI_VERSION;
}

sbw_audio_core* sbw_audio_core_create (
    double sample_rate,
    uint32_t max_block_size)
{
    try
    {
        auto* core = new (std::nothrow) sbw_audio_core;
        if (!core)
            return nullptr;
        if (!core->engine.setup (sample_rate, max_block_size))
        {
            delete core;
            return nullptr;
        }
        return core;
    }
    catch (...)
    {
        return nullptr;
    }
}

void sbw_audio_core_destroy (sbw_audio_core* core)
{
    try
    {
        delete core;
    }
    catch (...)
    {
    }
}

int32_t sbw_audio_core_note_on (
    sbw_audio_core* core,
    uint32_t note,
    float velocity)
{
    try
    {
        if (!core || note > 127 || !std::isfinite (velocity) ||
            velocity < 0.0f || velocity > 1.0f)
            return SBW_AUDIO_CORE_INVALID_ARGUMENT;
        core->engine.noteOn (static_cast<std::uint8_t> (note), velocity);
        return SBW_AUDIO_CORE_OK;
    }
    catch (...)
    {
        return SBW_AUDIO_CORE_RENDER_FAILED;
    }
}

int32_t sbw_audio_core_note_off (sbw_audio_core* core, uint32_t note)
{
    try
    {
        if (!core || note > 127)
            return SBW_AUDIO_CORE_INVALID_ARGUMENT;
        core->engine.noteOff (static_cast<std::uint8_t> (note));
        return SBW_AUDIO_CORE_OK;
    }
    catch (...)
    {
        return SBW_AUDIO_CORE_RENDER_FAILED;
    }
}

int32_t sbw_audio_core_control_change (
    sbw_audio_core* core,
    uint32_t controller,
    uint32_t value)
{
    try
    {
        if (!core || controller > 127 || value > 127)
            return SBW_AUDIO_CORE_INVALID_ARGUMENT;
        core->engine.controlChange (
            static_cast<std::uint8_t> (controller),
            static_cast<std::uint8_t> (value));
        return SBW_AUDIO_CORE_OK;
    }
    catch (...)
    {
        return SBW_AUDIO_CORE_RENDER_FAILED;
    }
}

int32_t sbw_audio_core_program_change (
    sbw_audio_core* core,
    uint32_t program)
{
    try
    {
        if (!core || program >= kPresetCount)
            return SBW_AUDIO_CORE_INVALID_ARGUMENT;
        core->engine.programChange (static_cast<std::uint8_t> (program));
        return SBW_AUDIO_CORE_OK;
    }
    catch (...)
    {
        return SBW_AUDIO_CORE_RENDER_FAILED;
    }
}

int32_t sbw_audio_core_apply_patch (
    sbw_audio_core* core,
    const sbw_audio_core_patch_v1* patch)
{
    try
    {
        if (!core || !patch || !validPatch (*patch))
            return SBW_AUDIO_CORE_INVALID_ARGUMENT;
        auto preset =
            presetForProgram (static_cast<std::uint8_t> (patch->program));
        preset.waveformA = static_cast<Waveform> (patch->waveform_a);
        preset.waveformB = static_cast<Waveform> (patch->waveform_b);
        preset.filterType = static_cast<FilterType> (patch->filter_type);
        preset.unisonVoices =
            static_cast<std::uint8_t> (patch->unison_voices);
        preset.waveformMix = patch->waveform_mix;
        preset.attackMs = patch->attack_ms;
        preset.decayMs = patch->decay_ms;
        preset.sustain = patch->sustain;
        preset.releaseMs = patch->release_ms;
        preset.filterCutoffHz = patch->filter_cutoff_hz;
        preset.filterResonance = patch->filter_resonance;
        preset.filterEnvelope = patch->filter_envelope;
        preset.detuneCents = patch->detune_cents;
        preset.vibratoRateHz = patch->vibrato_rate_hz;
        preset.vibratoDepthSemitones =
            patch->vibrato_depth_semitones;
        preset.reverbMix = patch->reverb_mix;
        preset.delayMix = patch->delay_mix;
        preset.delayTimeMs = patch->delay_time_ms;
        preset.chorusMix = patch->chorus_mix;
        return core->engine.applyPatch (
                   preset,
                   patch->master_gain,
                   patch->brightness)
                   ? SBW_AUDIO_CORE_OK
                   : SBW_AUDIO_CORE_INVALID_ARGUMENT;
    }
    catch (...)
    {
        return SBW_AUDIO_CORE_RENDER_FAILED;
    }
}

int32_t sbw_audio_core_render_interleaved (
    sbw_audio_core* core,
    float* stereo_output,
    uint32_t frames)
{
    try
    {
        if (!core || !stereo_output || frames == 0 ||
            frames > core->engine.maximumBlockSize ())
            return SBW_AUDIO_CORE_INVALID_ARGUMENT;
        if (!core->engine.isReady ())
            return SBW_AUDIO_CORE_NOT_READY;
        return core->engine.renderInterleaved (stereo_output, frames)
                   ? SBW_AUDIO_CORE_OK
                   : SBW_AUDIO_CORE_RENDER_FAILED;
    }
    catch (...)
    {
        return SBW_AUDIO_CORE_RENDER_FAILED;
    }
}

int32_t sbw_audio_core_panic (sbw_audio_core* core)
{
    try
    {
        if (!core)
            return SBW_AUDIO_CORE_INVALID_ARGUMENT;
        core->engine.panic ();
        return SBW_AUDIO_CORE_OK;
    }
    catch (...)
    {
        return SBW_AUDIO_CORE_RENDER_FAILED;
    }
}

uint32_t sbw_audio_core_active_voice_count (const sbw_audio_core* core)
{
    try
    {
        return core ? core->engine.activeVoiceCount () : 0;
    }
    catch (...)
    {
        return 0;
    }
}

uint64_t sbw_audio_core_nonfinite_recovery_count (
    const sbw_audio_core* core)
{
    try
    {
        return core ? core->engine.nonfiniteRecoveryCount () : 0;
    }
    catch (...)
    {
        return 0;
    }
}

} // extern "C"
