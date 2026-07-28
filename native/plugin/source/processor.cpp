#include "processor.h"

#include "base/source/fstreamer.h"
#include "ids.h"
#include "pluginterfaces/vst/ivstevents.h"
#include "pluginterfaces/vst/ivstparameterchanges.h"

#include <algorithm>
#include <cmath>

namespace Steinberg::Vst::SammyBlaze {
namespace {
constexpr double twoPi = 6.28318530717958647692;
}

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
    bridge.start ();
    return kResultOk;
}

tresult PLUGIN_API Processor::terminate ()
{
    bridge.stop ();
    resetVoices ();
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
    effectBuffer.assign (
        static_cast<std::size_t> (std::ceil (sampleRate * 2.0)),
        0.0f);
    effectWriteIndex = 0;
    return kResultOk;
}

tresult PLUGIN_API Processor::setProcessing (TBool state)
{
    if (!state)
        resetVoices ();
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
    if (!output)
        return kResultOk;
    std::fill_n (output[0], data.numSamples, 0.0f);
    std::fill_n (output[1], data.numSamples, 0.0f);

    const auto sampleRate = processSetup.sampleRate > 0.0 ? processSetup.sampleRate : 44100.0;
    const auto smoothing = 1.0 - std::exp (-1.0 / (sampleRate * 0.015));
    const auto bufferSize = effectBuffer.size ();
    const auto delaySamples = static_cast<std::size_t> (sampleRate * 0.34);
    const auto reverbSamplesA = static_cast<std::size_t> (sampleRate * 0.061);
    const auto reverbSamplesB = static_cast<std::size_t> (sampleRate * 0.089);
    for (int32 sample = 0; sample < data.numSamples; ++sample)
    {
        smoothedMasterGain += (masterGain - smoothedMasterGain) * smoothing;
        smoothedExpression += (expression - smoothedExpression) * smoothing;
        smoothedBrightness += (brightness - smoothedBrightness) * smoothing;
        smoothedReverbMix += (reverbMix - smoothedReverbMix) * smoothing;
        smoothedDelayMix += (delayMix - smoothedDelayMix) * smoothing;
        smoothedChorusMix += (chorusMix - smoothedChorusMix) * smoothing;
        const auto vibrato = std::sin (lfoPhase) * vibratoDepth * 40.0;
        float mixed = 0.0f;
        for (auto& voice : voices)
        {
            if (!voice.active)
                continue;
            const auto semitones = static_cast<double> (voice.pitch) - 69.0 + vibrato / 100.0;
            const auto frequency = 440.0 * std::pow (2.0, semitones / 12.0);
            voice.phase += twoPi * frequency / sampleRate;
            if (voice.phase >= twoPi)
                voice.phase -= twoPi;
            const auto fundamental = std::sin (voice.phase);
            const auto harmonic =
                std::sin (voice.phase * 2.0) * smoothedBrightness * 0.22;
            mixed += static_cast<float> ((fundamental + harmonic) * voice.velocity);
        }
        lfoPhase += twoPi * 5.0 / sampleRate;
        if (lfoPhase >= twoPi)
            lfoPhase -= twoPi;
        mixed *= static_cast<float> (smoothedMasterGain * smoothedExpression * 0.11);

        float left = mixed;
        float right = mixed;
        if (bufferSize > delaySamples + 1)
        {
            const auto tap = [this, bufferSize] (std::size_t samplesBack) {
                return effectBuffer[
                    (effectWriteIndex + bufferSize - samplesBack) % bufferSize];
            };
            const auto delayTap = tap (delaySamples);
            const auto reverbA = tap (reverbSamplesA);
            const auto reverbB = tap (reverbSamplesB);
            const auto chorusMod =
                static_cast<std::size_t> (
                    sampleRate * (0.018 + 0.005 * (0.5 + 0.5 * std::sin (lfoPhase * 0.73))));
            const auto chorusTap = tap (chorusMod);
            effectBuffer[effectWriteIndex] = std::clamp (
                mixed + delayTap * static_cast<float> (smoothedDelayMix * 0.42) +
                    (reverbA + reverbB) *
                        static_cast<float> (smoothedReverbMix * 0.24),
                -2.0f,
                2.0f);
            effectWriteIndex = (effectWriteIndex + 1) % bufferSize;

            left += delayTap * static_cast<float> (smoothedDelayMix * 0.62);
            right += delayTap * static_cast<float> (smoothedDelayMix * 0.48);
            left += reverbA * static_cast<float> (smoothedReverbMix * 0.48);
            right += reverbB * static_cast<float> (smoothedReverbMix * 0.48);
            left += chorusTap * static_cast<float> (smoothedChorusMix * 0.34);
            right -= chorusTap * static_cast<float> (smoothedChorusMix * 0.28);
        }
        output[0][sample] = std::clamp (left, -1.0f, 1.0f);
        output[1][sample] = std::clamp (right, -1.0f, 1.0f);
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
                noteOn (
                    static_cast<int16> (message.data1),
                    static_cast<float> (message.data2) / 127.0f);
                break;
            case BridgeMessageType::noteOff:
                noteOff (static_cast<int16> (message.data1));
                break;
            case BridgeMessageType::controlChange:
            {
                const auto normalized = static_cast<ParamValue> (message.data2) / 127.0;
                switch (message.data1)
                {
                    case 1: vibratoDepth = normalized; break;
                    case 7: masterGain = normalized; break;
                    case 11: expression = normalized; break;
                    case 64: setSustain (message.data2 >= 64); break;
                    case 74: brightness = normalized; break;
                    case 91: reverbMix = normalized; break;
                    case 93: chorusMix = normalized; break;
                    case 94: delayMix = normalized; break;
                    case 120:
                    case 123: resetVoices (); break;
                    default: break;
                }
                break;
            }
            case BridgeMessageType::panic: resetVoices (); break;
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
        if (event.type == Event::kNoteOnEvent)
            noteOn (event.noteOn.pitch, event.noteOn.velocity);
        else if (event.type == Event::kNoteOffEvent)
            noteOff (event.noteOff.pitch);
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
        if (queue->getPoint (queue->getPointCount () - 1, sampleOffset, value) != kResultOk)
            continue;
        switch (queue->getParameterId ())
        {
            case kMasterGainId: masterGain = value; break;
            case kVibratoDepthId: vibratoDepth = value; break;
            case kExpressionId: expression = value; break;
            case kBrightnessId: brightness = value; break;
            case kReverbMixId: reverbMix = value; break;
            case kDelayMixId: delayMix = value; break;
            case kChorusMixId: chorusMix = value; break;
            default: break;
        }
    }
}

