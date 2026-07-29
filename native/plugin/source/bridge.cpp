#include "bridge.h"

#include <array>
#include <chrono>
#include <cstring>

#if defined(_WIN32)
#include <winsock2.h>
#include <ws2tcpip.h>
#endif

namespace Steinberg::Vst::SammyBlaze {
namespace {
constexpr std::uint16_t bridgePort = 18736;
constexpr std::size_t packetSize = 14;

std::uint32_t readSequence (const std::array<std::uint8_t, packetSize>& packet)
{
    return static_cast<std::uint32_t> (packet[10]) |
           (static_cast<std::uint32_t> (packet[11]) << 8U) |
           (static_cast<std::uint32_t> (packet[12]) << 16U) |
           (static_cast<std::uint32_t> (packet[13]) << 24U);
}
} // namespace

GestureBridgeReceiver::~GestureBridgeReceiver ()
{
    stop ();
}

void GestureBridgeReceiver::start ()
{
    if (worker.joinable ())
        return;
    worker = std::jthread ([this] (std::stop_token stopToken) {
        receiveLoop (stopToken);
    });
}

void GestureBridgeReceiver::stop ()
{
    if (!worker.joinable ())
        return;
    worker.request_stop ();
    worker.join ();
}

bool GestureBridgeReceiver::pop (BridgeMessage& message)
{
    const auto read = readIndex.load (std::memory_order_relaxed);
    if (read == writeIndex.load (std::memory_order_acquire))
        return false;
    message = queue[read];
    readIndex.store ((read + 1) % queueCapacity, std::memory_order_release);
    return true;
}

bool GestureBridgeReceiver::push (const BridgeMessage& message)
{
    const auto write = writeIndex.load (std::memory_order_relaxed);
    const auto next = (write + 1) % queueCapacity;
    if (next == readIndex.load (std::memory_order_acquire))
        return false;
    queue[write] = message;
    writeIndex.store (next, std::memory_order_release);
    return true;
}

void GestureBridgeReceiver::receiveLoop (std::stop_token stopToken)
{
#if defined(_WIN32)
    WSADATA socketData {};
    if (WSAStartup (MAKEWORD (2, 2), &socketData) != 0)
        return;

    const auto socketHandle = socket (AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (socketHandle == INVALID_SOCKET)
    {
        WSACleanup ();
        return;
    }

    DWORD timeoutMs = 100;
    setsockopt (
        socketHandle,
        SOL_SOCKET,
        SO_RCVTIMEO,
        reinterpret_cast<const char*> (&timeoutMs),
        sizeof (timeoutMs));

    sockaddr_in address {};
    address.sin_family = AF_INET;
    address.sin_port = htons (bridgePort);
    inet_pton (AF_INET, "127.0.0.1", &address.sin_addr);
    if (bind (socketHandle, reinterpret_cast<sockaddr*> (&address), sizeof (address)) ==
        SOCKET_ERROR)
    {
        closesocket (socketHandle);
        WSACleanup ();
        return;
    }

    std::array<std::uint8_t, packetSize> packet {};
    std::uint32_t lastSequence = 0;
    bool hasSequence = false;
    auto lastPacketAt = std::chrono::steady_clock::now () - std::chrono::seconds (1);
    while (!stopToken.stop_requested ())
    {
        const auto received = recvfrom (
            socketHandle,
            reinterpret_cast<char*> (packet.data ()),
            static_cast<int> (packet.size ()),
            0,
            nullptr,
            nullptr);
        if (received != static_cast<int> (packet.size ()))
            continue;
        if (std::memcmp (packet.data (), "SBW1", 4) != 0 || packet[4] != 1)
            continue;
        if (packet[5] < static_cast<std::uint8_t> (BridgeMessageType::noteOn) ||
            packet[5] > static_cast<std::uint8_t> (BridgeMessageType::programChange))
            continue;
        if (packet[6] > 127 || packet[7] > 127 || packet[8] > 127)
            continue;

        const auto sequence = readSequence (packet);
        const auto now = std::chrono::steady_clock::now ();
        if (
            hasSequence &&
            static_cast<std::int32_t> (sequence - lastSequence) <= 0 &&
            now - lastPacketAt < std::chrono::milliseconds (500))
            continue;
        hasSequence = true;
        lastSequence = sequence;
        lastPacketAt = now;
        push ({
            static_cast<BridgeMessageType> (packet[5]),
            packet[6],
            packet[7],
            packet[8],
            sequence,
        });
    }

    closesocket (socketHandle);
    WSACleanup ();
#else
    while (!stopToken.stop_requested ())
        std::this_thread::sleep_for (std::chrono::milliseconds (100));
#endif
}

} // namespace Steinberg::Vst::SammyBlaze
