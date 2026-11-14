// ============================================================================
//  relay-server.cpp - T2R Online UDP relay. Per-session packet switch: learns
//  each peer's public address from REGISTER and forwards DATA between the
//  members of a session.
//
//  Build:  Linux    g++ -O2 -o relay-server relay-server.cpp
//          Windows  cl /O2 relay-server.cpp ws2_32.lib
//  Run:    ./relay-server [port]            (default 7000)
// ============================================================================
#include "relay-protocol.h"

#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <cstdarg>
#include <cstddef>
#include <cerrno>
#include <ctime>
#include <chrono>
#include <unordered_map>

#ifdef _WIN32
  #include <winsock2.h>
  #include <ws2tcpip.h>
  #include <mstcpip.h>   // SIO_UDP_CONNRESET
  #ifndef SIO_UDP_CONNRESET   // some SDK header sets omit it
    #define SIO_UDP_CONNRESET _WSAIOW(IOC_VENDOR, 12)
  #endif
  #pragma comment(lib, "ws2_32.lib")
  typedef int socklen_t;
  #define CLOSESOCK closesocket
#else
  #include <sys/socket.h>
  #include <netinet/in.h>
  #include <arpa/inet.h>
  #include <unistd.h>
  typedef int SOCKET;
  #define INVALID_SOCKET (-1)
  #define CLOSESOCK close
#endif

// ---- tuning -----------------------------------------------------------------
static const int     kDefaultPort      = 7000;
static const int64_t kPeerTimeoutMs    = 30000;   // drop a slot unheard-from this long
static const int64_t kSessionTimeoutMs = 60000;   // remove an empty session after this
static const int64_t kSweepIntervalMs  = 5000;    // how often to prune
static const int     kRecvTimeoutMs    = 1000;    // wake the loop to prune even when idle

// Hard ceiling on live sessions. REGISTER creates sessions on demand and each empty
// session is retained for kSessionTimeoutMs, so an uncapped table grows without bound.
// At the cap, REGISTERs for existing sessions still work; only creation is refused.
static const size_t  kMaxSessions      = 4096;

// ---- session table ----------------------------------------------------------
struct Peer {
    sockaddr_in addr{};
    bool        active     = false;
    int64_t     lastSeenMs = 0;
};
struct Session {
    Peer    slots[RELAY_MAX_SLOTS];
    int64_t lastActivityMs = 0;
};

static std::unordered_map<uint32_t, Session> g_sessions;
static SOCKET g_sock = INVALID_SOCKET;

// ---- helpers ----------------------------------------------------------------
static int64_t nowMs()
{
    using namespace std::chrono;
    return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}

static bool sameAddr(const sockaddr_in& a, const sockaddr_in& b)
{
    return a.sin_addr.s_addr == b.sin_addr.s_addr && a.sin_port == b.sin_port;
}

static const char* addrStr(const sockaddr_in& a, char* out, size_t n)
{
    char ip[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, (void*)&a.sin_addr, ip, sizeof(ip));
    snprintf(out, n, "%s:%u", ip, ntohs(a.sin_port));
    return out;
}

// True when recvfrom failed only because the SO_RCVTIMEO idle timeout elapsed:
// WSAETIMEDOUT/WSAEWOULDBLOCK on Windows, EAGAIN/EWOULDBLOCK on POSIX. Any other
// errno is a real error.
static bool recvIsIdleTimeout()
{
#ifdef _WIN32
    int e = WSAGetLastError();
    return e == WSAETIMEDOUT || e == WSAEWOULDBLOCK || e == WSAEINTR;
#else
    return errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR;
#endif
}

static void logf(const char* fmt, ...)
{
    char ts[16];
    time_t t = time(nullptr);
    struct tm tmv;
#ifdef _WIN32
    localtime_s(&tmv, &t);
#else
    localtime_r(&t, &tmv);
#endif
    strftime(ts, sizeof(ts), "%H:%M:%S", &tmv);
    printf("[%s] ", ts);
    va_list ap; va_start(ap, fmt); vprintf(fmt, ap); va_end(ap);
    printf("\n");
    fflush(stdout);
}

