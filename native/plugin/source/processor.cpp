#include "processor.h"

#include "base/source/fstreamer.h"
#include "ids.h"
#include "pluginterfaces/vst/ivstevents.h"
#include "pluginterfaces/vst/ivstparameterchanges.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace Steinberg::Vst::SammyBlaze {
namespace {

constexpr double twoPi = 6.28318530717958647692;
constexpr float minimumEnvelopeTimeMs = 0.5f;

float linearValue (float normalized, float minimum, float maximum) noexcept
{
    return minimum + (maximum - minimum) * normalized;
}

float logarithmicValue (float normalized, float minimum, float maximum) noexcept
{
    return minimum * std::pow (maximum / minimum, normalized);
}

double wrapPhase (double phase) noexcept
{
    phase -= std::floor (phase);
    return phase;
}

float polyBlep (double phase, double increment) noexcept
{
    if (increment <= 0.0)
        return 0.0f;
    if (phase < increment)
    {
        const auto t = phase / increment;
        return static_cast<float> (t + t - t * t - 1.0);
    }
    if (phase > 1.0 - increment)
    {
        const auto t = (phase - 1.0) / increment;
        return static_cast<float> (t * t + t + t + 1.0);
    }
    return 0.0f;
}

float randomBipolar (std::uint32_t& state) noexcept
{
    state = state * 1664525U + 1013904223U;
    return static_cast<float> ((state >> 8U) & 0x00FFFFFFU) /
               static_cast<float> (0x007FFFFFU) -
           1.0f;
}

float waveformSample (
    Waveform waveform,
    double phase,
    double increment,
    std::uint32_t& noiseState) noexcept
{
    const auto angle = phase * twoPi;
    switch (waveform)
    {
        case Waveform::sine:
            return static_cast<float> (std::sin (angle));
        case Waveform::triangle:
            return static_cast<float> ((2.0 / 3.14159265358979323846) *
                                       std::asin (std::sin (angle)));
        case Waveform::saw:
            return static_cast<float> (phase * 2.0 - 1.0) -
                   polyBlep (phase, increment);
        case Waveform::square:
        {
            auto value = phase < 0.5 ? 1.0f : -1.0f;
            value += polyBlep (phase, increment);
            value -= polyBlep (wrapPhase (phase + 0.5), increment);
            return value;
        }
        case Waveform::pulse:
        {
            constexpr double duty = 0.28;
            auto value = phase < duty ? 1.0f : -1.0f;
            value += polyBlep (phase, increment);
            value -= polyBlep (wrapPhase (phase + 1.0 - duty), increment);
            return value;
        }
        case Waveform::organ:
            return static_cast<float> (
                std::sin (angle) * 0.68 + std::sin (angle * 2.0) * 0.22 +
                std::sin (angle * 3.0) * 0.10);
        case Waveform::metal:
            return static_cast<float> (
                std::sin (angle) * 0.52 + std::sin (angle * 2.41) * 0.30 +
                std::sin (angle * 5.31) * 0.18);
        case Waveform::noise:
            return randomBipolar (noiseState);
        case Waveform::vocal:
            return static_cast<float> (
                std::sin (angle) * 0.58 + std::sin (angle * 2.0) * 0.27 +
                std::sin (angle * 4.0) * 0.15);
        case Waveform::wavetable:
            return static_cast<float> (
                std::sin (angle) * 0.62 + std::sin (angle * 3.0) * 0.23 +
                (phase * 2.0 - 1.0) * 0.15);
    }
    return 0.0f;
}

} // namespace

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
    applyPreset (0);
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
        static_cast<std::size_t> (std::ceil (sampleRate * 2.6)),
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
    const auto requestedDelay = static_cast<std::size_t> (
        sampleRate * static_cast<double> (currentPreset.delayTimeMs) / 1000.0);
    const auto delaySamples =
        bufferSize > 1 ? std::clamp<std::size_t> (requestedDelay, 1, bufferSize - 1) : 0;
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

        float mixed = 0.0f;
        for (auto& voice : voices)
        {
            if (voice.active)
                mixed += renderVoice (voice, sampleRate);
        }
        lfoPhase = wrapPhase (
            lfoPhase + static_cast<double> (currentPreset.vibratoRateHz) / sampleRate);
        mixed *= static_cast<float> (smoothedMasterGain * smoothedExpression * 0.13);

        float left = mixed;
        float right = mixed;
        if (bufferSize > reverbSamplesB + 1 && delaySamples > 0)
        {
            const auto tap = [this, bufferSize] (std::size_t samplesBack) {
                return effectBuffer[
                    (effectWriteIndex + bufferSize - samplesBack) % bufferSize];
            };
            const auto delayTap = tap (delaySamples);
            const auto reverbA = tap (reverbSamplesA);
            const auto reverbB = tap (reverbSamplesB);
            const auto chorusMod = static_cast<std::size_t> (
                sampleRate *
                (0.018 + 0.005 * (0.5 + 0.5 * std::sin (lfoPhase * twoPi * 0.73))));
            const auto chorusTap = tap (std::max<std::size_t> (1, chorusMod));
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
        output[0][sample] = std::tanh (left * 1.15f) * 0.86f;
        output[1][sample] = std::tanh (right * 1.15f) * 0.86f;
    }
    return kResultOk;
}

