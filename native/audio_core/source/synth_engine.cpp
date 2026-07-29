#include "sammyblaze/audio_core/synth_engine.h"

#include "sammyblaze/audio_core/dsp.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <new>

namespace SammyBlaze::AudioCore {
namespace {

constexpr double twoPi = 6.28318530717958647692;
constexpr float minimumEnvelopeTimeMs = 0.5f;
constexpr double minimumSampleRate = 8000.0;
constexpr double maximumSampleRate = 384000.0;
constexpr std::uint32_t maximumSupportedBlockSize = 65536;
constexpr std::size_t sineTableSize = 4096;
constexpr std::size_t exp2TableSize = 4096;
constexpr float exp2Minimum = -8.0f;
constexpr float exp2Maximum = 8.0f;

struct SineTable
{
    SineTable () noexcept
    {
        for (std::size_t index = 0; index <= sineTableSize; ++index)
        {
            values[index] = static_cast<float> (
                std::sin (
                    static_cast<double> (index) * twoPi /
                    static_cast<double> (sineTableSize)));
        }
    }

    std::array<float, sineTableSize + 1> values {};
};

const SineTable sineTable;

struct Exp2Table
{
    Exp2Table () noexcept
    {
        for (std::size_t index = 0; index <= exp2TableSize; ++index)
        {
            const auto exponent =
                static_cast<double> (exp2Minimum) +
                (static_cast<double> (exp2Maximum - exp2Minimum) *
                 static_cast<double> (index) /
                 static_cast<double> (exp2TableSize));
            values[index] = static_cast<float> (std::exp2 (exponent));
        }
    }