// ---- handlers ---------------------------------------------------------------
static void handleRegister(const uint8_t* buf, int n, const sockaddr_in& from)
{
    if (n < (int)sizeof(RelayRegister)) return;
    RelayRegister r; memcpy(&r, buf, sizeof(r));
    if (r.slot >= RELAY_MAX_SLOTS) return;

    // Session-table cap (see kMaxSessions): at the cap only REGISTERs for sessions
    // that already exist are honoured.
    if (g_sessions.size() >= kMaxSessions &&
        g_sessions.find(r.sessionId) == g_sessions.end()) {
        static int64_t lastCapLog = 0;
        int64_t t = nowMs();
        if (t - lastCapLog > 5000) {
            lastCapLog = t;
            logf("REGISTER  refused new session: at session cap (%zu)", kMaxSessions);
        }
        return;
    }

    Session& s = g_sessions[r.sessionId];   // create-on-demand
    Peer& p = s.slots[r.slot];
    bool isNew = !p.active || !sameAddr(p.addr, from);
    p.addr       = from;
    p.active     = true;
    p.lastSeenMs = nowMs();
    s.lastActivityMs = nowMs();

    // ACK so the client knows the relay is reachable.
    uint8_t ack = RELAY_REGISTER_ACK;
    sendto(g_sock, (const char*)&ack, 1, 0, (const sockaddr*)&from, sizeof(from));

    if (isNew) {
        char a[64];
        logf("REGISTER  session=%u slot=%u  %s", r.sessionId, r.slot, addrStr(from, a, sizeof(a)));
    }
}

static void handleData(uint8_t* buf, int n, const sockaddr_in& from)
{
    if (n < (int)sizeof(RelayDataHeader)) return;
    RelayDataHeader h; memcpy(&h, buf, sizeof(h));

    auto it = g_sessions.find(h.sessionId);
    if (it == g_sessions.end()) return;          // unknown session
    Session& s = it->second;

    // Verify the sender is a member; its real slot comes from its address.
    int src = -1;
    for (int i = 0; i < RELAY_MAX_SLOTS; ++i)
        if (s.slots[i].active && sameAddr(s.slots[i].addr, from)) { src = i; break; }
    if (src < 0) return;                          // not a member of this session -> drop

    s.slots[src].lastSeenMs = nowMs();
    s.lastActivityMs = nowMs();

    // Stamp the address-verified slot; receivers read srcSlot from this byte.
    buf[offsetof(RelayDataHeader, srcSlot)] = (uint8_t)src;

    if (h.destSlot == RELAY_BROADCAST) {
        for (int i = 0; i < RELAY_MAX_SLOTS; ++i)
            if (i != src && s.slots[i].active)
                sendto(g_sock, (const char*)buf, n, 0,
                       (const sockaddr*)&s.slots[i].addr, sizeof(sockaddr_in));
    } else if (h.destSlot < RELAY_MAX_SLOTS && s.slots[h.destSlot].active) {
        sendto(g_sock, (const char*)buf, n, 0,
               (const sockaddr*)&s.slots[h.destSlot].addr, sizeof(sockaddr_in));
    }
}

// Stateless latency probe: RELAY_PING is echoed back as RELAY_PONG, unchanged
// but for the type byte. Valid before any session exists; touches no session state.
static void handlePing(const uint8_t* buf, int n, const sockaddr_in& from)
{
    if (n < (int)sizeof(RelayPing)) return;
    RelayPing p; memcpy(&p, buf, sizeof(p));
    p.type = RELAY_PONG;                          // echo the nonce, flip the type
    sendto(g_sock, (const char*)&p, sizeof(p), 0, (const sockaddr*)&from, sizeof(from));
}

static void sweep()
{
    int64_t t = nowMs();
    for (auto it = g_sessions.begin(); it != g_sessions.end(); ) {
        Session& s = it->second;
        bool anyActive = false;
        for (auto& p : s.slots) {
            if (p.active && t - p.lastSeenMs > kPeerTimeoutMs) p.active = false;
            anyActive |= p.active;
        }
        if (!anyActive && t - s.lastActivityMs > kSessionTimeoutMs) {
            logf("EXPIRE    session=%u", it->first);
            it = g_sessions.erase(it);
        } else {
            ++it;
        }
    }
}

