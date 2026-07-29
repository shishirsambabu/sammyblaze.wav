#include "controller.h"
#include "ids.h"
#include "processor.h"
#include "version.h"

#include "public.sdk/source/main/pluginfactory_constexpr.h"

#define stringPluginName "SammyBlaze"

BEGIN_FACTORY_DEF (stringCompanyName, stringCompanyWeb, stringCompanyEmail, 2)

DEF_CLASS (
    Steinberg::Vst::SammyBlaze::ProcessorUID,
    Steinberg::PClassInfo::kManyInstances,
    kVstAudioEffectClass,
    stringPluginName,
    Steinberg::Vst::kDistributable,
    "Instrument|Synth",
    FULL_VERSION_STR,
    kVstVersionString,
    Steinberg::Vst::SammyBlaze::Processor::createInstance,
    nullptr)

DEF_CLASS (
    Steinberg::Vst::SammyBlaze::ControllerUID,
    Steinberg::PClassInfo::kManyInstances,
    kVstComponentControllerClass,
    stringPluginName "Controller",
    0,
    "",
    FULL_VERSION_STR,
    kVstVersionString,
    Steinberg::Vst::SammyBlaze::Controller::createInstance,
    nullptr)

END_FACTORY
