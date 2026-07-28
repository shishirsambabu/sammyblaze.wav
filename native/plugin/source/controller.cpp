#include "controller.h"

#include "base/source/fstreamer.h"
#include "ids.h"

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
        STR16 ("Reverb Mix"), STR16 ("%"), 0, 0.15, ParameterInfo::kCanAutomate, kReverbMixId);
    parameters.addParameter (
        STR16 ("Delay Mix"), STR16 ("%"), 0, 0.12, ParameterInfo::kCanAutomate, kDelayMixId);
    parameters.addParameter (
        STR16 ("Chorus Mix"), STR16 ("%"), 0, 0.08, ParameterInfo::kCanAutomate, kChorusMixId);
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
    return kResultOk;
}

} // namespace Steinberg::Vst::SammyBlaze
