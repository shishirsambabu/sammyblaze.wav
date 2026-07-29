#pragma once

#include "sammyblaze/audio_core/presets.h"

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <memory>

namespace SammyBlaze::AudioCore {

inline constexpr std::size_t kMaximumVoices = 24;

class SynthEngine final
{
public:
    SynthEngine () noexcept;
    ~SynthEngine () = default;

    SynthEngine (const SynthEngine&) = delete;
    SynthEngine& operator= (const SynthEngine&) = delete;
    SynthEngine (SynthEngine&&) = delete;
    SynthEngine& operator= (SynthEngine&&) = delete;

    bool setup (double sampleRate, std::uint32_t maximumBlockSize);
    bool isReady () const noexcept;
    double sampleRate () const noexcept;
    std::uint32_t maximumBlockSize () const noexcept;

    void noteOn (std::uint8_t pitch, float velocity) noexcept;
    void noteOff (std::uint8_t pitch) noexcept;
    void controlChange (std::uint8_t controller, std::uint8_t value) noexcept;
    void programChange (std::uint8_t program) noexcept;
    void applySoundParameter (std::uint8_t parameter, std::uint8_t value) noexcept;
    bool applyPatch (
        const SynthPreset& preset,
        float patchMasterGain,
        float patchBrightness) noexcept;

    void setMasterGain (float value) noexcept;
    void setVibratoDepth (float value) noexcept;
    void setExpression (float value) noexcept;
    void setBrightness (float value) noexcept;
    void setReverbMix (float value) noexcept;
    void setDelayMix (float value) noexcept;
    void setChorusMix (float value) noexcept;

    bool renderInterleaved (float* stereoOutput, std::uint32_t frames) noexcept;
    bool renderPlanar (
        float* leftOutput,
        float* rightOutput,
        std::uint32_t frames) noexcept;

    void panic () noexcept;
    std::uint32_t activeVoiceCount () const noexcept;
    std::uint64_t nonfiniteRecoveryCount () const noexcept;

    const SynthPreset& currentPreset () const noexcept;
    float masterGain () const noexcept;
    float vibratoDepth () const noexcept;
    float expression () const noexcept;
    float brightness () const noexcept;
    float reverbMix () const noexcept;
    float delayMix () const noexcept;
    float chorusMix () const noexcept;

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
        std::int16_t pitch {-1};
        std::array<double, 3> phaseA {};
        std::array<double, 3> phaseB {};
        std::array<double, 3> frequency {};
        float velocity {0.0f};
        float envelope {0.0f};
        float releaseStep {0.0f};
        float filterLow {0.0f};
        float filterBand {0.0f};
        float filterDamping {1.95f};
        float filterCoefficientLimit {0.95f};
        float unisonGain {1.0f};
        std::uint32_t noiseState {1};
        std::uint64_t age {0};
        SynthPreset preset {};
        EnvelopeStage stage {EnvelopeStage::off};
        std::uint8_t effectiveUnisonVoices {1};
        bool keyDown {false};
        bool active {false};
    };

    template <typename OutputWriter>
    bool renderBlock (std::uint32_t frames, OutputWriter&& writer) noexcept;

    void updateVoiceTuning (Voice& voice) noexcept;
    void updateActiveVoicePresets () noexcept;
    void beginRelease (Voice& voice) noexcept;
    void setSustain (bool enabled) noexcept;
    float renderVoice (Voice& voice, double vibratoRatio) noexcept;
    void renderSample (
        float& left,
        float& right,
        std::size_t delaySamples,
        std::size_t reverbSamplesA,
        std::size_t reverbSamplesB) noexcept;
    void recordRecovery () noexcept;
    void clearEffectBuffer () noexcept;

    std::array<Voice, kMaximumVoices> voices_ {};
    SynthPreset currentPreset_ {presetForProgram (0)};
    std::unique_ptr<float[]> effectBuffer_;
    std::size_t effectBufferSize_ {0};
    std::size_t effectWriteIndex_ {0};
    std::uint32_t maximumBlockSize_ {0};
    std::uint64_t voiceAge_ {0};
    std::atomic<std::uint64_t> nonfiniteRecoveryCount_ {0};
    double sampleRate_ {0.0};
    double lfoPhase_ {0.0};
    float masterGain_ {0.75f};
    float vibratoDepth_ {0.25f};
    float expression_ {1.0f};
    float brightness_ {0.5f};
    float reverbMix_ {0.05f};
    float delayMix_ {0.05f};
    float chorusMix_ {0.20f};
    float smoothedMasterGain_ {0.75f};
    float smoothedExpression_ {1.0f};
    float smoothedBrightness_ {0.5f};
    float smoothedReverbMix_ {0.05f};
    float smoothedDelayMix_ {0.05f};
    float smoothedChorusMix_ {0.20f};
    float smoothingCoefficient_ {0.0f};
    bool sustainEnabled_ {false};
};

static_assert (
    std::atomic<std::uint64_t>::is_always_lock_free,
    "The audio core requires lock-free recovery accounting");

} // namespace SammyBlaze::AudioCore
