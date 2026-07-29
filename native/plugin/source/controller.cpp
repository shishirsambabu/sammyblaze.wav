#include "controller.h"

#include "base/source/fstreamer.h"
#include "ids.h"
#include "pluginterfaces/base/ustring.h"
#include "presets.h"
#include "public.sdk/source/vst/vstparameters.h"

namespace Steinberg::Vst::SammyBlaze {

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

    auto* sound = new StringListParameter (
        STR16 ("Factory Sound"),
        kSoundProgramId,
        nullptr,
        ParameterInfo::kCanAutomate | ParameterInfo::kIsList |
            ParameterInfo::kIsProgramChange);
    for (std::size_t program = 0; program < kPresetCount; ++program)
    {
        String128 label {};
        UString (label, 128).fromAscii (presetName (program));
        sound->appendString (label);
    }
    parameters.addParameter (sound);
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
    return kResultOk;
}

} // namespace Steinberg::Vst::SammyBlaze
