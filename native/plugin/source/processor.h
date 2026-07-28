#pragma once

#include "bridge.h"
#include "public.sdk/source/vst/vstaudioeffect.h"

#include <array>
#include <vector>

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
    struct Voice
    {
        int16 pitch {-1};
        double phase {0.0};
        float velocity {0.0f};
        bool keyDown {false};
        bool active {false};
    };

    void handleBridge ();
    void handleEvents (IEventList* input, IEventList* output);
    void updateParameters (IParameterChanges* changes);
    void noteOn (int16 pitch, float velocity);
    void noteOff (int16 pitch);
    void setSustain (bool enabled);
    void resetVoices ();

    GestureBridgeReceiver bridge;
    std::array<Voice, 16> voices {};
    ParamValue masterGain {0.75};
    ParamValue vibratoDepth {0.25};
    ParamValue expression {1.0};
    ParamValue brightness {0.5};
    ParamValue reverbMix {0.15};
    ParamValue delayMix {0.12};
    ParamValue chorusMix {0.08};
    ParamValue smoothedMasterGain {0.75};
    ParamValue smoothedExpression {1.0};
    ParamValue smoothedBrightness {0.5};
    ParamValue smoothedReverbMix {0.15};
    ParamValue smoothedDelayMix {0.12};
    ParamValue smoothedChorusMix {0.08};
    std::vector<float> effectBuffer;
    std::size_t effectWriteIndex {0};
    bool sustainEnabled {false};
    double lfoPhase {0.0};
};

} // namespace Steinberg::Vst::SammyBlaze
