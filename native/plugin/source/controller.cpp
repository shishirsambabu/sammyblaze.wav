#include "controller.h"

#include "base/source/fstreamer.h"
#include "ids.h"
#include "pluginterfaces/base/ustring.h"
#include "presets.h"
#include "public.sdk/source/vst/vstparameters.h"

#include <algorithm>
#include <array>
#include <cmath>

namespace Steinberg::Vst::SammyBlaze {
namespace {

ParamValue logarithmicNormalized (float value, float minimum, float maximum)
{
    return std::log (std::max (value, minimum) / minimum) /
           std::log (maximum / minimum);
}

void appendAscii (StringListParameter& parameter, const char* value)
{
    String128 label {};
    UString (label, 128).fromAscii (value);
    parameter.appendString (label);
}

} // namespace

tresult PLUGIN_API Controller::initialize (FUnknown* context)
{
    const auto result = EditController::initialize (context);
    if (result != kResultOk)
        return result;

    parameters.addParameter (
        STR16 ("Master Gain"), STR16 ("%"), 0, 0.75, ParameterInfo::kCanAutomate, kMasterGainId);
    parameters.addParameter (
        STR16 ("Vibrato Depth"), STR16 ("cent"), 0, 0.25,
        ParameterInfo::kCanAutomate, kVibratoDepthId);
    parameters.addParameter (
        STR16 ("Expression"), STR16 ("%"), 0, 1.0, ParameterInfo::kCanAutomate, kExpressionId);
    parameters.addParameter (
        STR16 ("Brightness"), STR16 ("%"), 0, 0.5, ParameterInfo::kCanAutomate, kBrightnessId);
    parameters.addParameter (
        STR16 ("Reverb Mix"), STR16 ("%"), 0, 0.05, ParameterInfo::kCanAutomate, kReverbMixId);
    parameters.addParameter (
        STR16 ("Delay Mix"), STR16 ("%"), 0, 0.05, ParameterInfo::kCanAutomate, kDelayMixId);
    parameters.addParameter (
        STR16 ("Chorus Mix"), STR16 ("%"), 0, 0.20, ParameterInfo::kCanAutomate, kChorusMixId);

    const auto defaultPatch = presetForProgram (0);
    auto* sound = new StringListParameter (
        STR16 ("Factory Sound"),
        kSoundProgramId,
        nullptr,
        ParameterInfo::kCanAutomate | ParameterInfo::kIsList |
            ParameterInfo::kIsProgramChange);
    for (std::size_t program = 0; program < kPresetCount; ++program)
    {
        appendAscii (*sound, presetName (program));
    }
    parameters.addParameter (sound);

    constexpr std::array<const char*, 10> waveformNames {{
        "Sine", "Triangle", "Saw", "Square", "Pulse",
        "Organ", "Metal", "Noise", "Vocal", "Wavetable",
    }};
    auto* waveformA =
        new StringListParameter (STR16 ("Oscillator A"), kWaveformAId, nullptr);
    auto* waveformB =
        new StringListParameter (STR16 ("Oscillator B"), kWaveformBId, nullptr);
    for (const auto* waveformName : waveformNames)
    {
        appendAscii (*waveformA, waveformName);
        appendAscii (*waveformB, waveformName);
    }
    parameters.addParameter (waveformA);
    parameters.addParameter (waveformB);
    parameters.addParameter (
        STR16 ("Oscillator Mix"), STR16 ("%"), 0, defaultPatch.waveformMix,
        ParameterInfo::kCanAutomate, kWaveformMixId);
    parameters.addParameter (
        STR16 ("Attack"), STR16 ("ms"), 0,
        logarithmicNormalized (defaultPatch.attackMs, 0.5f, 20000.0f),
        ParameterInfo::kCanAutomate, kAttackId);
    parameters.addParameter (
        STR16 ("Decay"), STR16 ("ms"), 0,
        logarithmicNormalized (defaultPatch.decayMs, 0.5f, 20000.0f),
        ParameterInfo::kCanAutomate, kDecayId);
    parameters.addParameter (
        STR16 ("Sustain"), STR16 ("%"), 0, defaultPatch.sustain,
        ParameterInfo::kCanAutomate, kSustainId);
    parameters.addParameter (
        STR16 ("Release"), STR16 ("ms"), 0,
        logarithmicNormalized (defaultPatch.releaseMs, 0.5f, 30000.0f),
        ParameterInfo::kCanAutomate, kReleaseId);

    auto* filterType =
        new StringListParameter (STR16 ("Filter Type"), kFilterTypeId, nullptr);
    for (const auto* name : {"Low-pass", "High-pass", "Band-pass", "Notch"})
        appendAscii (*filterType, name);
    parameters.addParameter (filterType);
    parameters.addParameter (
        STR16 ("Filter Cutoff"), STR16 ("Hz"), 0,
        logarithmicNormalized (defaultPatch.filterCutoffHz, 20.0f, 20000.0f),
        ParameterInfo::kCanAutomate, kFilterCutoffId);
    parameters.addParameter (
        STR16 ("Filter Resonance"), STR16 ("%"), 0, defaultPatch.filterResonance,
        ParameterInfo::kCanAutomate, kFilterResonanceId);
    parameters.addParameter (
        STR16 ("Filter Envelope"), STR16 ("%"), 0,
        (defaultPatch.filterEnvelope + 1.0) * 0.5,
        ParameterInfo::kCanAutomate, kFilterEnvelopeId);
    parameters.addParameter (
        STR16 ("Unison Detune"), STR16 ("cent"), 0, defaultPatch.detuneCents / 100.0,
        ParameterInfo::kCanAutomate, kDetuneId);
    parameters.addParameter (
        STR16 ("Unison Voices"), STR16 ("voices"), 15,
        (static_cast<ParamValue> (defaultPatch.unisonVoices) - 1.0) / 15.0,
        ParameterInfo::kCanAutomate, kUnisonId);
    parameters.addParameter (
        STR16 ("Patch Vibrato Rate"), STR16 ("Hz"), 0,
        defaultPatch.vibratoRateHz / 15.0,
        ParameterInfo::kCanAutomate, kPatchVibratoRateId);
    parameters.addParameter (
        STR16 ("Patch Vibrato Depth"), STR16 ("st"), 0,
        defaultPatch.vibratoDepthSemitones / 2.0,
        ParameterInfo::kCanAutomate, kPatchVibratoDepthId);
    parameters.addParameter (
        STR16 ("Delay Time"), STR16 ("ms"), 0,
        logarithmicNormalized (defaultPatch.delayTimeMs, 1.0f, 2500.0f),
        ParameterInfo::kCanAutomate, kDelayTimeId);
    return kResultOk;
}

tresult PLUGIN_API Controller::setComponentState (IBStream* state)
{
    if (!state)
        return kResultFalse;
    IBStreamer streamer (state, kLittleEndian);
    double value = 0.0;
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (kMasterGainId, value);
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (kVibratoDepthId, value);
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (kExpressionId, value);
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (kBrightnessId, value);
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (kReverbMixId, value);
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (kDelayMixId, value);
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (kChorusMixId, value);
    uint32 program = 0;
    if (streamer.readInt32u (program))
    {
        setParamNormalized (
            kSoundProgramId,
            static_cast<ParamValue> (program % kPresetCount) /
                static_cast<ParamValue> (kPresetCount - 1));
    }

    uint32 discrete = 0;
    if (!streamer.readInt32u (discrete))
        return kResultOk;
    setParamNormalized (kWaveformAId, static_cast<ParamValue> (discrete % 10) / 9.0);
    if (!streamer.readInt32u (discrete))
        return kResultFalse;
    setParamNormalized (kWaveformBId, static_cast<ParamValue> (discrete % 10) / 9.0);
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (kWaveformMixId, value);
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (
        kAttackId, logarithmicNormalized (static_cast<float> (value), 0.5f, 20000.0f));
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (
        kDecayId, logarithmicNormalized (static_cast<float> (value), 0.5f, 20000.0f));
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (kSustainId, value);
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (
        kReleaseId, logarithmicNormalized (static_cast<float> (value), 0.5f, 30000.0f));
    if (!streamer.readInt32u (discrete))
        return kResultFalse;
    setParamNormalized (kFilterTypeId, static_cast<ParamValue> (discrete % 4) / 3.0);
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (
        kFilterCutoffId,
        logarithmicNormalized (static_cast<float> (value), 20.0f, 20000.0f));
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (kFilterResonanceId, value);
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (kFilterEnvelopeId, (value + 1.0) * 0.5);
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (kDetuneId, value / 100.0);
    if (!streamer.readInt32u (discrete))
        return kResultFalse;
    setParamNormalized (
        kUnisonId,
        (static_cast<ParamValue> (std::clamp<uint32> (discrete, 1, 16)) - 1.0) / 15.0);
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (kPatchVibratoRateId, value / 15.0);
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (kPatchVibratoDepthId, value / 2.0);
    if (!streamer.readDouble (value))
        return kResultFalse;
    setParamNormalized (
        kDelayTimeId,
        logarithmicNormalized (static_cast<float> (value), 1.0f, 2500.0f));
    return kResultOk;
}

} // namespace Steinberg::Vst::SammyBlaze
