#pragma once

#include "bridge.h"
#include "sammyblaze/audio_core/synth_engine.h"
#include "public.sdk/source/vst/vstaudioeffect.h"

#include <cstdint>

namespace Steinberg::Vst::SammyBlaze {

class Processor final : public AudioEffect
{
public:
    Processor ();

    static FUnknown* createInstance (void*)
    {
        return static_cast<IAudioProcessor*> (new Processor);
    }

    tresult PLUGIN_API initialize (FUnknown* context) SMTG_OVERRIDE;
    tresult PLUGIN_API terminate () SMTG_OVERRIDE;
    tresult PLUGIN_API setBusArrangements (
        SpeakerArrangement* inputs,
        int32 numIns,
        SpeakerArrangement* outputs,
        int32 numOuts) SMTG_OVERRIDE;
    tresult PLUGIN_API canProcessSampleSize (int32 symbolicSampleSize) SMTG_OVERRIDE;
    tresult PLUGIN_API setupProcessing (ProcessSetup& setup) SMTG_OVERRIDE;
    tresult PLUGIN_API setProcessing (TBool state) SMTG_OVERRIDE;
    tresult PLUGIN_API process (ProcessData& data) SMTG_OVERRIDE;
    tresult PLUGIN_API setState (IBStream* state) SMTG_OVERRIDE;
    tresult PLUGIN_API getState (IBStream* state) SMTG_OVERRIDE;

private:
    void handleBridge ();
    void applyParameter (ParamID parameter, ParamValue value) noexcept;

    GestureBridgeReceiver bridge;
    ::SammyBlaze::AudioCore::SynthEngine engine;
};

} // namespace Steinberg::Vst::SammyBlaze
