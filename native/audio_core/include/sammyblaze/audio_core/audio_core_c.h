#pragma once

#include <stdint.h>

#if defined(_WIN32)
#if defined(SBW_AUDIO_CORE_BUILD)
#define SBW_AUDIO_CORE_API __declspec(dllexport)
#else
#define SBW_AUDIO_CORE_API __declspec(dllimport)
#endif
#else
#define SBW_AUDIO_CORE_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define SBW_AUDIO_CORE_ABI_VERSION 1u

typedef struct sbw_audio_core sbw_audio_core;

typedef enum sbw_audio_core_status
{
    SBW_AUDIO_CORE_OK = 0,
    SBW_AUDIO_CORE_INVALID_ARGUMENT = -1,
    SBW_AUDIO_CORE_NOT_READY = -2,
    SBW_AUDIO_CORE_RENDER_FAILED = -3
} sbw_audio_core_status;

typedef struct sbw_audio_core_patch_v1
{
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t program;
    uint32_t waveform_a;
    uint32_t waveform_b;
    uint32_t filter_type;
    uint32_t unison_voices;
    float waveform_mix;
    float attack_ms;
    float decay_ms;
    float sustain;
    float release_ms;
    float filter_cutoff_hz;
    float filter_resonance;
    float filter_envelope;
    float detune_cents;
    float vibrato_rate_hz;
    float vibrato_depth_semitones;
    float reverb_mix;
    float delay_mix;
    float delay_time_ms;
    float chorus_mix;
    float master_gain;
    float brightness;
} sbw_audio_core_patch_v1;

SBW_AUDIO_CORE_API uint32_t sbw_audio_core_abi_version (void);
SBW_AUDIO_CORE_API sbw_audio_core* sbw_audio_core_create (
    double sample_rate,
    uint32_t max_block_size);
SBW_AUDIO_CORE_API void sbw_audio_core_destroy (sbw_audio_core* core);
SBW_AUDIO_CORE_API int32_t sbw_audio_core_note_on (
    sbw_audio_core* core,
    uint32_t note,
    float velocity);
SBW_AUDIO_CORE_API int32_t sbw_audio_core_note_off (
    sbw_audio_core* core,
    uint32_t note);
SBW_AUDIO_CORE_API int32_t sbw_audio_core_control_change (
    sbw_audio_core* core,
    uint32_t controller,
    uint32_t value);
SBW_AUDIO_CORE_API int32_t sbw_audio_core_program_change (
    sbw_audio_core* core,
    uint32_t program);
SBW_AUDIO_CORE_API int32_t sbw_audio_core_apply_patch (
    sbw_audio_core* core,
    const sbw_audio_core_patch_v1* patch);
SBW_AUDIO_CORE_API int32_t sbw_audio_core_render_interleaved (
    sbw_audio_core* core,
    float* stereo_output,
    uint32_t frames);
SBW_AUDIO_CORE_API int32_t sbw_audio_core_panic (sbw_audio_core* core);
SBW_AUDIO_CORE_API uint32_t sbw_audio_core_active_voice_count (
    const sbw_audio_core* core);
SBW_AUDIO_CORE_API uint64_t sbw_audio_core_nonfinite_recovery_count (
    const sbw_audio_core* core);

#ifdef __cplusplus
}
#endif