float Processor::renderVoice (Voice& voice, double sampleRate)
{
    const auto& preset = voice.preset;
    switch (voice.stage)
    {
        case EnvelopeStage::attack:
        {
            const auto attack = std::max (preset.attackMs, minimumEnvelopeTimeMs);
            voice.envelope += static_cast<float> (1000.0 / (attack * sampleRate));
            if (voice.envelope >= 1.0f)
            {
                voice.envelope = 1.0f;
                voice.stage = EnvelopeStage::decay;
            }
            break;
        }
        case EnvelopeStage::decay:
        {
            const auto decay = std::max (preset.decayMs, minimumEnvelopeTimeMs);
            voice.envelope -= static_cast<float> (
                (1.0 - preset.sustain) * 1000.0 / (decay * sampleRate));
            if (voice.envelope <= preset.sustain)
            {
                voice.envelope = preset.sustain;
                voice.stage = EnvelopeStage::sustain;
            }
            break;
        }
        case EnvelopeStage::sustain: voice.envelope = preset.sustain; break;
        case EnvelopeStage::release:
            voice.envelope -= voice.releaseStep;
            if (voice.envelope <= 0.0001f)
            {
                voice = {};
                return 0.0f;
            }
            break;
        case EnvelopeStage::off:
            voice = {};
            return 0.0f;
    }

    const auto gestureVibrato = static_cast<double> (vibratoDepth) * 0.5;
    const auto vibratoSemitones =
        (static_cast<double> (preset.vibratoDepthSemitones) + gestureVibrato) *
        std::sin (lfoPhase * twoPi);
    const auto baseSemitones =
        static_cast<double> (voice.pitch) - 69.0 + vibratoSemitones;
    const auto unisonCount = std::clamp<int> (preset.unisonVoices, 1, 3);
    float oscillators = 0.0f;
    for (int unison = 0; unison < unisonCount; ++unison)
    {
        const auto center = static_cast<double> (unisonCount - 1) * 0.5;
        const auto detune =
            (static_cast<double> (unison) - center) *
            static_cast<double> (preset.detuneCents) /
            std::max (1.0, center) / 100.0;
        const auto frequency = 440.0 * std::pow (2.0, (baseSemitones + detune) / 12.0);
        const auto increment = std::min (frequency / sampleRate, 0.45);
        voice.phaseA[static_cast<std::size_t> (unison)] = wrapPhase (
            voice.phaseA[static_cast<std::size_t> (unison)] + increment);
        voice.phaseB[static_cast<std::size_t> (unison)] = wrapPhase (
            voice.phaseB[static_cast<std::size_t> (unison)] + increment * 1.001);
        const auto a = waveformSample (
            preset.waveformA,
            voice.phaseA[static_cast<std::size_t> (unison)],
            increment,
            voice.noiseState);
        const auto b = waveformSample (
            preset.waveformB,
            voice.phaseB[static_cast<std::size_t> (unison)],
            increment,
            voice.noiseState);
        oscillators += a * (1.0f - preset.waveformMix) + b * preset.waveformMix;
    }
    oscillators /= std::sqrt (static_cast<float> (unisonCount));
    oscillators *= voice.velocity * voice.envelope;

    const auto envelopeOctaves = preset.filterEnvelope * voice.envelope * 4.0f;
    const auto brightnessOctaves =
        static_cast<float> ((smoothedBrightness - 0.5) * 4.0);
    const auto cutoff = std::clamp (
        preset.filterCutoffHz * std::pow (2.0f, envelopeOctaves + brightnessOctaves),
        25.0f,
        static_cast<float> (sampleRate * 0.42));
    const auto coefficient = std::clamp (
        2.0f * std::sin (
                   3.14159265358979323846f * cutoff / static_cast<float> (sampleRate)),
        0.001f,
        0.95f);
    const auto damping = 1.95f - preset.filterResonance * 1.55f;
    voice.filterLow += coefficient * voice.filterBand;
    const auto high = oscillators - voice.filterLow - damping * voice.filterBand;
    voice.filterBand += coefficient * high;
    switch (preset.filterType)
    {
        case FilterType::lowpass: return voice.filterLow;
        case FilterType::highpass: return high;
        case FilterType::bandpass: return voice.filterBand;
        case FilterType::notch: return voice.filterLow + high;
    }
    return oscillators;
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
            case BridgeMessageType::programChange: applyPreset (message.data1); break;
            case BridgeMessageType::soundParameter:
                applySoundParameter (message.data1, message.data2);
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
            case kMasterGainId:
                applySoundParameter (0, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kVibratoDepthId: vibratoDepth = value; break;
            case kExpressionId: expression = value; break;
            case kBrightnessId:
                applySoundParameter (20, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kReverbMixId:
                applySoundParameter (16, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kDelayMixId:
                applySoundParameter (17, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kChorusMixId:
                applySoundParameter (19, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kSoundProgramId:
                applyPreset (static_cast<std::uint8_t> (
                    std::round (value * static_cast<ParamValue> (kPresetCount - 1))));
                break;
            case kWaveformAId:
                applySoundParameter (1, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kWaveformBId:
                applySoundParameter (2, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kWaveformMixId:
                applySoundParameter (3, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kAttackId:
                applySoundParameter (4, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kDecayId:
                applySoundParameter (5, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kSustainId:
                applySoundParameter (6, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kReleaseId:
                applySoundParameter (7, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kFilterTypeId:
                applySoundParameter (8, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kFilterCutoffId:
                applySoundParameter (9, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kFilterResonanceId:
                applySoundParameter (10, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kFilterEnvelopeId:
                applySoundParameter (11, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kDetuneId:
                applySoundParameter (12, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kUnisonId:
                applySoundParameter (13, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kPatchVibratoRateId:
                applySoundParameter (14, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kPatchVibratoDepthId:
                applySoundParameter (15, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            case kDelayTimeId:
                applySoundParameter (18, static_cast<std::uint8_t> (std::round (value * 127.0)));
                break;
            default: break;
        }
    }
}

void Processor::applyPreset (std::uint8_t program)
{
    const auto selected = presetForProgram (program);
    if (selected.program == currentPreset.program && currentPreset.name == selected.name)
        return;
    resetVoices ();
    currentPreset = selected;
    reverbMix = currentPreset.reverbMix;
    delayMix = currentPreset.delayMix;
    chorusMix = currentPreset.chorusMix;
}

void Processor::applySoundParameter (std::uint8_t parameter, std::uint8_t value)
{
    const auto normalized = static_cast<float> (value) / 127.0f;
    switch (parameter)
    {
        case 0: masterGain = normalized; break;
        case 1:
            currentPreset.waveformA =
                static_cast<Waveform> (std::clamp (std::lround (normalized * 9.0f), 0L, 9L));
            break;
        case 2:
            currentPreset.waveformB =
                static_cast<Waveform> (std::clamp (std::lround (normalized * 9.0f), 0L, 9L));
            break;
        case 3: currentPreset.waveformMix = normalized; break;
        case 4:
            currentPreset.attackMs =
                value == 0 ? 0.0f : logarithmicValue (normalized, 0.5f, 20000.0f);
            break;
        case 5:
            currentPreset.decayMs = logarithmicValue (normalized, 0.5f, 20000.0f);
            break;
        case 6: currentPreset.sustain = normalized; break;
        case 7:
            currentPreset.releaseMs =
                value == 0 ? 0.0f : logarithmicValue (normalized, 0.5f, 30000.0f);
            break;
        case 8:
            currentPreset.filterType =
                static_cast<FilterType> (
                    std::clamp (std::lround (normalized * 3.0f), 0L, 3L));
            break;
        case 9:
            currentPreset.filterCutoffHz =
                logarithmicValue (normalized, 20.0f, 20000.0f);
            break;
        case 10: currentPreset.filterResonance = normalized; break;
        case 11: currentPreset.filterEnvelope = linearValue (normalized, -1.0f, 1.0f); break;
        case 12: currentPreset.detuneCents = normalized * 100.0f; break;
        case 13:
            currentPreset.unisonVoices = static_cast<std::uint8_t> (
                std::clamp (std::lround (linearValue (normalized, 1.0f, 16.0f)), 1L, 16L));
            break;
        case 14: currentPreset.vibratoRateHz = normalized * 15.0f; break;
        case 15: currentPreset.vibratoDepthSemitones = normalized * 2.0f; break;
        case 16:
            currentPreset.reverbMix = normalized;
            reverbMix = normalized;
            break;
        case 17:
            currentPreset.delayMix = normalized;
            delayMix = normalized;
            break;
        case 18:
            currentPreset.delayTimeMs =
                logarithmicValue (normalized, 1.0f, 2500.0f);
            break;
        case 19:
            currentPreset.chorusMix = normalized;
            chorusMix = normalized;
            break;
        case 20: brightness = normalized; break;
        default: return;
    }
    for (auto& voice : voices)
    {
        if (voice.active)
            voice.preset = currentPreset;
    }
}

void Processor::noteOn (int16 pitch, float velocity)
{
    auto voice = std::find_if (voices.begin (), voices.end (), [] (const Voice& candidate) {
        return !candidate.active;
    });
    if (voice == voices.end ())
    {
        voice = std::min_element (
            voices.begin (),
            voices.end (),
            [] (const Voice& left, const Voice& right) {
                if (left.stage == EnvelopeStage::release &&
                    right.stage != EnvelopeStage::release)
                    return true;
                if (right.stage == EnvelopeStage::release &&
                    left.stage != EnvelopeStage::release)
                    return false;
                if (left.envelope != right.envelope)
                    return left.envelope < right.envelope;
                return left.age < right.age;
            });
    }
    *voice = {};
    voice->pitch = pitch;
    voice->velocity = std::clamp (velocity, 0.0f, 1.0f);
    voice->phaseB.fill (0.173);
    voice->keyDown = true;
    voice->active = true;
    voice->stage = EnvelopeStage::attack;
    voice->preset = currentPreset;
    voice->age = ++voiceAge;
    voice->noiseState =
        static_cast<std::uint32_t> (voiceAge * 747796405ULL + pitch * 2891336453ULL);
}

void Processor::beginRelease (Voice& voice)
{
    if (!voice.active || voice.stage == EnvelopeStage::release)
        return;
    const auto sampleRate = processSetup.sampleRate > 0.0 ? processSetup.sampleRate : 44100.0;
    const auto releaseSamples = std::max (
        1.0,
        static_cast<double> (std::max (voice.preset.releaseMs, minimumEnvelopeTimeMs)) *
            sampleRate / 1000.0);
    voice.releaseStep = voice.envelope / static_cast<float> (releaseSamples);
    voice.stage = EnvelopeStage::release;
}

void Processor::noteOff (int16 pitch)
{
    for (auto& voice : voices)
    {
        if (voice.active && voice.pitch == pitch)
        {
            voice.keyDown = false;
            if (!sustainEnabled)
                beginRelease (voice);
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
                beginRelease (voice);
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
    if (!streamer.readDouble (masterGain) ||
        !streamer.readDouble (vibratoDepth) ||
        !streamer.readDouble (expression) ||
        !streamer.readDouble (brightness) ||
        !streamer.readDouble (reverbMix) ||
        !streamer.readDouble (delayMix) ||
        !streamer.readDouble (chorusMix))
        return kResultFalse;
    const auto savedReverbMix = reverbMix;
    const auto savedDelayMix = delayMix;
    const auto savedChorusMix = chorusMix;
    uint32 program = 0;
    if (streamer.readInt32u (program))
    {
        applyPreset (static_cast<std::uint8_t> (program % kPresetCount));
        reverbMix = savedReverbMix;
        delayMix = savedDelayMix;
        chorusMix = savedChorusMix;
        currentPreset.reverbMix = static_cast<float> (savedReverbMix);
        currentPreset.delayMix = static_cast<float> (savedDelayMix);
        currentPreset.chorusMix = static_cast<float> (savedChorusMix);
    }
    uint32 discrete = 0;
    double patchValue = 0.0;
    if (!streamer.readInt32u (discrete))
        return kResultOk;
    currentPreset.waveformA = static_cast<Waveform> (std::min<uint32> (discrete, 9));
    if (!streamer.readInt32u (discrete))
        return kResultFalse;
    currentPreset.waveformB = static_cast<Waveform> (std::min<uint32> (discrete, 9));
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    currentPreset.waveformMix = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    currentPreset.attackMs = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    currentPreset.decayMs = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    currentPreset.sustain = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    currentPreset.releaseMs = static_cast<float> (patchValue);
    if (!streamer.readInt32u (discrete))
        return kResultFalse;
    currentPreset.filterType =
        static_cast<FilterType> (std::min<uint32> (discrete, 3));
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    currentPreset.filterCutoffHz = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    currentPreset.filterResonance = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    currentPreset.filterEnvelope = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    currentPreset.detuneCents = static_cast<float> (patchValue);
    if (!streamer.readInt32u (discrete))
        return kResultFalse;
    currentPreset.unisonVoices =
        static_cast<std::uint8_t> (std::clamp<uint32> (discrete, 1, 16));
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    currentPreset.vibratoRateHz = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    currentPreset.vibratoDepthSemitones = static_cast<float> (patchValue);
    if (!streamer.readDouble (patchValue))
        return kResultFalse;
    currentPreset.delayTimeMs = static_cast<float> (patchValue);
    return kResultOk;
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
                   streamer.writeDouble (chorusMix) &&
                   streamer.writeInt32u (currentPreset.program) &&
                   streamer.writeInt32u (
                       static_cast<uint32> (currentPreset.waveformA)) &&
                   streamer.writeInt32u (
                       static_cast<uint32> (currentPreset.waveformB)) &&
                   streamer.writeDouble (currentPreset.waveformMix) &&
                   streamer.writeDouble (currentPreset.attackMs) &&
                   streamer.writeDouble (currentPreset.decayMs) &&
                   streamer.writeDouble (currentPreset.sustain) &&
                   streamer.writeDouble (currentPreset.releaseMs) &&
                   streamer.writeInt32u (
                       static_cast<uint32> (currentPreset.filterType)) &&
                   streamer.writeDouble (currentPreset.filterCutoffHz) &&
                   streamer.writeDouble (currentPreset.filterResonance) &&
                   streamer.writeDouble (currentPreset.filterEnvelope) &&
                   streamer.writeDouble (currentPreset.detuneCents) &&
                   streamer.writeInt32u (currentPreset.unisonVoices) &&
                   streamer.writeDouble (currentPreset.vibratoRateHz) &&
                   streamer.writeDouble (currentPreset.vibratoDepthSemitones) &&
                   streamer.writeDouble (currentPreset.delayTimeMs)
               ? kResultOk
               : kResultFalse;
}

} // namespace Steinberg::Vst::SammyBlaze