void Processor::noteOn (int16 pitch, float velocity)
{
    auto voice = std::find_if (voices.begin (), voices.end (), [] (const Voice& candidate) {
        return !candidate.active;
    });
    if (voice == voices.end ())
        voice = voices.begin ();
    voice->pitch = pitch;
    voice->velocity = std::clamp (velocity, 0.0f, 1.0f);
    voice->phase = 0.0;
    voice->keyDown = true;
    voice->active = true;
}

void Processor::noteOff (int16 pitch)
{
    for (auto& voice : voices)
    {
        if (voice.active && voice.pitch == pitch)
        {
            voice.keyDown = false;
            if (!sustainEnabled)
                voice.active = false;
        }
    }
}

void Processor::setSustain (bool enabled)
{
    if (sustainEnabled == enabled)
        return;
    sustainEnabled = enabled;
    if (!sustainEnabled)
    {
        for (auto& voice : voices)
        {
            if (voice.active && !voice.keyDown)
                voice.active = false;
        }
    }
}

void Processor::resetVoices ()
{
    for (auto& voice : voices)
        voice = {};
    sustainEnabled = false;
    lfoPhase = 0.0;
    std::fill (effectBuffer.begin (), effectBuffer.end (), 0.0f);
    effectWriteIndex = 0;
}

tresult PLUGIN_API Processor::setState (IBStream* state)
{
    if (!state)
        return kResultFalse;
    IBStreamer streamer (state, kLittleEndian);
    return streamer.readDouble (masterGain) &&
                   streamer.readDouble (vibratoDepth) &&
                   streamer.readDouble (expression) &&
                   streamer.readDouble (brightness) &&
                   streamer.readDouble (reverbMix) &&
                   streamer.readDouble (delayMix) &&
                   streamer.readDouble (chorusMix)
               ? kResultOk
               : kResultFalse;
}

tresult PLUGIN_API Processor::getState (IBStream* state)
{
    if (!state)
        return kResultFalse;
    IBStreamer streamer (state, kLittleEndian);
    return streamer.writeDouble (masterGain) &&
                   streamer.writeDouble (vibratoDepth) &&
                   streamer.writeDouble (expression) &&
                   streamer.writeDouble (brightness) &&
                   streamer.writeDouble (reverbMix) &&
                   streamer.writeDouble (delayMix) &&
                   streamer.writeDouble (chorusMix)
               ? kResultOk
               : kResultFalse;
}

} // namespace Steinberg::Vst::SammyBlaze