// ---- main -------------------------------------------------------------------
int main(int argc, char** argv)
{
    int port = (argc > 1) ? atoi(argv[1]) : kDefaultPort;
    if (port < 1 || port > 65535) {
        fprintf(stderr, "invalid port '%s' - using default %d\n",
                (argc > 1) ? argv[1] : "?", kDefaultPort);
        port = kDefaultPort;
    }

#ifdef _WIN32
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) { fprintf(stderr, "WSAStartup failed\n"); return 1; }
#endif

    g_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (g_sock == INVALID_SOCKET) { fprintf(stderr, "socket() failed\n"); return 1; }

#ifdef _WIN32
    // Without this, an ICMP port-unreachable from a dead peer surfaces as
    // WSAECONNRESET on a later unrelated recvfrom. Linux reports ICMP errors only on
    // connected UDP sockets, so no equivalent is needed there.
    { DWORD bytes = 0; BOOL off = FALSE;
      WSAIoctl(g_sock, SIO_UDP_CONNRESET, &off, sizeof(off),
               nullptr, 0, &bytes, nullptr, nullptr); }
#endif

    sockaddr_in bindAddr{};
    bindAddr.sin_family      = AF_INET;
    bindAddr.sin_addr.s_addr = INADDR_ANY;
    bindAddr.sin_port        = htons((uint16_t)port);
    if (bind(g_sock, (sockaddr*)&bindAddr, sizeof(bindAddr)) != 0) {
        fprintf(stderr, "bind() to UDP %d failed\n", port);
        return 1;
    }

    // Recv timeout so the loop wakes to prune even with no traffic.
#ifdef _WIN32
    DWORD tv = (DWORD)kRecvTimeoutMs;
    setsockopt(g_sock, SOL_SOCKET, SO_RCVTIMEO, (const char*)&tv, sizeof(tv));
#else
    timeval tv; tv.tv_sec = kRecvTimeoutMs / 1000; tv.tv_usec = (kRecvTimeoutMs % 1000) * 1000;
    setsockopt(g_sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
#endif

    logf("to1 relay listening on UDP %d", port);

    // Must be >= the largest datagram a client can send: sizeof(RelayDataHeader) +
    // RELAY_MAX_PAYLOAD. A smaller buffer truncates (Linux) or drops (Windows)
    // oversized datagrams.
    uint8_t buf[sizeof(RelayDataHeader) + RELAY_MAX_PAYLOAD];
    int64_t lastSweep = nowMs();

    for (;;) {
        sockaddr_in from{};
        socklen_t fromLen = sizeof(from);
        int n = recvfrom(g_sock, (char*)buf, sizeof(buf), 0, (sockaddr*)&from, &fromLen);
        if (n > 0) {
            switch (buf[0]) {
                case RELAY_REGISTER: handleRegister(buf, n, from); break;
                case RELAY_DATA:     handleData(buf, n, from);     break;
                case RELAY_PING:     handlePing(buf, n, from);     break;
                default: break;      // ignore unknown
            }
        } else if (n < 0 && !recvIsIdleTimeout()) {
            // Real socket error: log at most once per 5s, since a persistently failing
            // socket would otherwise log at loop speed.
            static int64_t lastErrLog = 0;
            int64_t t = nowMs();
            if (t - lastErrLog > 5000) {
                lastErrLog = t;
#ifdef _WIN32
                logf("RECV     error %d (continuing)", WSAGetLastError());
#else
                logf("RECV     error %d (%s) (continuing)", errno, strerror(errno));
#endif
            }
        }
        if (nowMs() - lastSweep >= kSweepIntervalMs) { sweep(); lastSweep = nowMs(); }
    }

    CLOSESOCK(g_sock);
#ifdef _WIN32
    WSACleanup();
#endif
    return 0;
}
