#include "processor.h"

#include "base/source/fstreamer.h"
#include "ids.h"
#include "pluginterfaces/vst/ivstevents.h"
#include "pluginterfaces/vst/ivstparameterchanges.h"
#include "sammyblaze/audio_core/presets.h"

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace Steinberg::Vst::SammyBlaze {
namespace Core = ::SammyBlaze::AudioCore;

Processor::Processor ()
{
    setControllerClass (FUID::fromTUID (ControllerUID));
}

tresult PLUGIN_API Processor::initialize (FUnknown* context)
{
    const auto result = AudioEffect::initialize (context);
    if (result != kResultOk)
        return result;
    addAudioOutput (STR16 ("Stereo Out"), SpeakerArr::kStereo);
    addEventInput (STR16 ("MIDI In"), 16);
    addEventOutput (STR16 ("Generated MIDI"), 16);
    engine.programChange (0);
    bridge.start ();
    return kResultOk;
}

tresult PLUGIN_API Processor::terminate ()
{
    bridge.stop ();
    engine.panic ();
    return AudioEffect::terminate ();
}

tresult PLUGIN_API Processor::setBusArrangements (
    SpeakerArrangement* inputs,
    int32 numIns,
    SpeakerArrangement* outputs,
    int32 numOuts)
{
    if (numIns == 0 && numOuts == 1 && outputs[0] == SpeakerArr::kStereo)
        return AudioEffect::setBusArrangements (inputs, numIns, outputs, numOuts);
    return kResultFalse;
}

tresult PLUGIN_API Processor::canProcessSampleSize (int32 symbolicSampleSize)
{
    return symbolicSampleSize == kSample32 ? kResultTrue : kResultFalse;
}

tresult PLUGIN_API Processor::setupProcessing (ProcessSetup& setup)
{
    const auto result = AudioEffect::setupProcessing (setup);
    if (result != kResultOk)
        return result;
    const auto sampleRate = setup.sampleRate > 0.0 ? setup.sampleRate : 44100.0;
    const auto maximumBlockSize = static_cast<std::uint32_t> (
        std::max<int32> (setup.maxSamplesPerBlock, 1));
    return engine.setup (sampleRate, maximumBlockSize)
               ? kResultOk
               : kResultFalse;
}

tresult PLUGIN_API Processor::setProcessing (TBool state)
{
    if (!state)
        engine.panic ();
    return AudioEffect::setProcessing (state);
}

tresult PLUGIN_API Processor::process (ProcessData& data)
{
    updateParameters (data.inputParameterChanges);
    handleBridge ();
    handleEvents (data.inputEvents, data.outputEvents);
    if (data.numOutputs == 0 || data.numSamples <= 0)
        return kResultOk;

    auto** output = data.outputs[0].channelBuffers32;
    if (!output || !output[0] || !output[1])
        return kResultOk;

    if (!engine.renderPlanar (
            output[0],
            output[1],
            static_cast<std::uint32_t> (data.numSamples)))
    {
        std::fill_n (output[0], data.numSamples, 0.0f);
        std::fill_n (output[1], data.numSamples, 0.0f);
    }
    return kResultOk;
}

void Processor::handleBridge ()
{
    BridgeMessage message {};
    while (bridge.pop (message))
    {
        switch (message.type)
        {
            case BridgeMessageType::noteOn:
                engine.noteOn (
                    message.data1,
                    static_cast<float> (message.data2) / 127.0f);
                break;
            case BridgeMessageType::noteOff:
                engine.noteOff (message.data1);
                break;
            case BridgeMessageType::controlChange:
                engine.controlChange (message.data1, message.data2);
                break;
            case BridgeMessageType::panic:
                engine.panic ();
                break;
            case BridgeMessageType::programChange:
                engine.programChange (message.data1);
                break;
            case BridgeMessageType::soundParameter:
                engine.applySoundParameter (message.data1, message.data2);
                break;
        }
    }
}

void Processor::handleEvents (IEventList* input, IEventList* output)
{
    if (!input)
        return;
    Event event {};
    for (int32 index = 0; index < input->getEventCount (); ++index)
    {
        if (input->getEvent (index, event) != kResultOk)
            continue;
        if (event.type == Event::kNoteOnEvent &&
            event.noteOn.pitch >= 0 && event.noteOn.pitch <= 127)
        {
            engine.noteOn (
                static_cast<std::uint8_t> (event.noteOn.pitch),
                event.noteOn.velocity);
        }
        else if (
            event.type == Event::kNoteOffEvent &&
            event.noteOff.pitch >= 0 && event.noteOff.pitch <= 127)
        {
            engine.noteOff (
                static_cast<std::uint8_t> (event.noteOff.pitch));
        }
        if (output)
            output->addEvent (event);
    }
}

void Processor::updateParameters (IParameterChanges* changes)
{
    if (!changes)
        return;
    for (int32 index = 0; index < changes->getParameterCount (); ++index)
    {
        auto* queue = changes->getParameterData (index);
        if (!queue || queue->getPointCount () == 0)
            continue;
        int32 sampleOffset = 0;
        ParamValue value = 0.0;
        if (queue->getPoint (
                queue->getPointCount () - 1,
                sampleOffset,
                value) != kResultOk)
            continue;
        const auto byteValue = static_cast<std::uint8_t> (
            std::clamp (std::lround (value * 127.0), 0L, 127L));
        switch (queue->getParameterId ())
        {
            case kMasterGainId:
                engine.applySoundParameter (0, byteValue);
                break;
            case kVibratoDepthId:
                engine.setVibratoDepth (static_cast<float> (value));
                break;
            case kExpressionId:
                engine.setExpression (static_cast<float> (value));
                break;
            case kBrightnessId:
                engine.applySoundParameter (20, byteValue);
                break;
            case kReverbMixId:
                engine.applySoundParameter (16, byteValue);
                break;
            case kDelayMixId:
                engine.applySoundParameter (17, byteValue);
                break;
            case kChorusMixId:
                engine.applySoundParameter (19, byteValue);
                break;
            case kSoundProgramId:
                engine.programChange (static_cast<std::uint8_t> (
                    std::clamp (
                        std::lround (
                            value *
                            static_cast<ParamValue> (
                                Core::kPresetCount - 1)),
                        0L,
                        static_cast<long> (Core::kPresetCount - 1))));
                break;
            case kWaveformAId:
                engine.applySoundParameter (1, byteValue);
                break;
            case kWaveformBId:
                engine.applySoundParameter (2, byteValue);
                break;
            case kWaveformMixId:
                engine.applySoundParameter (3, byteValue);
                break;
            case kAttackId:
                engine.applySoundParameter (4, byteValue);
                break;
            case kDecayId:
                engine.applySoundParameter (5, byteValue);
                break;
            case kSustainId:
                engine.applySoundParameter (6, byteValue);
                break;
            case kReleaseId:
                engine.applySoundParameter (7, byteValue);
                break;
            case kFilterTypeId:
                engine.applySoundParameter (8, byteValue);
                break;
            case kFilterCutoffId:
                engine.applySoundParameter (9, byteValue);
                break;
            case kFilterResonanceId:
                engine.applySoundParameter (10, byteValue);
                break;
            case kFilterEnvelopeId:
                engine.applySoundParameter (11, byteValue);
                break;
            case kDetuneId:
                engine.applySoundParameter (12, byteValue);
                break;
            case kUnisonId:
                engine.applySoundParameter (13, byteValue);
                break;
            case kPatchVibratoRateId:
                engine.applySoundParameter (14, byteValue);
                break;
            case kPatchVibratoDepthId:
                engine.applySoundParameter (15, byteValue);
                break;
            case kDelayTimeId:
                engine.applySoundParameter (18, byteValue);
                break;
            default: break;
        }
    }
}

tresult PLUGIN_API Processor::setState (IBStream* state)
{
    if (!state)
        return kResultFalse;
    IBStreamer streamer (state, kLittleEndian);
    double masterGain = 0.75;
    double vibratoDepth = 0.25;
    double expression = 1.0;
    double brightness = 0.5;
    double reverbMix = 0.05;
    double delayMix = 0.05;
    double chorusMix = 0.20;
    if (!streamer.readDouble (masterGain) ||
        !streamer.readDouble (vibratoDepth) ||
        !streamer.readDouble (expression) ||
        !streamer.readDouble (brightness) ||
        !streamer.readDouble (reverbMix) ||
        !streamer.readDouble (delayMix) ||
        !streamer.readDouble (chorusMix))
        return kResultFalse;

    engine.setMasterGain (static_cast<float> (masterGain));
    engine.setVibratoDepth (static_cast<float> (vibratoDepth));
    engine.setExpression (static_cast<float> (expression));
    engine.setBrightness (static_cast<float> (brightness));
    engine.setReverbMix (static_cast<float> (reverbMix));
    engine.setDelayMix (static_cast<float> (delayMix));
    engine.setChorusMix (static_cast<float> (chorusMix));

    uint32 program = 0;
    if (streamer.readInt32u (program))
    {
        engine.programChange (
            static_cast<std::uint8_t> (program % Core::kPresetCount));
        engine.setReverbMix (static_cast<float> (reverbMix));
        engine.setDelayMix (static_cast<float> (delayMix));
        engine.setChorusMix (static_cast<float> (chorusMix));
    }

    auto patch = engine.currentPreset ();
    patch.reverbMix = static_cast<float> (reverbMix);
    patch.delayMix = static_cast<float> (delayMix);
    patch.chorusMix = static_cast<float> (chorusMix);
    uint32 discrete = 0;
    double patchValue = 0.0;
    if (!streamer.readInt32u (discrete))
        return kResultOk;
    patch.waveformA =
        static_cast<Core::Waveform> (std::min<uint32> (discrete, 9));
    if (!streamer.readInt32u (discrete))
        return kResultFalse;
    patch.waveformB =
        static_cast<Core::Waveform> (std::min<uint32> (discrete, 9));
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    patch.waveformMix = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    patch.attackMs = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    patch.decayMs = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    patch.sustain = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    patch.releaseMs = static_cast<float> (patchValue);
    if (!streamer.readInt32u (discrete))
        return kResultFalse;
    patch.filterType =
        static_cast<Core::FilterType> (std::min<uint32> (discrete, 3));
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    patch.filterCutoffHz = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    patch.filterResonance = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    patch.filterEnvelope = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    patch.detuneCents = static_cast<float> (patchValue);
    if (!streamer.readInt32u (discrete))
        return kResultFalse;
    patch.unisonVoices = static_cast<std::uint8_t> (
        std::clamp<uint32> (discrete, 1, 16));
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    patch.vibratoRateHz = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    patch.vibratoDepthSemitones = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    patch.delayTimeMs = static_cast<float> (patchValue);
    return engine.applyPatch (
               patch,
               static_cast<float> (masterGain),
               static_cast<float> (brightness))
               ? kResultOk
               : kResultFalse;
}

tresult PLUGIN_API Processor::getState (IBStream* state)
{
    if (!state)
        return kResultFalse;
    const auto& patch = engine.currentPreset ();
    IBStreamer streamer (state, kLittleEndian);
    return streamer.writeDouble (engine.masterGain ()) &&
                   streamer.writeDouble (engine.vibratoDepth ()) &&
                   streamer.writeDouble (engine.expression ()) &&
                   streamer.writeDouble (engine.brightness ()) &&
                   streamer.writeDouble (engine.reverbMix ()) &&
                   streamer.writeDouble (engine.delayMix ()) &&
                   streamer.writeDouble (engine.chorusMix ()) &&
                   streamer.writeInt32u (patch.program) &&
                   streamer.writeInt32u (
                       static_cast<uint32> (patch.waveformA)) &&
                   streamer.writeInt32u (
                       static_cast<uint32> (patch.waveformB)) &&
                   streamer.writeDouble (patch.waveformMix) &&
                   streamer.writeDouble (patch.attackMs) &&
                   streamer.writeDouble (patch.decayMs) &&
                   streamer.writeDouble (patch.sustain) &&
                   streamer.writeDouble (patch.releaseMs) &&
                   streamer.writeInt32u (
                       static_cast<uint32> (patch.filterType)) &&
                   streamer.writeDouble (patch.filterCutoffHz) &&
                   streamer.writeDouble (patch.filterResonance) &&
                   streamer.writeDouble (patch.filterEnvelope) &&
                   streamer.writeDouble (patch.detuneCents) &&
                   streamer.writeInt32u (patch.unisonVoices) &&
                   streamer.writeDouble (patch.vibratoRateHz) &&
                   streamer.writeDouble (patch.vibratoDepthSemitones) &&
                   streamer.writeDouble (patch.delayTimeMs)
               ? kResultOk
               : kResultFalse;
}

} // namespace Steinberg::Vst::SammyBlaze
