#pragma once

#include "pluginterfaces/base/funknown.h"

namespace Steinberg::Vst::SammyBlaze {

enum ParameterIds : Steinberg::Vst::ParamID
{
    kMasterGainId = 100,
    kVibratoDepthId = 101,
    kExpressionId = 102,
    kBrightnessId = 103,
    kReverbMixId = 104,
    kDelayMixId = 105,
    kChorusMixId = 106,
    kSoundProgramId = 107,
};

static DECLARE_UID (
    ProcessorUID, 0x53424C5A, 0xA47E4F11, 0x9D8A7461, 0x22F3B401);
static DECLARE_UID (
    ControllerUID, 0x53424C5A, 0xC8D744A0, 0xB18E6B37, 0x9310F5D2);

} // namespace Steinberg::Vst::SammyBlaze