    std::array<float, exp2TableSize + 1> values {};
};

const Exp2Table exp2Table;

float clampFinite (float value, float fallback, float minimum, float maximum) noexcept
{
    return std::clamp (std::isfinite (value) ? value : fallback, minimum, maximum);
}

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

double advanceUnitPhase (double phase, double increment) noexcept
{
    phase += increment;
    return phase >= 1.0 ? phase - 1.0 : phase;
}

float sineFromUnitPhase (double phase) noexcept
{
    const auto tablePosition =
        phase * static_cast<double> (sineTableSize);
    const auto index = static_cast<std::size_t> (tablePosition);
    const auto fraction =
        static_cast<float> (tablePosition - static_cast<double> (index));
    const auto lower = sineTable.values[index];
    return lower + (sineTable.values[index + 1] - lower) * fraction;
}

float sineFromPhase (double phase) noexcept
{
    return sineFromUnitPhase (wrapPhase (phase));
}

float fastExp2 (float exponent) noexcept
{
    const auto bounded = std::clamp (
        std::isfinite (exponent) ? exponent : 0.0f,
        exp2Minimum,
        exp2Maximum);
    const auto tablePosition =
        (bounded - exp2Minimum) *
        (static_cast<float> (exp2TableSize) /
         (exp2Maximum - exp2Minimum));
    const auto index = static_cast<std::size_t> (tablePosition);
    const auto fraction =
        tablePosition - static_cast<float> (index);
    const auto lower = exp2Table.values[index];
    return lower +
           (exp2Table.values[std::min (index + 1, exp2TableSize)] - lower) *
               fraction;
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
    switch (waveform)
    {
        case Waveform::sine:
            return sineFromUnitPhase (phase);
        case Waveform::triangle:
            if (phase < 0.25)
                return static_cast<float> (phase * 4.0);
            if (phase < 0.75)
                return static_cast<float> (2.0 - phase * 4.0);
            return static_cast<float> (phase * 4.0 - 4.0);
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
            return sineFromUnitPhase (phase) * 0.68f +
                   sineFromPhase (phase * 2.0) * 0.22f +
                   sineFromPhase (phase * 3.0) * 0.10f;
        case Waveform::metal:
            return sineFromUnitPhase (phase) * 0.52f +
                   sineFromPhase (phase * 2.41) * 0.30f +
                   sineFromPhase (phase * 5.31) * 0.18f;
        case Waveform::noise:
            return randomBipolar (noiseState);
        case Waveform::vocal:
            return sineFromUnitPhase (phase) * 0.58f +
                   sineFromPhase (phase * 2.0) * 0.27f +
                   sineFromPhase (phase * 4.0) * 0.15f;
        case Waveform::wavetable:
            return sineFromUnitPhase (phase) * 0.62f +
                   sineFromPhase (phase * 3.0) * 0.23f +
                   static_cast<float> (phase * 2.0 - 1.0) * 0.15f;
    }
    return 0.0f;
}

bool validPreset (const SynthPreset& preset) noexcept
{
    const auto finiteInRange = [] (float value, float minimum, float maximum) {
        return std::isfinite (value) && value >= minimum && value <= maximum;
    };
    return preset.program < kPresetCount &&
           static_cast<std::uint32_t> (preset.waveformA) <= 9 &&
           static_cast<std::uint32_t> (preset.waveformB) <= 9 &&
           static_cast<std::uint32_t> (preset.filterType) <= 3 &&
           preset.unisonVoices >= 1 && preset.unisonVoices <= 16 &&
           finiteInRange (preset.waveformMix, 0.0f, 1.0f) &&
           finiteInRange (preset.attackMs, 0.0f, 20000.0f) &&
           finiteInRange (preset.decayMs, 0.0f, 20000.0f) &&
           finiteInRange (preset.sustain, 0.0f, 1.0f) &&
           finiteInRange (preset.releaseMs, 0.0f, 30000.0f) &&
           finiteInRange (preset.filterCutoffHz, 20.0f, 20000.0f) &&
           finiteInRange (preset.filterResonance, 0.0f, 1.0f) &&
           finiteInRange (preset.filterEnvelope, -1.0f, 1.0f) &&
           finiteInRange (preset.detuneCents, 0.0f, 100.0f) &&
           finiteInRange (preset.vibratoRateHz, 0.0f, 15.0f) &&
           finiteInRange (preset.vibratoDepthSemitones, 0.0f, 2.0f) &&
           finiteInRange (preset.reverbMix, 0.0f, 1.0f) &&
           finiteInRange (preset.delayMix, 0.0f, 1.0f) &&
           finiteInRange (preset.delayTimeMs, 1.0f, 2500.0f) &&
           finiteInRange (preset.chorusMix, 0.0f, 1.0f);
}

} // namespace

SynthEngine::SynthEngine () noexcept = default;

bool SynthEngine::setup (double sampleRate, std::uint32_t maximumBlockSize)
{
    if (!std::isfinite (sampleRate) || sampleRate < minimumSampleRate ||
        sampleRate > maximumSampleRate || maximumBlockSize == 0 ||
        maximumBlockSize > maximumSupportedBlockSize)
        return false;

    const auto requestedSize =
        static_cast<std::size_t> (std::ceil (sampleRate * 2.6));
    auto replacement = std::make_unique<float[]> (requestedSize);
    std::fill_n (replacement.get (), requestedSize, 0.0f);

    effectBuffer_ = std::move (replacement);
    effectBufferSize_ = requestedSize;
    effectWriteIndex_ = 0;
    sampleRate_ = sampleRate;
    maximumBlockSize_ = maximumBlockSize;
    smoothedMasterGain_ = masterGain_;
    smoothedExpression_ = expression_;
    smoothedBrightness_ = brightness_;
    smoothedReverbMix_ = reverbMix_;
    smoothedDelayMix_ = delayMix_;
    smoothedChorusMix_ = chorusMix_;
    smoothingCoefficient_ = static_cast<float> (
        1.0 - std::exp (-1.0 / (sampleRate_ * 0.015)));
    panic ();
    return true;
}

bool SynthEngine::isReady () const noexcept
{
    return effectBuffer_ != nullptr && effectBufferSize_ > 0 &&
           sampleRate_ >= minimumSampleRate && maximumBlockSize_ > 0;
}

double SynthEngine::sampleRate () const noexcept
{
    return sampleRate_;
}

std::uint32_t SynthEngine::maximumBlockSize () const noexcept
{
    return maximumBlockSize_;
}

void SynthEngine::updateVoiceTuning (Voice& voice) noexcept
{
    const auto unisonCount = std::clamp<int> (
        voice.preset.unisonVoices,
        1,
        static_cast<int> (kMaximumUnisonVoices));
    voice.requestedUnisonVoices =
        static_cast<std::uint8_t> (unisonCount);
    voice.filterDamping =
        filterDamping (voice.preset.filterResonance);
    voice.filterCoefficientLimit = std::min (
        kLegacyFilterCoefficientLimit,
        maximumStableFilterCoefficient (voice.filterDamping));
    const auto baseFrequency =
        440.0 * std::exp2 ((static_cast<double> (voice.pitch) - 69.0) / 12.0);
    for (int unison = 0; unison < unisonCount; ++unison)
    {
        const auto center = static_cast<double> (unisonCount - 1) * 0.5;
        const auto detune =
            (static_cast<double> (unison) - center) *
            static_cast<double> (voice.preset.detuneCents) /
            std::max (1.0, center) / 100.0;
        voice.frequency[static_cast<std::size_t> (unison)] =
            baseFrequency * std::exp2 (detune / 12.0);
    }
}

void SynthEngine::noteOn (std::uint8_t pitch, float velocity) noexcept
{
    auto voice = std::find_if (voices_.begin (), voices_.end (), [] (const Voice& candidate) {
        return !candidate.active;
    });
    if (voice == voices_.end ())
    {
        voice = std::min_element (
            voices_.begin (),
            voices_.end (),
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
    voice->pitch = static_cast<std::int16_t> (pitch);
    voice->velocity = clampFinite (velocity, 0.0f, 0.0f, 1.0f);
    voice->phaseB.fill (0.173);
    voice->keyDown = true;
    voice->active = true;
    voice->stage = EnvelopeStage::attack;
    voice->preset = currentPreset_;
    voice->age = ++voiceAge_;
    voice->noiseState = static_cast<std::uint32_t> (
        voiceAge_ * 747796405ULL +
        static_cast<std::uint64_t> (pitch) * 2891336453ULL);
    updateVoiceTuning (*voice);
}

void SynthEngine::beginRelease (Voice& voice) noexcept
{
    if (!voice.active || voice.stage == EnvelopeStage::release)
        return;
    const auto releaseSamples = std::max (
        1.0,
        static_cast<double> (
            std::max (voice.preset.releaseMs, minimumEnvelopeTimeMs)) *
            std::max (sampleRate_, 44100.0) / 1000.0);
    voice.releaseStep = voice.envelope / static_cast<float> (releaseSamples);
    voice.stage = EnvelopeStage::release;
}

void SynthEngine::noteOff (std::uint8_t pitch) noexcept
{
    for (auto& voice : voices_)
    {
        if (voice.active && voice.pitch == static_cast<std::int16_t> (pitch))
        {
            voice.keyDown = false;
            if (!sustainEnabled_)
                beginRelease (voice);
        }
    }
}

void SynthEngine::setSustain (bool enabled) noexcept
{
    if (sustainEnabled_ == enabled)
        return;
    sustainEnabled_ = enabled;
    if (!sustainEnabled_)
    {
        for (auto& voice : voices_)
        {
            if (voice.active && !voice.keyDown)
                beginRelease (voice);
        }
    }
}

void SynthEngine::controlChange (
    std::uint8_t controller,
    std::uint8_t value) noexcept
{
    const auto normalized = static_cast<float> (value) / 127.0f;
    switch (controller)
    {
        case 1: setVibratoDepth (normalized); break;
        case 7: setMasterGain (normalized); break;
        case 11: setExpression (normalized); break;
        case 64: setSustain (value >= 64); break;
        case 74: setBrightness (normalized); break;
        case 91: setReverbMix (normalized); break;
        case 93: setChorusMix (normalized); break;
        case 94: setDelayMix (normalized); break;
        case 120:
        case 123: panic (); break;
        default: break;
    }
}

void SynthEngine::programChange (std::uint8_t program) noexcept
{
    panic ();
    currentPreset_ = presetForProgram (program);
    reverbMix_ = currentPreset_.reverbMix;
    delayMix_ = currentPreset_.delayMix;
    chorusMix_ = currentPreset_.chorusMix;
}

void SynthEngine::updateActiveVoicePresets () noexcept
{
    for (auto& voice : voices_)
    {
        if (voice.active)
        {
            voice.preset = currentPreset_;
            updateVoiceTuning (voice);
        }
    }
}

void SynthEngine::applySoundParameter (
    std::uint8_t parameter,
    std::uint8_t value) noexcept
{
    const auto normalized = static_cast<float> (value) / 127.0f;
    switch (parameter)
    {
        case 0: setMasterGain (normalized); return;
        case 1:
            currentPreset_.waveformA = static_cast<Waveform> (
                std::clamp (std::lround (normalized * 9.0f), 0L, 9L));
            break;
        case 2:
            currentPreset_.waveformB = static_cast<Waveform> (
                std::clamp (std::lround (normalized * 9.0f), 0L, 9L));
            break;
        case 3: currentPreset_.waveformMix = normalized; break;
        case 4:
            currentPreset_.attackMs =
                value == 0 ? 0.0f
                           : logarithmicValue (normalized, 0.5f, 20000.0f);
            break;
        case 5:
            currentPreset_.decayMs =
                logarithmicValue (normalized, 0.5f, 20000.0f);
            break;
        case 6: currentPreset_.sustain = normalized; break;
        case 7:
            currentPreset_.releaseMs =
                value == 0 ? 0.0f
                           : logarithmicValue (normalized, 0.5f, 30000.0f);
            break;
        case 8:
            currentPreset_.filterType = static_cast<FilterType> (
                std::clamp (std::lround (normalized * 3.0f), 0L, 3L));
            break;
        case 9:
            currentPreset_.filterCutoffHz =
                logarithmicValue (normalized, 20.0f, 20000.0f);
            break;
        case 10: currentPreset_.filterResonance = normalized; break;
        case 11:
            currentPreset_.filterEnvelope =
                linearValue (normalized, -1.0f, 1.0f);
            break;
        case 12: currentPreset_.detuneCents = normalized * 100.0f; break;
        case 13:
            currentPreset_.unisonVoices = static_cast<std::uint8_t> (
                std::clamp (
                    std::lround (linearValue (normalized, 1.0f, 16.0f)),
                    1L,
                    16L));
            break;
        case 14: currentPreset_.vibratoRateHz = normalized * 15.0f; break;
        case 15:
            currentPreset_.vibratoDepthSemitones = normalized * 2.0f;
            break;
        case 16:
            currentPreset_.reverbMix = normalized;
            setReverbMix (normalized);
            break;
        case 17:
            currentPreset_.delayMix = normalized;
            setDelayMix (normalized);
            break;
        case 18:
            currentPreset_.delayTimeMs =
                logarithmicValue (normalized, 1.0f, 2500.0f);
            break;
        case 19:
            currentPreset_.chorusMix = normalized;
            setChorusMix (normalized);
            break;
        case 20: setBrightness (normalized); return;
        default: return;
    }
    updateActiveVoicePresets ();
}

bool SynthEngine::applyPatch (
    const SynthPreset& preset,
    float patchMasterGain,
    float patchBrightness) noexcept
{
    if (!validPreset (preset) || !std::isfinite (patchMasterGain) ||
        patchMasterGain < 0.0f || patchMasterGain > 1.0f ||
        !std::isfinite (patchBrightness) || patchBrightness < 0.0f ||
        patchBrightness > 1.0f)
        return false;

    currentPreset_ = preset;
    currentPreset_.name = presetName (preset.program);
    masterGain_ = patchMasterGain;
    brightness_ = patchBrightness;
    reverbMix_ = preset.reverbMix;
    delayMix_ = preset.delayMix;
    chorusMix_ = preset.chorusMix;
    updateActiveVoicePresets ();
    return true;
}

void SynthEngine::setMasterGain (float value) noexcept
{
    masterGain_ = clampFinite (value, masterGain_, 0.0f, 1.0f);
}

void SynthEngine::setVibratoDepth (float value) noexcept
{
    vibratoDepth_ = clampFinite (value, vibratoDepth_, 0.0f, 1.0f);
}

void SynthEngine::setExpression (float value) noexcept
{
    expression_ = clampFinite (value, expression_, 0.0f, 1.0f);
}

void SynthEngine::setBrightness (float value) noexcept
{
    brightness_ = clampFinite (value, brightness_, 0.0f, 1.0f);
}

void SynthEngine::setReverbMix (float value) noexcept
{
    reverbMix_ = clampFinite (value, reverbMix_, 0.0f, 1.0f);
}

void SynthEngine::setDelayMix (float value) noexcept
{
    delayMix_ = clampFinite (value, delayMix_, 0.0f, 1.0f);
}

void SynthEngine::setChorusMix (float value) noexcept
{
    chorusMix_ = clampFinite (value, chorusMix_, 0.0f, 1.0f);
}

void SynthEngine::recordRecovery () noexcept
{
    nonfiniteRecoveryCount_.fetch_add (1, std::memory_order_relaxed);
}

float SynthEngine::renderVoice (Voice& voice, double vibratoRatio) noexcept
{
    const auto& preset = voice.preset;
    switch (voice.stage)
    {
        case EnvelopeStage::attack:
        {
            const auto attack = std::max (preset.attackMs, minimumEnvelopeTimeMs);
            voice.envelope += static_cast<float> (
                1000.0 / (static_cast<double> (attack) * sampleRate_));
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
                (1.0 - static_cast<double> (preset.sustain)) * 1000.0 /
                (static_cast<double> (decay) * sampleRate_));
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

    const auto unisonCount =
        static_cast<int> (voice.requestedUnisonVoices);
    const auto renderedLanes = std::min (
        unisonCount,
        static_cast<int> (renderedUnisonLanesPerVoice_));
    float oscillators = 0.0f;
    for (int lane = 0; lane < renderedLanes; ++lane)
    {
        const auto unison =
            renderedLanes == unisonCount
                ? lane
                : renderedLanes == 1
                      ? (unisonCount - 1) / 2
                      : (lane * (unisonCount - 1) +
                         (renderedLanes - 1) / 2) /
                            (renderedLanes - 1);
        const auto index = static_cast<std::size_t> (unison);
        const auto frequency = voice.frequency[index] * vibratoRatio;
        const auto increment = std::min (frequency / sampleRate_, 0.45);
        voice.phaseA[index] =
            advanceUnitPhase (voice.phaseA[index], increment);
        voice.phaseB[index] =
            advanceUnitPhase (
                voice.phaseB[index],
                increment * 1.001);
        const auto a = waveformSample (
            preset.waveformA,
            voice.phaseA[index],
            increment,
            voice.noiseState);
        const auto b = waveformSample (
            preset.waveformB,
            voice.phaseB[index],
            increment,
            voice.noiseState);
        oscillators += a * (1.0f - preset.waveformMix) +
                       b * preset.waveformMix;
    }
    oscillatorWorkCount_ += static_cast<std::uint64_t> (renderedLanes);
    const auto laneGain =
        1.0f / std::sqrt (static_cast<float> (renderedLanes));
    oscillators *=
        laneGain *
        voice.velocity * voice.envelope;

    const auto cutoffOctaves =
        preset.filterEnvelope * voice.envelope * 4.0f +
        (smoothedBrightness_ - 0.5f) * 4.0f;
    const auto cutoff = std::clamp (
        preset.filterCutoffHz * fastExp2 (cutoffOctaves),
        kMinimumFilterCutoffHz,
        static_cast<float> (sampleRate_) *
            kMaximumFilterNyquistRatio);
    bool recovered = false;
    if (!std::isfinite (voice.filterLow) ||
        !std::isfinite (voice.filterBand))
    {
        voice.filterLow = 0.0f;
        voice.filterBand = 0.0f;
        recovered = true;
    }
    const auto safeInput = std::isfinite (oscillators) ? oscillators : 0.0f;
    recovered = recovered || !std::isfinite (oscillators);
    const auto coefficient = std::clamp (
        2.0f * sineFromUnitPhase (
                   static_cast<double> (cutoff) /
                   (2.0 * sampleRate_)),
        kMinimumFilterCoefficient,
        voice.filterCoefficientLimit);
    voice.filterLow += coefficient * voice.filterBand;
    const auto high =
        safeInput - voice.filterLow -
        voice.filterDamping * voice.filterBand;
    voice.filterBand += coefficient * high;
    if (!std::isfinite (voice.filterLow) ||
        !std::isfinite (voice.filterBand) || !std::isfinite (high))
    {
        voice.filterLow = 0.0f;
        voice.filterBand = 0.0f;
        recordRecovery ();
        return 0.0f;
    }
    if (recovered)
        recordRecovery ();
    return selectFilterOutput (
        {voice.filterLow,
         high,
         voice.filterBand,
         voice.filterLow + high},
        preset.filterType);
}

void SynthEngine::renderSample (
    float& left,
    float& right,
    std::size_t delaySamples,
    std::size_t reverbSamplesA,
    std::size_t reverbSamplesB) noexcept
{
    smoothedMasterGain_ +=
        (masterGain_ - smoothedMasterGain_) * smoothingCoefficient_;
    smoothedExpression_ +=
        (expression_ - smoothedExpression_) * smoothingCoefficient_;
    smoothedBrightness_ +=
        (brightness_ - smoothedBrightness_) * smoothingCoefficient_;
    smoothedReverbMix_ +=
        (reverbMix_ - smoothedReverbMix_) * smoothingCoefficient_;
    smoothedDelayMix_ +=
        (delayMix_ - smoothedDelayMix_) * smoothingCoefficient_;
    smoothedChorusMix_ +=
        (chorusMix_ - smoothedChorusMix_) * smoothingCoefficient_;

    const auto gestureVibrato = static_cast<double> (vibratoDepth_) * 0.5;
    const auto vibratoSemitones =
        (static_cast<double> (currentPreset_.vibratoDepthSemitones) +
         gestureVibrato) *
        sineFromUnitPhase (lfoPhase_);
    const auto vibratoRatio =
        static_cast<double> (
            fastExp2 (static_cast<float> (vibratoSemitones / 12.0)));

    float mixed = 0.0f;
    for (auto& voice : voices_)
    {
        if (voice.active)
            mixed += renderVoice (voice, vibratoRatio);
    }
    lfoPhase_ = advanceUnitPhase (
        lfoPhase_,
        static_cast<double> (currentPreset_.vibratoRateHz) / sampleRate_);
    mixed *= smoothedMasterGain_ * smoothedExpression_ * 0.13f;

    left = mixed;
    right = mixed;
    if (effectBufferSize_ > reverbSamplesB + 1 && delaySamples > 0)
    {
        const auto tap = [this] (std::size_t samplesBack) {
            return effectBuffer_[
                (effectWriteIndex_ + effectBufferSize_ - samplesBack) %
                effectBufferSize_];
        };
        const auto delayTap = tap (delaySamples);
        const auto reverbA = tap (reverbSamplesA);
        const auto reverbB = tap (reverbSamplesB);
        const auto chorusMod = static_cast<std::size_t> (
            sampleRate_ *
            (0.018 +
             0.005 *
                 (0.5 +
                  0.5 * sineFromUnitPhase (lfoPhase_ * 0.73))));
        const auto chorusTap =
            tap (std::max<std::size_t> (1, chorusMod));
        const auto feedbackSample =
            mixed + delayTap * smoothedDelayMix_ * 0.42f +
            (reverbA + reverbB) * smoothedReverbMix_ * 0.24f;
        if (std::isfinite (feedbackSample))
            effectBuffer_[effectWriteIndex_] =
                std::clamp (feedbackSample, -2.0f, 2.0f);
        else
        {
            effectBuffer_[effectWriteIndex_] = 0.0f;
            recordRecovery ();
        }
        effectWriteIndex_ = (effectWriteIndex_ + 1) % effectBufferSize_;

        left += delayTap * smoothedDelayMix_ * 0.62f;
        right += delayTap * smoothedDelayMix_ * 0.48f;
        left += reverbA * smoothedReverbMix_ * 0.48f;
        right += reverbB * smoothedReverbMix_ * 0.48f;
        left += chorusTap * smoothedChorusMix_ * 0.34f;
        right -= chorusTap * smoothedChorusMix_ * 0.28f;
    }

    if (std::isfinite (left))
        left = std::tanh (left * 1.15f) * 0.86f;
    else
    {
        left = 0.0f;
        recordRecovery ();
    }
    if (std::isfinite (right))
        right = std::tanh (right * 1.15f) * 0.86f;
    else
    {
        right = 0.0f;
        recordRecovery ();
    }
}

template <typename OutputWriter>
bool SynthEngine::renderBlock (
    std::uint32_t frames,
    OutputWriter&& writer) noexcept
{
    if (!isReady () || frames == 0 || frames > maximumBlockSize_)
        return false;
    const auto activeVoices = std::max<std::uint32_t> (
        activeVoiceCount (),
        1);
    const auto requested = static_cast<std::uint8_t> (
        std::clamp<std::size_t> (
            currentPreset_.unisonVoices,
            1,
            kMaximumUnisonVoices));
    const auto budgetedLanes = std::max<std::size_t> (
        1,
        kUnisonOscillatorBudgetPerSample /
            static_cast<std::size_t> (activeVoices));
    renderedUnisonLanesPerVoice_ = static_cast<std::uint8_t> (
        std::min<std::size_t> (requested, budgetedLanes));
    unisonQualityLimited_ =
        renderedUnisonLanesPerVoice_ < requested;
    const auto requestedDelay = static_cast<std::size_t> (
        sampleRate_ * static_cast<double> (currentPreset_.delayTimeMs) /
        1000.0);
    const auto delaySamples =
        effectBufferSize_ > 1
            ? std::clamp<std::size_t> (
                  requestedDelay,
                  1,
                  effectBufferSize_ - 1)
            : 0;
    const auto reverbSamplesA =
        static_cast<std::size_t> (sampleRate_ * 0.061);
    const auto reverbSamplesB =
        static_cast<std::size_t> (sampleRate_ * 0.089);
    for (std::uint32_t sample = 0; sample < frames; ++sample)
    {
        float left = 0.0f;
        float right = 0.0f;
        renderSample (
            left,
            right,
            delaySamples,
            reverbSamplesA,
            reverbSamplesB);
        writer (sample, left, right);
    }
    return true;
}

bool SynthEngine::renderInterleaved (
    float* stereoOutput,
    std::uint32_t frames) noexcept
{
    if (!stereoOutput)
        return false;
    return renderBlock (
        frames,
        [stereoOutput] (
            std::uint32_t sample,
            float left,
            float right) noexcept {
            const auto index = static_cast<std::size_t> (sample) * 2;
            stereoOutput[index] = left;
            stereoOutput[index + 1] = right;
        });
}

bool SynthEngine::renderPlanar (
    float* leftOutput,
    float* rightOutput,
    std::uint32_t frames) noexcept
{
    if (!leftOutput || !rightOutput)
        return false;
    return renderBlock (
        frames,
        [leftOutput, rightOutput] (
            std::uint32_t sample,
            float left,
            float right) noexcept {
            leftOutput[sample] = left;
            rightOutput[sample] = right;
        });
}

void SynthEngine::clearEffectBuffer () noexcept
{
    if (effectBuffer_)
        std::fill_n (effectBuffer_.get (), effectBufferSize_, 0.0f);
    effectWriteIndex_ = 0;
}

void SynthEngine::panic () noexcept
{
    for (auto& voice : voices_)
        voice = {};
    sustainEnabled_ = false;
    lfoPhase_ = 0.0;
    renderedUnisonLanesPerVoice_ = 1;
    unisonQualityLimited_ = false;
    clearEffectBuffer ();
}

std::uint32_t SynthEngine::activeVoiceCount () const noexcept
{
    return static_cast<std::uint32_t> (
        std::count_if (voices_.begin (), voices_.end (), [] (const Voice& voice) {
            return voice.active;
        }));
}

std::uint64_t SynthEngine::nonfiniteRecoveryCount () const noexcept
{
    return nonfiniteRecoveryCount_.load (std::memory_order_relaxed);
}

std::uint8_t SynthEngine::requestedUnisonVoices () const noexcept
{
    return static_cast<std::uint8_t> (
        std::clamp<std::size_t> (
            currentPreset_.unisonVoices,
            1,
            kMaximumUnisonVoices));
}

std::uint8_t SynthEngine::renderedUnisonLanesPerVoice () const noexcept
{
    return renderedUnisonLanesPerVoice_;
}

bool SynthEngine::unisonQualityLimited () const noexcept
{
    return unisonQualityLimited_;
}

std::uint64_t SynthEngine::oscillatorWorkCount () const noexcept
{
    return oscillatorWorkCount_;
}

const SynthPreset& SynthEngine::currentPreset () const noexcept
{
    return currentPreset_;
}

float SynthEngine::masterGain () const noexcept
{
    return masterGain_;
}

float SynthEngine::vibratoDepth () const noexcept
{
    return vibratoDepth_;
}

float SynthEngine::expression () const noexcept
{
    return expression_;
}

float SynthEngine::brightness () const noexcept
{
    return brightness_;
}

float SynthEngine::reverbMix () const noexcept
{
    return reverbMix_;
}

float SynthEngine::delayMix () const noexcept
{
    return delayMix_;
}

float SynthEngine::chorusMix () const noexcept
{
    return chorusMix_;
}

} // namespace SammyBlaze::AudioCore
