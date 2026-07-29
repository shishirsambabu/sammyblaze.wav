#pragma once

#include "bridge.h"
#include "presets.h"
#include "public.sdk/source/vst/vstaudioeffect.h"

#include <array>
#include <cstdint>
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
    enum class EnvelopeStage : std::uint8_t
    {
        off,
        attack,
        decay,
        sustain,
        release,
    };

    struct Voice
    {
        int16 pitch {-1};
        std::array<double, 3> phaseA {};
        std::array<double, 3> phaseB {};
        float velocity {0.0f};
        float envelope {0.0f};
        float releaseStep {0.0f};
        float filterLow {0.0f};
        float filterBand {0.0f};
        std::uint32_t noiseState {1};
        std::uint64_t age {0};
        SynthPreset preset {};
        EnvelopeStage stage {EnvelopeStage::off};
        bool keyDown {false};
        bool active {false};
    };

    void handleBridge ();
    void handleEvents (IEventList* input, IEventList* output);
    void updateParameters (IParameterChanges* changes);
    void applyPreset (std::uint8_t program);
    void noteOn (int16 pitch, float velocity);
    void noteOff (int16 pitch);
    void beginRelease (Voice& voice);
    void setSustain (bool enabled);
    void resetVoices ();
    float renderVoice (Voice& voice, double sampleRate);

    GestureBridgeReceiver bridge;
    std::array<Voice, 24> voices {};
    SynthPreset currentPreset {presetForProgram (0)};
    ParamValue masterGain {0.75};
    ParamValue vibratoDepth {0.25};
    ParamValue expression {1.0};
    ParamValue brightness {0.5};
    ParamValue reverbMix {0.05};
    ParamValue delayMix {0.05};
    ParamValue chorusMix {0.20};
    ParamValue smoothedMasterGain {0.75};
    ParamValue smoothedExpression {1.0};
    ParamValue smoothedBrightness {0.5};
    ParamValue smoothedReverbMix {0.05};
    ParamValue smoothedDelayMix {0.05};
    ParamValue smoothedChorusMix {0.20};
    std::vector<float> effectBuffer;
    std::size_t effectWriteIndex {0};
    std::uint64_t voiceAge {0};
    bool sustainEnabled {false};
    double lfoPhase {0.0};
};

} // namespace Steinberg::Vst::SammyBlaze
