// ============================================================================
//  matchmaker-server.cpp  -  T2R Online matchmaker
//
//  Single-threaded, poll()-driven TCP server that groups players into matches and
//  hands each matched player a relay address plus a minted sessionId. The relay
//  creates the session on demand at REGISTER; the two programs never talk directly.
//
//  Build (Linux):   g++ -O2 -Wall -Wextra matchmaker-server.cpp -o matchmaker
//  Build (Windows): cl /O2 /EHsc matchmaker-server.cpp ws2_32.lib
//  Run:             ./matchmaker [listenPort] [relayIp] [relayPort] [timeoutSec] [relay2Ip relay2Port ...]
//                   defaults: 7001  127.0.0.1  7000  15
//                   the first relay (relayIp:relayPort) is the DEFAULT/fallback.
// ============================================================================
#define _CRT_SECURE_NO_WARNINGS
#include "matchmaker-protocol.h"
#include "relay-protocol.h"   // RELAY_PING / RELAY_PONG for server-side relay health probes

#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <cstdint>
#include <cstdarg>
#include <ctime>
#include <vector>
#include <string>
#include <map>         // session -> load-barrier deadline
#include <set>         // sessions that have already started (start-once guard)
#include <random>      // server-side random map selection
#include <algorithm>   // stable_sort for the relay-fair group former
#include <cctype>      // username validation
#include <sqlite3.h>   // account store  (build: -lsqlite3)
#include <openssl/sha.h>   // token hashing at rest
#include <openssl/rand.h>  // cryptographically-random tokens  (build: -lcrypto)
#include <cmath>

#ifdef _WIN32
  #include <winsock2.h>
  #include <ws2tcpip.h>
  #include <mstcpip.h>   // SIO_UDP_CONNRESET for the relay health-probe socket
  #ifndef SIO_UDP_CONNRESET   // some SDK header sets omit it
    #define SIO_UDP_CONNRESET _WSAIOW(IOC_VENDOR, 12)
  #endif
  #pragma comment(lib, "ws2_32.lib")
  typedef int socklen_t;
  #define CLOSESOCK closesocket
  #define poll      WSAPoll
#else
  #include <sys/socket.h>
  #include <netinet/in.h>
  #include <netinet/tcp.h>
  #include <arpa/inet.h>
  #include <poll.h>
  #include <fcntl.h>
  #include <unistd.h>
  #include <time.h>
  #include <cerrno>    // errno / EAGAIN / EWOULDBLOCK for the non-blocking send path
  #include <csignal>   // ignore SIGPIPE: a send() to a dropped client must not end the process
  typedef int SOCKET;
  #define INVALID_SOCKET (-1)
  #define CLOSESOCK close
#endif

// ---- tuning -----------------------------------------------------------------
static const int kDefaultPort     = 7001;

// Players per match, and the minimum number of eligible players required to start
// one. Capped at MM_MAX_SLOTS: the roster/spawn/team buffers and the relay slots are
// sized to it, so a larger value would overflow them.
static const int kMatchSize       = 4;     // players per match / min-to-start (2v2; assignTeams even-splits 4 -> 2+2)
static_assert(kMatchSize >= 1 && kMatchSize <= MM_MAX_SLOTS,
              "kMatchSize must be within the fixed roster/relay slot cap (MM_MAX_SLOTS)");

// Strict hold: a queued player becomes eligible to be matched only after waiting
// this long, which fills the pool before the relay pick below. Every match therefore
// takes at least this long to form.
static const uint64_t kHoldMs     = 3000;  // strict-hold window (ms)

// Match-quality floor. A group whose worst ping on the fairest relay exceeds this is
// "poor" and is deferred, but only while another searcher exists who could improve it
// and no member has waited past kPoorMatchMaxWaitMs. Past either bound it forms anyway.
// Unreachable groups (no shared relay) are not deferred: they fall straight through to
// the default-relay fallback.
// ---- two-tier forming ------------------------------------------------------
// kMatchSize above is the TARGET; a match forms as soon as the target is reachable. If
// the queue stalls, the fallback forms the largest EVEN size >= kMinMatchSize. Odd sizes
// are never formed; the odd player stays queued and seeds the next lobby.
//
// "Stalled" is a quiet timer: time since the LAST player joined that bucket, so a bucket
// that is still filling keeps waiting. kLobbyMaxMs caps total lobby age, so a steady
// trickle of joiners cannot extend a lobby indefinitely.
static const int      kMinMatchSize   = 2;       // never below this, and always even
static const uint64_t kQuietMs        = 60000;   // no new joiner for this long -> form the bucket as it stands
static const uint64_t kLobbyMaxMs     = 120000;  // hard cap on total lobby age
// The fallback path takes `have - have%2`: an odd kMinMatchSize is never reachable, and a
// minimum above the target makes the fallback unreachable.
static_assert(kMinMatchSize >= 2 && kMinMatchSize % 2 == 0,
              "kMinMatchSize must be even and at least 2 (teams are split evenly)");
static_assert(kMinMatchSize <= kMatchSize,
              "kMinMatchSize must not exceed kMatchSize (the fallback could never form)");
// The primary path takes kMatchSize verbatim (only the fallback rounds down), and
// assignTeams gives the odd player to SERAPHITES, so an odd kMatchSize forms 2v1 matches.
static_assert(kMatchSize % 2 == 0,
              "kMatchSize must be even - an odd value forms 2v1 matches (assignTeams splits (n+1)/2)");

static const long     kPingQualityCeilingMs = 150;    // worst-player ping above this = "poor"
static const uint64_t kPoorMatchMaxWaitMs   = 30000;  // accept a poor match once queued this long
// Cost added (not a hard skip) to a relay that stopped answering the matchmaker's own
// health probe but which the client group can still reach. Probe health is measured from
// the matchmaker's vantage point and can differ from a group's path to the relay, so a
// probe-down relay is deprioritised rather than excluded.
static const long     kUnhealthyRelayPenaltyMs = 120;

// Relay health. The matchmaker probes each relay over UDP (the stateless RELAY_PING the
// clients also use) and steers matches away from ones that stop answering. If EVERY relay
// looks dead, all of them are considered again so a false positive cannot stall matching.
static const uint64_t kRelayHealthPingMs = 2000;   // probe cadence per relay
static const uint64_t kRelayDeadAfterMs  = 7000;   // silent this long => treated as DOWN

// Admin telemetry (read-only control-panel feed). A second TCP listener, bound to
// loopback. On connect and then every kAdminSnapshotMs it streams a newline-delimited
// JSON snapshot of full server state. Its own port and framing, separate from the game
// protocol. Derived from the listen port (listenPort + 1) rather than fixed, so a second
// instance on the same box gets its own admin port. Release: 7001 -> 7002. Dev: 7003 -> 7004.
static int            g_adminPort      = 7002;
static const uint64_t kAdminSnapshotMs = 1000;   // snapshot cadence

// ---- canonical map list -----------------------------------------------------
// Source of truth for the map pool; clients fetch it at connect (MM_CONFIG). Each
// entry: display name, preview image path, the task to load when the match starts,
// and the number of spawn points the level packs ("to1-spawn-point-1..N"). A spawn
// count above the level's real number lets the server pick a spawn point that does
// not exist.
struct ServerMap { const char* name; const char* preview; const char* task; uint8_t spawns; };
static const ServerMap g_maps[] = {
    { "SHIPYARD",       		"streaming/menus/to1/map-pvp-shipyard.png",     	 "to1-shipyard",       	11 	},
    { "SCHOOL",       			"streaming/menus/to1/map-pvp-school.png",       	 "to1-school",         	11  },
    { "SERAPHITE CAMP",         "streaming/menus/to1/map-pvp-seraphite-camp.png",    "to1-seraphite-camp", 	9   },
    { "RESORT",      		    "streaming/menus/to1/map-pvp-resort.png",      		 "to1-resort",         	8   },
    { "GAS STATION",  			"streaming/menus/to1/map-pvp-gas-station.png",  	 "to1-gas-station",  	9   },
    { "HOUSES",      			"streaming/menus/to1/map-pvp-houses.png",       	 "to1-jesse-houses", 	10  },
//    { "FOREST",       "streaming/menus/to1/map-pvp-forest.png",       "to1-forest",       8 },
 //   { "CUSTOM MAP",   "streaming/menus/to1/map-pvp-blockmesh-1.png",  "to1-custom-map-1", 8 },
};
static const int g_mapCount = static_cast<int>(sizeof(g_maps) / sizeof(g_maps[0]));
static const int kMaxRxBytes      = 8192;  // per-client recv buffer cap
static const int kDefaultTimeoutS = 15;    // reap a client silent this long
static const uint64_t kStatusEveryMs = 30000;  // periodic status line

// Outgoing-buffer caps. Sockets are non-blocking: a blocking send to a stalled peer
// would freeze the whole single-threaded loop. Bytes that cannot be sent immediately
// queue per connection and drain on POLLOUT; a peer whose queue exceeds its cap is not
// reading and is reaped like any other broken connection.
static const size_t kMaxClientTxBytes = 256 * 1024;   // game client outgoing cap
static const size_t kMaxAdminTxBytes  = 1024 * 1024;  // admin watcher outgoing cap (~snapshots)

// Hard ceiling on concurrent game connections; each Client holds an rx/tx buffer, so
// without a cap a connect flood exhausts fds and memory. Excess connects are closed at
// accept before anything is allocated.
static const size_t kMaxClients = 512;

static uint64_t g_clientTimeoutMs = kDefaultTimeoutS * 1000ull;

// A connection must authenticate (MM_AUTH) within this window of connecting, or it is
// reaped. MM_PING satisfies the liveness reaper but does not complete auth, so without
// this an unauthenticated peer could park a socket open indefinitely.
static const uint64_t kAuthGraceMs = 10000;

// ---- state ------------------------------------------------------------------
struct Client {
    SOCKET               fd       = INVALID_SOCKET;
    std::vector<uint8_t> rx;                 // accumulates stream bytes for framing
    std::vector<uint8_t> tx;                 // outgoing bytes not yet accepted by the socket
    size_t               txOff    = 0;       // consumed prefix of tx (compacted lazily)
    uint64_t             clientId = 0;       // stable per-player id (0 = not yet seen)
    char                 name[MM_NAME_LEN]   = {0};
    uint8_t              mode     = 0;
    uint8_t              map      = 0;
    uint64_t             primaryWeapon   = 0;   // chosen primary weapon SID (0 = default)
    uint64_t             secondaryWeapon = 0;   // chosen secondary weapon SID (0 = default)
    bool                 queued   = false;   // in the matchmaking pool
    bool                 ready    = false;   // sent MM_READY: this player's match level is loaded
    bool                 dead     = false;   // flagged for removal this tick
    const char*          deadWhy  = "disconnect";
    uint32_t             session  = 0;       // match id once matched (0 = none)
    uint64_t             lastSeen = 0;       // monotonic ms of last byte received
    uint64_t             connectedAtMs = 0;  // monotonic ms at accept - drives the unauthed grace
    char                 ip[24]   = {0};     // remote IP (dotted), captured at accept - for the panel
    bool                 authed   = false;   // completed MM_AUTH: bound to an account
    long long            accountId = 0;      // account this connection is authenticated as (0 = none)
    bool                 hello    = false;   // sent MM_HELLO: present at the menu (name is known)
    int                  hwidReported = -1;
    int                  hwidMatched  = 0;
    int                  hwidAdded    = 0;
    uint8_t              hwidFlags    = 0;
    bool                 hwidMalformed = false;
    uint64_t             queuedAtMs = 0;     // queue entry time (drives the strict hold)
    // Per-relay RTT (ms) the client measured, indexed to the MM_CONFIG relay list.
    // MM_PING_UNREACHABLE = timed out / not measured. Set on every MM_QUEUE and kept
    // across a peer-left re-queue. Only read for queued clients.
    uint16_t             relayPing[MM_MAX_RELAYS] = { 0 };
    // What this player got at match formation, so the admin telemetry can describe a
    // session without a separate session table. Meaningful only while session != 0.
    uint8_t              matchSlot     = 0;
    uint8_t              matchTeam     = 0;
    uint8_t              matchSpawn    = 0;
    uint8_t              matchRelayIdx = 0;
    uint8_t              matchMap      = 0;
    uint64_t             matchFormedMs = 0;
    uint16_t             tamperMsgs    = 0;
    bool                 tamperFloodLogged = false;
};

// A connected control-panel watcher: snapshots stream out to it, newline-delimited text
// commands (account management) come in from it. rx accumulates command bytes; tx/txOff
// queue outgoing snapshot bytes for the non-blocking flush, so a slow watcher cannot
// stall the game loop.
struct AdminClient {
    SOCKET fd = INVALID_SOCKET;
    bool dead = false;
    std::vector<uint8_t> rx;
    std::vector<uint8_t> tx;
    size_t txOff = 0;
};
static std::vector<AdminClient> g_adminClients;
static SOCKET                   g_adminListen = INVALID_SOCKET;
static uint64_t                 g_bootMs      = 0;   // process start, for uptime in the snapshot

static std::vector<Client> g_clients;
// Session ids are minted by allocSessionId(): random and collision-checked rather than a
// sequential counter, so a matchmaker restart cannot reuse an id still held by a live
// relay session from before the restart.

// Live match -> its row id in the `matches` table, so ended_at can be stamped when the
// session empties. Populated at startSession, drained when the last member leaves.
static std::map<uint32_t, long long> g_matchRow;

// How many players each session was FORMED with. The two-tier former can produce a match
// smaller than kMatchSize, so startSession's shrink guard must compare against this and
// not the constant. Written by formMatch, erased everywhere g_startedSessions / g_matchRow
// are.
static std::map<uint32_t, int> g_sessionSize;
// Sessions that have already crossed START. Start-once guard: a duplicate MM_READY after
// the match began must NOT re-run startSession (double-count + duplicate history row).
// DB-independent, unlike g_matchRow.
static std::set<uint32_t> g_startedSessions;
// Lightweight live server metrics (historical stats are queried from the DB).
static uint64_t g_mMatchesStarted = 0;   // matches that reached START
static uint64_t g_mAborts         = 0;   // matches aborted during load
static int      g_mPeakConnected  = 0;   // high-water mark of concurrent connections
static uint64_t g_mQueueWaitSumMs = 0;   // sum of per-player queue waits at match time
static uint64_t g_mQueueWaitCount = 0;   // ...and the count, for the average

// Defined in the accounts/DB section below; used by startSession + the match-end sweep.
static long long matchRecordStart(uint32_t sid);
static void      matchRecordEnd(long long rowId);

// The relay pool. g_relays[0] is the DEFAULT relay: the fallback when a group shares
// no reachable relay, and the tie-break winner when relays are equally good. Additional
// relays are appended from argv. The client learns this exact list (and order) from
// MM_CONFIG and reports relayPing[i] for g_relays[i]. addr/lastPongMs/healthyLog drive
// the health check and are set up after argv parsing; parse-time aggregate init supplies
// { ip, port } only.
struct RelayCfg {
    std::string ip;
    uint16_t    port       = 0;
    sockaddr_in addr{};             // resolved once, for sending health pings
    bool        addrValid  = false;
    uint32_t    lastNonce  = 0;     // nonce of the most recent probe to this relay
    uint64_t    lastPongMs = 0;     // last time this relay answered a health ping
    bool        healthyLog = true;  // last-logged health; only transitions are logged
};
static std::vector<RelayCfg> g_relays;
static SOCKET                g_healthSock = INVALID_SOCKET;   // UDP socket for relay health probes

// Load-ready barrier. A session appears here once its first member sends MM_READY;
// the value is the deadline by which everyone must be ready, else the match aborts.
// Presence in this map also means "this session has left the lobby and is loading"
// - which flips a member dropping from "re-queue the peers" to "abort the match".
static std::map<uint32_t, uint64_t> g_loadDeadline;
static const uint64_t kLoadBarrierTimeoutMs = 120000;  // grace for the slowest loader once the first is in (2 min)

// Server-driven lobby countdown. Per match: when it formed, and the last (phase,
// countdown) broadcast, so MM_LOBBY is sent only when it changes. The timeline is
// match-found hold -> map shown -> countdown, fixed durations below.
struct LobbyTimer { uint64_t formedMs; int lastKey; };   // lastKey = phase*256+countdown, -1 = none yet
static std::map<uint32_t, LobbyTimer> g_lobby;
static const int kLobbyFoundSecs     = 2;    // "MATCH FOUND" hold before the map reveal
static const int kLobbyMapShownSecs  = 2;    // map shown before the countdown
static const int kLobbyCountdownSecs = 5;   // "STARTING IN N" 10..1, then launch

// ---- time / log -------------------------------------------------------------
static uint64_t nowMs()
{
#ifdef _WIN32
    return GetTickCount64();
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return static_cast<uint64_t>(ts.tv_sec) * 1000ull + ts.tv_nsec / 1000000ull;
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

static const char* safeName(const Client& c) { return c.name[0] ? c.name : "?"; }

// ---- low-level send ---------------------------------------------------------
static void copyStr(char* dst, size_t dstSize, const char* src)
{
    size_t i = 0;
    for (; i + 1 < dstSize && src && src[i]; ++i) dst[i] = src[i];
    for (; i < dstSize; ++i) dst[i] = 0;
}

// Did the last socket call fail only because it would block? Sockets here are
// non-blocking, so "no buffer space right now" is not an error; the bytes queue.
static bool lastErrWouldBlock()
{
#ifdef _WIN32
    return WSAGetLastError() == WSAEWOULDBLOCK;
#else
    return errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR;
#endif
}

static void setNonBlocking(SOCKET s)
{
#ifdef _WIN32
    u_long nb = 1; ioctlsocket(s, FIONBIO, &nb);
#else
    int fl = fcntl(s, F_GETFL, 0); fcntl(s, F_SETFL, fl | O_NONBLOCK);
#endif
}

// ---- non-blocking send queue ------------------------------------------------
// One writer path for every connection (game client or admin watcher): try the
// socket directly while the queue is empty, queue whatever it won't take, and
// drain the queue on POLLOUT. Frame bytes are only ever appended whole and the
// queue preserves order, so a partial send can never interleave or truncate a
// frame on the wire. Returns false on a hard error or when the peer's queue
// exceeds `cap` (it has stopped reading); the caller marks the connection dead.
static bool txQueueBytes(SOCKET fd, std::vector<uint8_t>& tx, size_t& txOff,
                         const void* data, size_t len, size_t cap)
{
    const uint8_t* p = static_cast<const uint8_t*>(data);
    size_t off = 0;

    if (tx.size() == txOff) {                       // queue empty: try the wire directly
        tx.clear(); txOff = 0;
        while (off < len) {
            int n = send(fd, reinterpret_cast<const char*>(p + off),
                         static_cast<int>(len - off), 0);
            if (n > 0) { off += static_cast<size_t>(n); continue; }
            if (n < 0 && lastErrWouldBlock()) break; // kernel buffer full: queue the rest
            return false;                            // hard error: peer is gone
        }
        if (off == len) return true;
    }

    if ((tx.size() - txOff) + (len - off) > cap) return false;   // peer stopped reading
    tx.insert(tx.end(), p + off, p + len);
    return true;
}

// Drain a connection's queue after poll() reported POLLOUT. Returns false on a
// hard send error.
static bool txFlush(SOCKET fd, std::vector<uint8_t>& tx, size_t& txOff)
{
    while (txOff < tx.size()) {
        int n = send(fd, reinterpret_cast<const char*>(tx.data() + txOff),
                     static_cast<int>(tx.size() - txOff), 0);
        if (n > 0) { txOff += static_cast<size_t>(n); continue; }
        if (n < 0 && lastErrWouldBlock()) break;
        return false;
    }
    if (txOff == tx.size()) { tx.clear(); txOff = 0; }
    else if (txOff > 65536) { tx.erase(tx.begin(), tx.begin() + txOff); txOff = 0; }
    return true;
}

// Frame and send one message: [uint16 total][type][body], total = 1 + bodyLen.
// "Sent" means accepted by the socket or queued for the POLLOUT drain. On failure
// the caller flags the client dead.
static bool sendFramed(Client& c, uint8_t type, const void* body, uint16_t bodyLen)
{
    uint8_t buf[4096];   // large enough for the match-found roster and the map config
    // Bounds-check in size_t BEFORE the uint16 arithmetic: bodyLen==0xFFFF wraps
    // `1 + bodyLen` to 0, which passes a check done on `total`.
    if (static_cast<size_t>(bodyLen) > sizeof(buf) - 3) return false;
    uint16_t total = static_cast<uint16_t>(1 + bodyLen);
    memcpy(buf, &total, 2);
    buf[2] = type;
    if (bodyLen) memcpy(buf + 3, body, bodyLen);
    return txQueueBytes(c.fd, c.tx, c.txOff, buf, static_cast<size_t>(2 + total), kMaxClientTxBytes);
}

// Queue raw bytes to an admin watcher; flags it dead on failure.
static void adminSend(AdminClient& a, const void* data, size_t len)
{
    if (a.dead) return;
    if (!txQueueBytes(a.fd, a.tx, a.txOff, data, len, kMaxAdminTxBytes)) a.dead = true;
}

// ---- match lifecycle --------------------------------------------------------
// Server-authoritative map pick. One generator for the process, seeded once.
static uint8_t pickRandomMap()
{
    static std::mt19937 rng{ std::random_device{}() };
    static std::uniform_int_distribution<int> dist(0, g_mapCount - 1);
    return static_cast<uint8_t>(dist(rng));
}

// Serialize the map list for MM_CONFIG (see matchmaker-protocol.h for the format):
//   [u8 count] then per map [u8 len][name][u8 len][preview][u8 len][task][u8 spawns].
// spawns is the per-level "to1-spawn-point-N" count; the client needs it to pick RESPAWN
// points against the real count.
static void buildConfigBody(std::vector<uint8_t>& out)
{
    out.clear();
    out.push_back(static_cast<uint8_t>(g_mapCount));
    auto putStr = [&out](const char* s) {
        size_t len = strlen(s);
        if (len > 255) len = 255;
        out.push_back(static_cast<uint8_t>(len));
        out.insert(out.end(), s, s + len);
    };
    for (int i = 0; i < g_mapCount; ++i) {
        putStr(g_maps[i].name);
        putStr(g_maps[i].preview);
        putStr(g_maps[i].task);
        out.push_back(g_maps[i].spawns);       // spawn-point count
    }

    // Append the relay list so the client can ping each relay and report the results
    // in MMQueue. [u8 relayCount] then per relay [u8 ipLen][ip][u16 port LE].
    out.push_back(static_cast<uint8_t>(g_relays.size()));
    for (const auto& r : g_relays) {
        size_t len = r.ip.size();
        if (len > 255) len = 255;
        out.push_back(static_cast<uint8_t>(len));
        out.insert(out.end(), r.ip.data(), r.ip.data() + len);
        out.push_back(static_cast<uint8_t>(r.port & 0xFF));          // little-endian, matches the wire
        out.push_back(static_cast<uint8_t>((r.port >> 8) & 0xFF));
    }
}

// ---- strict-hold + relay-fair grouping helpers ------------------------------
// A queued player is eligible to be matched only after serving the strict hold.
// Milliseconds from `stamp` to `now`, clamped at 0. Both are UNSIGNED and a stamp can lead
// `now`: the tick caches one `now` while helpers stamp with a later nowMs(). Bare
// subtraction would underflow to ~2^64 and read as "waited forever".
static uint64_t elapsedMs(uint64_t now, uint64_t stamp)
{
    return (now > stamp) ? (now - stamp) : 0;
}

static bool isRipe(const Client& c, uint64_t now)
{
    return c.queued && !c.dead && (elapsedMs(now, c.queuedAtMs) >= kHoldMs);
}

// This client's reported RTT to relay `relayIdx` (0xFFFF if out of range / unknown).
// Out-of-range relays read as unreachable so they can never be picked.
static uint16_t pingToRelay(const Client& c, int relayIdx)
{
    if (relayIdx < 0 || relayIdx >= static_cast<int>(g_relays.size()) || relayIdx >= MM_MAX_RELAYS)
        return MM_PING_UNREACHABLE;
    return c.relayPing[relayIdx];
}

// ---- relay health -----------------------------------------------------------
// A relay is healthy if it answered a probe within kRelayDeadAfterMs. A relay that
// cannot be probed (its ip is not a dotted IPv4, so addrValid is false) counts as
// healthy: clients get the raw ip string regardless, so it must stay eligible.
static bool relayHealthy(const RelayCfg& r, uint64_t now)
{
    return !r.addrValid || (now - r.lastPongMs) < kRelayDeadAfterMs;
}
static bool anyRelayHealthy(uint64_t now)
{
    for (const auto& r : g_relays) if (relayHealthy(r, now)) return true;
    return false;
}

// How many queued (not necessarily eligible) players share this (mode,map). The
// match-quality gate defers a poor match only while another searcher here could ripen
// into a better partner, so not-yet-ripe newcomers count as prospects.
static int queuedInBucket(uint8_t mode, uint8_t map)
{
    int n = 0;
    for (const auto& c : g_clients)
        if (c.queued && !c.dead && c.mode == mode && c.map == map) ++n;
    return n;
}

// The most recent queue stamp in this (mode,map), counting EVERY searcher including ones
// still inside the kHoldMs hold. Returns 0 if nobody is queued here.
//
// bucketStalled's QUIET trigger must use this rather than the ripe-filtered bucket it is
// handed: a player inside the hold is not in that bucket, so "nobody joined recently"
// could read true while somebody was joining, and a fallback match would form without them.
static uint64_t newestQueueStampInBucket(uint8_t mode, uint8_t map)
{
    uint64_t newest = 0;
    for (const auto& c : g_clients)
        if (c.queued && !c.dead && c.mode == mode && c.map == map && c.queuedAtMs > newest)
            newest = c.queuedAtMs;
    return newest;
}

// Assign each player in a forming match a UNIQUE spawn point (1..spawnCount),
// shuffled so the choice is random and no two players share one. out[k] is slot
// k's spawn point number; 0 means "no spawn" (only if the map has fewer points
// than players, which shouldn't happen with a correctly-configured spawn count).
static void assignSpawns(uint8_t spawnCount, size_t players, uint8_t out[])
{
    static std::mt19937 rng{ std::random_device{}() };
    std::vector<uint8_t> pool;
    // int induction variable: with uint8_t, a spawnCount of 255 makes `s <= spawnCount`
    // a tautology (s wraps 255 -> 0) and this loop never terminates.
    for (int s = 1; s <= spawnCount; ++s) pool.push_back(static_cast<uint8_t>(s));
    for (size_t i = pool.size(); i > 1; --i) {            // Fisher-Yates shuffle
        std::uniform_int_distribution<size_t> d(0, i - 1);
        size_t  j = d(rng);
        uint8_t t = pool[i - 1]; pool[i - 1] = pool[j]; pool[j] = t;
    }
    for (size_t k = 0; k < players; ++k)
        out[k] = (k < pool.size()) ? pool[k] : 0;
}

// Split the forming match evenly into two teams. out[k] is slot k's team
// (MM_TEAM_SERAPHITES = 0 or MM_TEAM_WLF = 1). An even player count gives each team the
// same number; an odd count differs by one, and the extra player goes to SERAPHITES.
// Which players land on each side is random per match.
//
// The slot list is shuffled (same Fisher-Yates as assignSpawns) rather than each slot
// randomised independently: a per-slot coin flip would not keep the sides even.
static void assignTeams(size_t players, uint8_t out[])
{
    static std::mt19937 rng{ std::random_device{}() };

    std::vector<size_t> order;
    order.reserve(players);
    for (size_t k = 0; k < players; ++k) order.push_back(k);

    for (size_t i = order.size(); i > 1; --i) {            // Fisher-Yates shuffle
        std::uniform_int_distribution<size_t> d(0, i - 1);
        size_t j = d(rng);
        size_t t = order[i - 1]; order[i - 1] = order[j]; order[j] = t;
    }

    const size_t half = (players + 1) / 2;                 // extra player (odd counts) -> SERAPHITES
    for (size_t i = 0; i < order.size(); ++i)
        out[order[i]] = (i < half) ? static_cast<uint8_t>(MM_TEAM_SERAPHITES)
                                   : static_cast<uint8_t>(MM_TEAM_WLF);
}

// Allocate a fresh, non-zero session id that collides with no session this process
// currently knows about. Cryptographically random, not a counter: a counter resets on
// restart and could mint an id a still-live relay session is using, which strands that
// match's players (the relay overwrites their host slot) and leaks packets across the two
// matches. The relay treats sessionId as an opaque token; nothing requires it to be
// sequential.
static uint32_t allocSessionId()
{
    for (int tries = 0; tries < 10000; ++tries) {
        uint32_t sid = 0;
        if (RAND_bytes(reinterpret_cast<unsigned char*>(&sid), sizeof(sid)) != 1)
            sid = static_cast<uint32_t>(nowMs());        // CSPRNG unavailable: time-based fallback
        if (sid == 0) continue;                          // 0 is reserved for "no session"
        if (g_startedSessions.count(sid) || g_matchRow.count(sid) ||
            g_loadDeadline.count(sid)    || g_lobby.count(sid) ||
            g_sessionSize.count(sid))
            continue;
        bool inUse = false;
        for (const Client& c : g_clients)
            if (c.session == sid) { inUse = true; break; }
        if (!inUse) return sid;
    }
    return static_cast<uint32_t>(nowMs()) | 1u;          // pathological fallback (never expected)
}

// Form a match from `group` on relay `relayIdx` (chosen by the caller to minimise
// the group's worst ping). `worstPing` is that worst ping, for the log only.
static void formMatch(const std::vector<size_t>& group, int relayIdx, long worstPing)
{
    uint32_t sid   = allocSessionId();
    uint8_t  count = static_cast<uint8_t>(group.size());
    uint8_t  map   = pickRandomMap();   // the matchmaker owns the map; everyone in this match gets it

    // The relay everyone in this match dials. relayIdx is always valid (the former
    // only proposes configured relays; index 0 is the default fallback).
    const RelayCfg& relay = g_relays[relayIdx];

    uint8_t spawnFor[MM_MAX_SLOTS];     // unique spawn point per slot, chosen server-side
    assignSpawns(g_maps[map].spawns, group.size(), spawnFor);

    uint8_t teamFor[MM_MAX_SLOTS];      // even team split, chosen server-side (0 = SERAPHITES, 1 = WLF)
    assignTeams(group.size(), teamFor);

    // Remember the formed size for startSession's shrink guard.
    g_sessionSize[sid] = static_cast<int>(group.size());

    for (size_t k = 0; k < group.size(); ++k) {
        Client& c = g_clients[group[k]];

        uint8_t body[sizeof(MMMatchFound) + MM_MAX_SLOTS * sizeof(MMRosterEntry)];
        MMMatchFound mf;
        memset(&mf, 0, sizeof(mf));
        copyStr(mf.relayIp, sizeof(mf.relayIp), relay.ip.c_str());
        mf.relayPort   = relay.port;
        mf.sessionId   = sid;
        mf.map         = map;
        mf.yourSlot    = static_cast<uint8_t>(k);
        mf.playerCount = count;
        mf.yourSpawn   = spawnFor[k];   // this player's unique spawn point
        mf.yourTeam    = teamFor[k];    // this player's team (SERAPHITES / WLF)
        memcpy(body, &mf, sizeof(mf));

        uint8_t* p = body + sizeof(mf);
        for (size_t r = 0; r < group.size(); ++r) {
            MMRosterEntry e;
            memset(&e, 0, sizeof(e));
            e.slot = static_cast<uint8_t>(r);
            copyStr(e.name, sizeof(e.name), g_clients[group[r]].name);
            e.primaryWeapon   = g_clients[group[r]].primaryWeapon;
            e.secondaryWeapon = g_clients[group[r]].secondaryWeapon;
            e.team            = teamFor[r];     // everyone learns everyone's team
            memcpy(p, &e, sizeof(e));
            p += sizeof(e);
        }

        uint16_t bodyLen = static_cast<uint16_t>(p - body);
        if (!sendFramed(c, MM_MATCH_FOUND, body, bodyLen)) {
            c.dead = true; c.deadWhy = "send failed";
        }
        c.queued  = false;
        c.session = sid;
        c.ready   = false;   // fresh load barrier: never inherit a prior match's READY (else this
                             // match starts while a re-queued player is still loading the new map)
        // Remember what this player got, for the admin telemetry.
        c.matchSlot     = static_cast<uint8_t>(k);
        c.matchTeam     = teamFor[k];
        c.matchSpawn    = spawnFor[k];
        c.matchRelayIdx = static_cast<uint8_t>(relayIdx);
        c.matchMap      = map;
        c.matchFormedMs = nowMs();
        // Metric: how long this player waited to be matched. The guard is arithmetic
        // safety (never record a negative wait).
        if (c.queuedAtMs != 0 && c.matchFormedMs >= c.queuedAtMs) {
            g_mQueueWaitSumMs += c.matchFormedMs - c.queuedAtMs;
            ++g_mQueueWaitCount;
        }
    }

    {
        char sp[80]; int off = 0;
        for (size_t k = 0; k < group.size() && off < static_cast<int>(sizeof(sp)) - 8; ++k)
            off += snprintf(sp + off, sizeof(sp) - off, "%s%u", k ? "," : "", spawnFor[k]);
        logf("MATCH    session=%u size=%u map=%u spawns=[%s] (mode=%u)",
             sid, count, map, sp, g_clients[group[0]].mode);
    }

    // Which relay this match got, and the worst player's ping on it.
    if (worstPing >= MM_PING_UNREACHABLE)
        logf("RELAY    session=%u -> relay#%d %s:%u (no shared reachable relay; default)",
             sid, relayIdx, relay.ip.c_str(), relay.port);
    else
        logf("RELAY    session=%u -> relay#%d %s:%u (worst ping %ldms)",
             sid, relayIdx, relay.ip.c_str(), relay.port, worstPing);

    // Team split - log who landed on each side.
    {
        std::string seraph, wlf;
        for (size_t k = 0; k < group.size(); ++k) {
            std::string& side = (teamFor[k] == MM_TEAM_WLF) ? wlf : seraph;
            if (!side.empty()) side += ", ";
            side += safeName(g_clients[group[k]]);
        }
        logf("TEAMS    session=%u  SERAPHITES: %s  |  WLF: %s",
             sid, seraph.empty() ? "-" : seraph.c_str(), wlf.empty() ? "-" : wlf.c_str());
        for (size_t k = 0; k < group.size(); ++k)
            logf("TEAM     session=%u slot=%zu \"%s\" -> %s",
                 sid, k, safeName(g_clients[group[k]]), MMTeamName(teamFor[k]));
    }

    g_lobby[sid] = { nowMs(), -1 };   // start the server-driven lobby countdown
}

// Strict-hold, relay-fair group former. Each pass forms the single best match available
// among ELIGIBLE (held long enough) players that share a (mode,map), then repeats until
// no group can be assembled.
//
// "Best" = lowest achievable worst-player ping. For a candidate relay r the best group is
// the eligible players with the lowest ping to r; that group's cost is the WORST of their
// pings. Every relay and every (mode,map) bucket is tried and the lowest cost kept. Ties
// go to the lower relay index, so the default relay (0) wins when relays are equally good.
// An unknown/unreachable ping is the max value, so a group that can reach no relay has an
// equal cost everywhere and forms on the default relay.
//
// Two refinements layer on top:
//   relay health  - a relay that stopped answering the server's health probe is
//                   deprioritised. If NO relay looks healthy, all of them are considered
//                   again so a false positive cannot stop matchmaking.
//   quality floor - a best cost above kPingQualityCeilingMs is "poor" and is deferred, but
//                   only while another searcher in the bucket could still improve it AND no
//                   member has waited past kPoorMatchMaxWaitMs. Unreachable groups are not
//                   deferred; they take the default-relay fallback.
// Has this bucket stopped filling? Two independent triggers:
//   QUIET  - nobody has joined for kQuietMs, measured from the NEWEST member's queue time.
//   AGE    - the oldest member has been waiting past kLobbyMaxMs, so a steady trickle of
//            joiners (each resetting the quiet timer) cannot hold the lobby open forever.
//
// Every member carries a real queue stamp, so both triggers are plain elapsed-time tests
// over elapsedMs.
//
// The two triggers read different populations:
//   QUIET reads EVERY searcher in the (mode,map), including ones still inside the hold.
//   AGE   reads only the ripe bucket: a non-ripe player is the youngest here and could
//         never be the oldest member.
static bool bucketStalled(const std::vector<size_t>& bucket, uint64_t now,
                          uint8_t mode, uint8_t map)
{
    if (bucket.empty()) return false;

    uint64_t oldest = UINT64_MAX; // smallest queuedAtMs == longest waiting
    for (size_t idx : bucket) {
        const uint64_t q = g_clients[idx].queuedAtMs;
        if (q < oldest) oldest = q;
    }
    const uint64_t newest = newestQueueStampInBucket(mode, map);   // includes non-ripe joiners

    const bool quiet   = elapsedMs(now, newest) >= kQuietMs;     // nobody joined recently
    const bool tooOld  = elapsedMs(now, oldest) >= kLobbyMaxMs;  // someone has waited too long
    return quiet || tooOld;
}

// ---------------------------------------------------------------------------
//  MM_LOBBY_ROSTER - names of everyone searching in the same bucket
//
// Sends the names of everyone currently queued in the SAME bucket (same mode+map), on a
// timer rather than on membership change, so a name can lag by up to kLobbyRosterMs.
//
// Includes the recipient's own name: the client draws itself in slot 0 from its local
// username and skips the first entry matching it, as the MM_MATCH_FOUND path does.
static const uint64_t kLobbyRosterMs = 1000;   // broadcast cadence

static void pumpLobbyRosters(uint64_t now)
{
    static uint64_t lastSend = 0;
    if (now - lastSend < kLobbyRosterMs) return;
    lastSend = now;

    for (auto& c : g_clients) {
        if (c.dead || !c.queued || c.session != 0) continue;   // only players still searching

        // Everyone queued in the same bucket. Ripeness is irrelevant: this is a display
        // of who is present, not who is matchable.
        std::vector<uint8_t> body;
        body.push_back(0);                                     // count, patched below
        uint8_t count = 0;
        for (auto& o : g_clients) {
            if (o.dead || !o.queued || o.session != 0) continue;
            if (o.mode != c.mode || o.map != c.map) continue;
            if (count >= MM_MAX_SLOTS) break;
            size_t len = strnlen(o.name, sizeof(o.name));
            if (len > 255) len = 255;
            body.push_back(static_cast<uint8_t>(len));
            body.insert(body.end(), o.name, o.name + len);
            ++count;
        }
        body[0] = count;
        // Reap on a failed send, so a client that dropped its socket while searching is
        // cleaned up this tick instead of lingering in the queue and in everyone else's
        // lobby list.
        if (!sendFramed(c, MM_LOBBY_ROSTER, body.data(), static_cast<uint16_t>(body.size()))) {
            c.dead = true; c.deadWhy = "send failed";
        }
    }
}

static void tryFormMatches(uint64_t now)
{
    for (;;) {
        // The eligible pool: queued, alive, past the hold.
        std::vector<size_t> pool;
        for (size_t i = 0; i < g_clients.size(); ++i)
            if (isRipe(g_clients[i], now)) pool.push_back(i);
        if (static_cast<int>(pool.size()) < kMinMatchSize) break;  // can't even make the smallest

        bool healthyExists = anyRelayHealthy(now);   // is any relay currently up?

        long                bestCost  = 0;    // valid only once bestRelay >= 0
        int                 bestRelay = -1;
        int                 bestTake  = 0;    // size of the winning group (sizes can differ)
        std::vector<size_t> bestGroup;

        for (size_t a = 0; a < pool.size(); ++a) {
            uint8_t mode = g_clients[pool[a]].mode, map = g_clients[pool[a]].map;

            // Consider each (mode,map) bucket once - skip if an earlier anchor already had it.
            bool already = false;
            for (size_t b = 0; b < a; ++b)
                if (g_clients[pool[b]].mode == mode && g_clients[pool[b]].map == map) { already = true; break; }
            if (already) continue;

            std::vector<size_t> bucket;
            for (size_t idx : pool)
                if (g_clients[idx].mode == mode && g_clients[idx].map == map) bucket.push_back(idx);
            if (static_cast<int>(bucket.size()) < kMinMatchSize) continue;

            // How many to take from this bucket this pass:
            //   full target reachable  -> take the target, immediately
            //   otherwise              -> only if the lobby has stalled, and then the largest
            //                             reachable EVEN count
            const int have = static_cast<int>(bucket.size());
            int take = 0;
            if (have >= kMatchSize) {
                take = kMatchSize;                       // full lobby: go now, no waiting
            }
            else if (bucketStalled(bucket, now, mode, map)) {
                take = have - (have % 2);                // largest even <= have
                if (take < kMinMatchSize) continue;      // 1 player left over: keep waiting
            }
            else {
                continue;                                // still filling - give it time
            }

            // Is there another searcher here who could still improve a poor match?
            // (all queued in this bucket, ripe or not, beyond the players a match needs)
            bool prospects = queuedInBucket(mode, map) > take;
            // Has anyone in this bucket waited past the patience bound? Past it, poor
            // matches stop being deferred here and the best available forms, so a laggy
            // player who can never be in the lowest-ping pair still leaves the queue.
            bool patienceExpired = false;
            for (size_t idx : bucket)
                if (elapsedMs(now, g_clients[idx].queuedAtMs) >= kPoorMatchMaxWaitMs) { patienceExpired = true; break; }

            for (int r = 0; r < static_cast<int>(g_relays.size()); ++r) {
                // Order this bucket by ping to relay r (asc); tie-break the earlier
                // queuer, then lower index, so the choice is deterministic and favours
                // who has waited longest. Done BEFORE the health check, which consults
                // the group's own reachability to relay r.
                std::vector<size_t> byPing = bucket;
                std::stable_sort(byPing.begin(), byPing.end(), [&](size_t x, size_t y) {
                    uint16_t px = pingToRelay(g_clients[x], r), py = pingToRelay(g_clients[y], r);
                    if (px != py) return px < py;
                    if (g_clients[x].queuedAtMs != g_clients[y].queuedAtMs)
                        return g_clients[x].queuedAtMs < g_clients[y].queuedAtMs;
                    return x < y;
                });
                // Cost = worst ping among the `take` lowest.
                long cost = pingToRelay(g_clients[byPing[take - 1]], r);

                // Relay health is a SOFT preference, not a hard exclusion: probe health is
                // measured from the matchmaker's vantage point, which can differ from this
                // group's path to the relay. A probe-down relay is hard-skipped only when the
                // group also cannot reach it (their worst ping is unreachable); otherwise it
                // stays a candidate with a penalty, so a probe-healthy relay wins when pings
                // are close.
                if (healthyExists && !relayHealthy(g_relays[r], now)) {
                    if (cost >= MM_PING_UNREACHABLE) continue;   // group can't reach it either -> truly skip
                    cost = std::min<long>(cost + kUnhealthyRelayPenaltyMs, MM_PING_UNREACHABLE - 1);
                }

                // Quality gate. "poor" = reachable but above the ceiling; an unreachable
                // group is NOT poor and takes the fallback immediately. Defer a poor match
                // only while a better partner might still come AND nobody here has run out
                // of patience.
                bool poor = (cost > kPingQualityCeilingMs) && (cost < MM_PING_UNREACHABLE);
                if (poor && prospects && !patienceExpired) continue;   // hold out for something better

                // SIZE FIRST, then cost. Candidate groups differ in size and a bigger match
                // always beats a smaller one, so a stalled fallback group never forms in
                // place of a full-size group waiting in another bucket. Within one bucket
                // `take` is constant, so this falls through to the cost test: strictly-lower
                // replaces, so the FIRST (lowest-index) relay achieving the minimum wins the
                // tie and the default relay is preferred when equal.
                if (bestRelay < 0 || take > bestTake || (take == bestTake && cost < bestCost)) {
                    bestCost  = cost;
                    bestRelay = r;
                    bestTake  = take;
                    bestGroup.assign(byPing.begin(), byPing.begin() + take);
                }
            }
        }

        if (bestRelay < 0) break;   // nothing formable this pass (no group, or all deferred)
        formMatch(bestGroup, bestRelay, bestCost);
    }
}

// Re-queue every live member of session `sid` except `leaver`; tell each it is
// searching again (fresh MM_QUEUED). Returns how many were re-queued.
static int requeueSessionPeers(uint32_t sid, const Client* leaver)
{
    if (sid == 0) return 0;
    int requeued = 0;
    for (auto& o : g_clients) {
        if (&o == leaver || o.dead || o.session != sid) continue;
        o.session = 0;
        o.queued  = true;
        // A re-queued survivor gets a real stamp, identical to one from an MM_QUEUE sent
        // now: every elapsed-time test in the former measures `now - queuedAtMs`, and a
        // sentinel of 0 reads as "waiting since the epoch", permanently tripping
        // bucketStalled's AGE trigger and kPoorMatchMaxWaitMs. The survivor therefore
        // re-serves the kHoldMs hold.
        o.queuedAtMs = nowMs();
        if (!sendFramed(o, MM_QUEUED, nullptr, 0)) { o.dead = true; o.deadWhy = "send failed"; }
        ++requeued;
    }
    return requeued;
}

// THE single dissolve path. If `c` is in a match, re-queue every other member
// and clear c's session. Used by cancel, disconnect, timeout, and replacement.
static int leaveMatch(Client& c, const char* reason)
{
    if (c.session == 0) return 0;
    uint32_t sid = c.session;
    c.session = 0;
    int n = requeueSessionPeers(sid, &c);
    g_lobby.erase(sid);       // lobby is moot; the match dissolved
    g_sessionSize.erase(sid); // ...and its formed size: this is the dissolve path for a lobby
                              // that breaks up before any READY
    logf("LEAVE    %s (%s) session=%u -> %d re-queued", safeName(c), reason, sid, n);
    return n;
}

// ---- load-ready barrier -----------------------------------------------------
// Count the live (non-dead) members of a session, and how many are ready.
static int countSession(uint32_t sid)
{
    int n = 0;
    for (auto& c : g_clients) if (c.session == sid && !c.dead) ++n;
    return n;
}
static int countSessionReady(uint32_t sid)
{
    int n = 0;
    for (auto& c : g_clients) if (c.session == sid && !c.dead && c.ready) ++n;
    return n;
}

// Everyone in the session is loaded -> the single authoritative "go". Broadcast
// MM_START and close the barrier; the match is now live. Idempotent: a duplicate call
// (e.g. a re-sent MM_READY) is ignored, so nothing is double-recorded or double-counted.
static void startSession(uint32_t sid)
{
    if (g_startedSessions.count(sid)) return;   // already started - do this exactly once
    // Full-roster guard: a match whose live roster has shrunk below the size it was FORMED
    // with does not start. A peer's socket-close can be marked dead in the same tick as the
    // survivor's MM_READY, and countSession/countSessionReady both exclude the dead peer.
    // Bailing here leaves g_loadDeadline set, so the deferred memberGone(deadPeer) takes the
    // abort path: MM_ABORT to the survivor, no history row.
    // The comparison is against the formed size, not kMatchSize, because the two-tier former
    // can commit a match smaller than kMatchSize. A missing entry falls back to kMatchSize;
    // formMatch always writes one.
    {
        auto szIt = g_sessionSize.find(sid);
        const int formedWith = (szIt != g_sessionSize.end()) ? szIt->second : kMatchSize;
        if (countSession(sid) < formedWith) return;
    }
    g_startedSessions.insert(sid);
    g_lobby.erase(sid);   // a started session must never keep ticking as a lobby
                          // (pumpLobbies would re-arm a stale load deadline)

    int told = 0;
    for (auto& c : g_clients) {
        if (c.session != sid || c.dead) continue;
        if (!sendFramed(c, MM_START, nullptr, 0)) { c.dead = true; c.deadWhy = "send failed"; }
        ++told;
    }
    g_loadDeadline.erase(sid);
    logf("START    session=%u -> %d players go", sid, told);

    // The match is live: record it in history and count it. The row is stamped ended_at
    // when the session empties (see the match-end sweep in the main loop).
    ++g_mMatchesStarted;
    long long row = matchRecordStart(sid);
    if (row) g_matchRow[sid] = row;
}

// A committed match fell apart during loading. Tell every remaining member to bail to
// the MP main menu and clear the session; they are NOT re-queued, having left the lobby.
// `except` is skipped (the member whose drop triggered this, already being removed).
static void abortSession(uint32_t sid, const char* why, const Client* except)
{
    if (sid == 0) return;
    int told = 0;
    for (auto& c : g_clients) {
        if (c.session != sid) continue;
        if (&c != except && !c.dead) {
            if (!sendFramed(c, MM_ABORT, nullptr, 0)) { c.dead = true; c.deadWhy = "send failed"; }
            ++told;
        }
        c.session = 0;
        c.ready   = false;
        c.queued  = false;          // back to idle on the menu, not the queue
    }
    g_loadDeadline.erase(sid);
    g_lobby.erase(sid);
    ++g_mAborts;
    // If the match had already been recorded as started, close its history row now.
    auto it = g_matchRow.find(sid);
    if (it != g_matchRow.end()) { matchRecordEnd(it->second); g_matchRow.erase(it); }
    g_startedSessions.erase(sid);
    g_sessionSize.erase(sid);
    logf("ABORT    session=%u (%s) -> %d players to menu", sid, why, told);
}

// A STARTED (live) match lost a member. Unlike a pre-start lobby, the survivors must NOT
// be re-queued: back in the pool, the same tick's former can pair a survivor into an
// involuntary rematch and fire a phantom MATCH FOUND at whoever is waiting in the queue.
// Instead the match ends and each survivor goes back to the MP menu idle. MM_QUEUED flips
// the client to Searching, which its in-match / load state machine reads as "the match
// ended" and bails to the MP main menu (net-gui2); queued=false server-side so the former
// can never pick a survivor before it leaves. The history row and g_startedSessions entry
// are closed by the main-loop match-end sweep once the session has emptied
// (countSession==0). The host reports MM_RESULT before the scoreboard/cancel, so on a
// normal end the winner is already recorded when this runs.
static void endLiveMatch(Client& leaver, const char* reason)
{
    uint32_t sid = leaver.session;
    int told = 0;
    for (auto& o : g_clients) {
        if (o.session != sid) continue;
        o.session = 0;
        o.queued  = false;   // idle on the menu, NOT re-queued -> never instantly-ripe / auto-rematched
        o.ready   = false;
        if (&o != &leaver && !o.dead) {
            if (!sendFramed(o, MM_QUEUED, nullptr, 0)) { o.dead = true; o.deadWhy = "send failed"; }
            ++told;
        }
    }
    g_lobby.erase(sid);
    logf("ENDLIVE  %s (%s) session=%u -> %d players to menu", safeName(leaver), reason, sid, told);
}

// A member left/dropped (cancel, disconnect, timeout). Which teardown depends on the phase:
//   - loading (in g_loadDeadline): the match is committed but not yet live -> abort it for all.
//   - started (in g_startedSessions): the match is live -> end it; survivors go idle to the menu.
//   - otherwise (pre-load lobby): re-queue the survivors so they can immediately re-match.
static void memberGone(Client& c, const char* reason)
{
    if (c.session == 0) return;
    if      (g_loadDeadline.count(c.session))    abortSession(c.session, reason, &c);
    else if (g_startedSessions.count(c.session)) endLiveMatch(c, reason);
    else                                         leaveMatch(c, reason);
}

// Server-driven lobby countdown. Each tick, recompute (phase, countdown) from how
// long ago the match formed and broadcast MM_LOBBY to the match whenever it changes,
// so every member renders the same value. The fixed timeline:
//   [0, kLobbyFoundSecs)                          -> phase 0 (match-found hold)
//   [.., +kLobbyMapShownSecs)                     -> phase 1 (map shown)
//   [.., +kLobbyCountdownSecs) countdown 10..1    -> phase 2
//   at the end: phase 2 / countdown 0             -> launch cue, then the lobby ends
static void pumpLobbies(uint64_t now)
{
    for (auto it = g_lobby.begin(); it != g_lobby.end(); ) {
        uint32_t sid = it->first;
        // formedMs is stamped in formMatch with a nowMs() sampled LATER than this loop's `now`,
        // so on the first pump of a just-formed lobby formedMs can exceed now. These are
        // unsigned, so (now - formedMs) would UNDERFLOW and elapsed would read as "past the
        // whole countdown", firing the launch cue immediately. Clamp to 0 so a fresh lobby
        // starts at phase 0.
        int elapsed  = (now <= it->second.formedMs)
                         ? 0
                         : static_cast<int>((now - it->second.formedMs) / 1000);

        uint8_t phase, cd;
        if (elapsed < kLobbyFoundSecs)                            { phase = 0; cd = 0; }
        else if (elapsed < kLobbyFoundSecs + kLobbyMapShownSecs)  { phase = 1; cd = 0; }
        else {
            int into = elapsed - (kLobbyFoundSecs + kLobbyMapShownSecs);   // 0..kLobbyCountdownSecs
            phase = 2;
            cd = (into < kLobbyCountdownSecs)
                     ? static_cast<uint8_t>(kLobbyCountdownSecs - into)    // 10..1
                     : 0;                                                  // launch
        }

        int key = phase * 256 + cd;
        if (key != it->second.lastKey) {
            it->second.lastKey = key;
            MMLobby body{ phase, cd };
            for (auto& c : g_clients)
                if (c.session == sid && !c.dead &&
                    !sendFramed(c, MM_LOBBY, &body, sizeof(body)))
                    { c.dead = true; c.deadWhy = "send failed"; }
        }

        if (phase == 2 && cd == 0) {        // launch cue sent -> the lobby is done
            // Armed at load START rather than on the first MM_READY, so the load-timeout
            // sweep covers a session where NOBODY readies (a shared load failure, e.g. a
            // bad map task id) and which is therefore in no other timed structure.
            if (!g_loadDeadline.count(sid))
                g_loadDeadline[sid] = now + kLoadBarrierTimeoutMs;
            it = g_lobby.erase(it);         // (the load barrier takes over from here)
        } else {
            ++it;
        }
    }
}

// Refuse a client: version mismatch or an invalid/banned token. Carries the server
// version and the reason; the client shows it and disconnects.
static void sendReject(Client& c, uint8_t reason = MM_REJECT_VERSION)
{
    MMReject body{ reason, static_cast<uint8_t>(MM_PROTOCOL_VERSION) };
    sendFramed(c, MM_REJECT, &body, sizeof(body));
}

// ---- relay health probing ---------------------------------------------------
// Fire one RELAY_PING at every probeable relay (the same stateless probe the clients
// use), each stamped with a fresh, distinct nonce. The pong echoes that nonce, which
// identifies the answering relay. Matching by nonce rather than source address survives
// a multi-homed relay replying from a different egress IP, and two relays sharing a port
// on different IPs.
static void sendHealthPings()
{
    if (g_healthSock == INVALID_SOCKET) return;
    static uint32_t nonce = 1;
    for (auto& r : g_relays) {
        if (!r.addrValid) continue;
        r.lastNonce = nonce++;
        if (nonce == 0) nonce = 1;                          // never hand out 0
        RelayPing p; p.type = RELAY_PING; p.nonce = r.lastNonce;
        sendto(g_healthSock, reinterpret_cast<const char*>(&p), sizeof(p), 0,
               reinterpret_cast<const sockaddr*>(&r.addr), sizeof(r.addr));
    }
}

// Drain any RELAY_PONGs and stamp the answering relay alive, matched by the echoed
// nonce. Non-blocking; returns as soon as the socket is empty. A stale pong (nonce
// from a prior round) matches nothing and is ignored.
static void drainHealthPongs(uint64_t now)
{
    if (g_healthSock == INVALID_SOCKET) return;
    for (;;) {
        sockaddr_in from; socklen_t fl = sizeof(from);
        uint8_t buf[64];
        int n = recvfrom(g_healthSock, reinterpret_cast<char*>(buf), sizeof(buf), 0,
                         reinterpret_cast<sockaddr*>(&from), &fl);
        if (n < 0) break;                                   // EWOULDBLOCK: nothing more pending
        if (n < static_cast<int>(sizeof(RelayPing))) continue;
        RelayPing p; memcpy(&p, buf, sizeof(p));
        if (p.type != RELAY_PONG) continue;
        for (auto& r : g_relays)
            if (r.addrValid && r.lastNonce == p.nonce) { r.lastPongMs = now; break; }
    }
}

// Log health transitions (UP <-> DOWN) so relay outages are visible on the console.
static void logHealthTransitions(uint64_t now)
{
    for (size_t i = 0; i < g_relays.size(); ++i) {
        bool h = relayHealthy(g_relays[i], now);
        if (h != g_relays[i].healthyLog) {
            g_relays[i].healthyLog = h;
            logf("RELAY    relay#%zu %s:%u is now %s", i,
                 g_relays[i].ip.c_str(), g_relays[i].port, h ? "UP" : "DOWN");
        }
    }
}

// ---- admin telemetry (read-only control-panel feed) -------------------------
// Minimal JSON writer (fixed, small schema - no dependency). Emits no raw newline,
// so snapshots are safely newline-delimited on the wire.
static void jEsc(std::string& o, const char* s)
{
    for (; s && *s; ++s) {
        unsigned char ch = static_cast<unsigned char>(*s);
        switch (ch) {
            case '"':  o += "\\\""; break;
            case '\\': o += "\\\\"; break;
            case '\n': o += "\\n";  break;
            case '\r': o += "\\r";  break;
            case '\t': o += "\\t";  break;
            default:
                if (ch < 0x20) { char b[8]; snprintf(b, sizeof(b), "\\u%04x", ch); o += b; }
                else o += static_cast<char>(ch);
        }
    }
}
static void jStr(std::string& o, const char* s) { o += '"'; jEsc(o, s); o += '"'; }

// ---- accounts (SQLite-backed) -----------------------------------------------
// Identity = an admin-created account (unique username) plus a random token delivered
// to the player in tlou-ii-mp.json. Only sha256(token) is stored. One active token per
// account; regen invalidates the old one. All queries use bound parameters.
static sqlite3* g_db = nullptr;

static std::string toHex(const unsigned char* p, size_t n) {
    static const char* H = "0123456789abcdef";
    std::string s; s.reserve(n * 2);
    for (size_t i = 0; i < n; ++i) { s += H[p[i] >> 4]; s += H[p[i] & 0xF]; }
    return s;
}
static std::string sha256Hex(const std::string& in) {
    unsigned char d[SHA256_DIGEST_LENGTH];
    SHA256(reinterpret_cast<const unsigned char*>(in.data()), in.size(), d);
    return toHex(d, sizeof(d));
}
// A fresh 256-bit token as 64 hex chars; empty on RNG failure (caller must abort).
static std::string genToken() {
    unsigned char r[32];
    if (RAND_bytes(r, sizeof(r)) != 1) return std::string();
    return toHex(r, sizeof(r));
}
// Usernames: 1..24 chars, [A-Za-z0-9_-] only. No spaces: the admin command line splits
// on them. Uniqueness is case-insensitive (COLLATE NOCASE).
static bool validUsername(const std::string& u) {
    if (u.empty() || u.size() > 24) return false;
    for (char ch : u)
        if (!(std::isalnum(static_cast<unsigned char>(ch)) || ch == '_' || ch == '-')) return false;
    return true;
}

// One-time migration to AUTOINCREMENT account ids. A bare INTEGER PRIMARY KEY lets
// SQLite REUSE the id of a deleted account (max(rowid)+1), and match_players rows
// survive an account's deletion keyed by account_id, so a reused id inherits the
// deleted player's history. AUTOINCREMENT makes ids strictly increasing. Runs only
// when the deployed DB still has the old schema; the sequence is seeded past every
// id history has seen.
static bool accountsHasColumn(const char* column) {
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db, "PRAGMA table_info(accounts);", -1, &st, nullptr) != SQLITE_OK) return true;
    bool found = false;
    while (sqlite3_step(st) == SQLITE_ROW) {
        const unsigned char* name = sqlite3_column_text(st, 1);
        if (name && strcmp(reinterpret_cast<const char*>(name), column) == 0) { found = true; break; }
    }
    sqlite3_finalize(st);
    return found;
}

static void migrateAccountsBanColumns() {
    struct Col { const char* name; const char* ddl; };
    const Col cols[] = {
        { "hwid_banned", "ALTER TABLE accounts ADD COLUMN hwid_banned INTEGER NOT NULL DEFAULT 0;" },
        { "ban_reason",  "ALTER TABLE accounts ADD COLUMN ban_reason TEXT;" },
        { "banned_at",   "ALTER TABLE accounts ADD COLUMN banned_at INTEGER;" },
    };
    for (const Col& c : cols) {
        if (accountsHasColumn(c.name)) continue;
        char* err = nullptr;
        if (sqlite3_exec(g_db, c.ddl, nullptr, nullptr, &err) != SQLITE_OK) {
            logf("ACCT     warning: adding accounts.%s failed: %s", c.name, err ? err : "?");
            if (err) sqlite3_free(err);
        } else {
            logf("ACCT     added accounts.%s", c.name);
        }
    }
}

static void migrateAccountsAutoincrement() {
    sqlite3_stmt* st = nullptr;
    bool needsMigration = false;
    if (sqlite3_prepare_v2(g_db,
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='accounts';",
            -1, &st, nullptr) == SQLITE_OK) {
        if (sqlite3_step(st) == SQLITE_ROW) {
            const char* sql = reinterpret_cast<const char*>(sqlite3_column_text(st, 0));
            needsMigration = sql && !strstr(sql, "AUTOINCREMENT");
        }
        sqlite3_finalize(st);
    }
    if (!needsMigration) return;

    const char* mig =
        "BEGIN IMMEDIATE;"
        "ALTER TABLE accounts RENAME TO accounts_old;"
        "CREATE TABLE accounts ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " username TEXT NOT NULL UNIQUE COLLATE NOCASE,"
        " token_hash TEXT NOT NULL,"
        " created_at INTEGER NOT NULL,"
        " last_login_at INTEGER,"
        " disabled INTEGER NOT NULL DEFAULT 0);"
        "INSERT INTO accounts SELECT id,username,token_hash,created_at,last_login_at,disabled"
        " FROM accounts_old;"
        "DROP TABLE accounts_old;"
        // Seed the sequence past everything history has seen (match_players keeps ids of
        // deleted accounts). INSERT OR REPLACE, not UPDATE: with an empty accounts table
        // sqlite_sequence has no 'accounts' row yet and an UPDATE would silently no-op.
        "INSERT OR REPLACE INTO sqlite_sequence(name,seq) VALUES('accounts',"
        " (SELECT MAX(m) FROM (SELECT IFNULL(MAX(id),0) m FROM accounts"
        "  UNION ALL SELECT IFNULL(MAX(account_id),0) FROM match_players)));"
        "COMMIT;";
    char* err = nullptr;
    if (sqlite3_exec(g_db, mig, nullptr, nullptr, &err) != SQLITE_OK) {
        logf("ACCT     warning: AUTOINCREMENT migration failed: %s", err ? err : "?");
        if (err) sqlite3_free(err);
        sqlite3_exec(g_db, "ROLLBACK;", nullptr, nullptr, nullptr);
    } else {
        logf("ACCT     migrated accounts table to AUTOINCREMENT ids (no more id reuse)");
    }
}

static void accountsInit(const char* path) {
    if (sqlite3_open(path, &g_db) != SQLITE_OK) {
        logf("ACCT     warning: could not open account DB '%s': %s - accounts disabled",
             path, g_db ? sqlite3_errmsg(g_db) : "?");
        if (g_db) { sqlite3_close(g_db); g_db = nullptr; }
        return;
    }
    // Both instances (release + dev) share this file; without a busy timeout a write
    // that lands while the other process holds the lock fails immediately with
    // SQLITE_BUSY and is dropped.
    // Journal mode stays the default rollback journal: the panel's "export accounts.db"
    // copies the single DB file, and a WAL DB copied without its -wal sidecar loses the
    // latest transactions.
    sqlite3_busy_timeout(g_db, 5000);
    const char* ddl =
        "CREATE TABLE IF NOT EXISTS accounts ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"       // never reuse ids - see migration note
        " username TEXT NOT NULL UNIQUE COLLATE NOCASE,"
        " token_hash TEXT NOT NULL,"
        " created_at INTEGER NOT NULL,"
        " last_login_at INTEGER,"
        " disabled INTEGER NOT NULL DEFAULT 0);"
        // Match history: one row per match that actually started (MM_START), stamped
        // ended_at when its session empties. winner_team stays NULL until MM_RESULT.
        "CREATE TABLE IF NOT EXISTS matches ("
        " id INTEGER PRIMARY KEY,"
        " started_at INTEGER NOT NULL,"
        " ended_at INTEGER,"
        " map INTEGER NOT NULL,"
        " map_name TEXT,"
        " relay_idx INTEGER NOT NULL,"
        " relay_ip TEXT,"
        " worst_ping INTEGER,"
        " player_count INTEGER NOT NULL,"
        " winner_team INTEGER);"
        // Who was in each match. account_id may be 0 for an unauthed connection; username
        // is captured at match time, so history survives a rename or delete.
        "CREATE TABLE IF NOT EXISTS match_players ("
        " match_id INTEGER NOT NULL,"
        " account_id INTEGER,"
        " username TEXT,"
        " team INTEGER,"
        " slot INTEGER);"
        "CREATE INDEX IF NOT EXISTS idx_mp_match   ON match_players(match_id);"
        "CREATE INDEX IF NOT EXISTS idx_mp_account ON match_players(account_id);"
        // Auth resolves sha256(token) -> account on every login; without this index
        // that is a full table scan per MM_AUTH.
        "CREATE INDEX IF NOT EXISTS idx_accounts_token ON accounts(token_hash);"
        // The metrics snapshot counts matches in the last 24h every second while a
        // panel is attached; this turns that from a full scan into an index range.
        "CREATE INDEX IF NOT EXISTS idx_matches_started ON matches(started_at);"
        "CREATE TABLE IF NOT EXISTS account_hwids ("
        " account_id INTEGER NOT NULL,"
        " tag INTEGER NOT NULL,"
        " hash TEXT NOT NULL,"
        " first_seen_at INTEGER NOT NULL,"
        " last_seen_at INTEGER NOT NULL,"
        " seen_count INTEGER NOT NULL DEFAULT 1,"
        " PRIMARY KEY(account_id, tag, hash));"
        "CREATE INDEX IF NOT EXISTS idx_hwids_hash ON account_hwids(hash);"
        "CREATE TABLE IF NOT EXISTS account_ips ("
        " account_id INTEGER NOT NULL,"
        " ip TEXT NOT NULL,"
        " first_seen_at INTEGER NOT NULL,"
        " last_seen_at INTEGER NOT NULL,"
        " login_count INTEGER NOT NULL DEFAULT 1,"
        " PRIMARY KEY(account_id, ip));"
        "CREATE INDEX IF NOT EXISTS idx_ips_ip ON account_ips(ip);"
        "CREATE TABLE IF NOT EXISTS account_tamper ("
        " account_id INTEGER NOT NULL,"
        " kind INTEGER NOT NULL,"
        " detail TEXT NOT NULL,"
        " flags INTEGER NOT NULL DEFAULT 0,"
        " pid INTEGER NOT NULL DEFAULT 0,"
        " last_match_id INTEGER,"
        " first_seen_at INTEGER NOT NULL,"
        " last_seen_at INTEGER NOT NULL,"
        " seen_count INTEGER NOT NULL DEFAULT 1,"
        " PRIMARY KEY(account_id, kind, detail));";
    char* err = nullptr;
    if (sqlite3_exec(g_db, ddl, nullptr, nullptr, &err) != SQLITE_OK) {
        logf("ACCT     warning: schema init failed: %s", err ? err : "?");
        if (err) sqlite3_free(err);
    }
    migrateAccountsAutoincrement();
    migrateAccountsBanColumns();
    // Reconcile any match left "live" (ended_at NULL) by a previous crash/restart: no
    // session survives a process restart, so close them at their start time.
    sqlite3_exec(g_db, "UPDATE matches SET ended_at=started_at WHERE ended_at IS NULL;",
                 nullptr, nullptr, nullptr);
    logf("ACCT     account DB ready: %s", path);
}

// Create an account. On success fills outId + outToken (the RAW token, shown once).
static bool accountCreate(const std::string& username, long long& outId,
                          std::string& outToken, std::string& outErr) {
    if (!g_db) { outErr = "account DB not available"; return false; }
    if (!validUsername(username)) { outErr = "invalid username (1-24 chars: letters, digits, _ or -)"; return false; }
    std::string token = genToken();
    if (token.empty()) { outErr = "RNG failure"; return false; }
    std::string hash = sha256Hex(token);
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db,
            "INSERT INTO accounts (username, token_hash, created_at) VALUES (?,?,?);",
            -1, &st, nullptr) != SQLITE_OK) { outErr = sqlite3_errmsg(g_db); return false; }
    sqlite3_bind_text (st, 1, username.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text (st, 2, hash.c_str(),     -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(st, 3, static_cast<sqlite3_int64>(time(nullptr)));
    int rc = sqlite3_step(st);
    sqlite3_finalize(st);
    if (rc != SQLITE_DONE) {
        outErr = (rc == SQLITE_CONSTRAINT) ? "username already exists" : sqlite3_errmsg(g_db);
        return false;
    }
    outId = sqlite3_last_insert_rowid(g_db);
    outToken = token;
    return true;
}

// Resolve a raw token -> account. Returns true if a matching account exists (even if
// disabled - the caller distinguishes "banned" from "no such token" via outDisabled).
static bool accountResolveToken(const std::string& token, long long& outId,
                                std::string& outName, bool& outDisabled) {
    if (!g_db || token.empty()) return false;
    std::string hash = sha256Hex(token);
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db,
            "SELECT id, username, disabled FROM accounts WHERE token_hash = ?;",
            -1, &st, nullptr) != SQLITE_OK) return false;
    sqlite3_bind_text(st, 1, hash.c_str(), -1, SQLITE_TRANSIENT);
    bool found = false;
    if (sqlite3_step(st) == SQLITE_ROW) {
        outId = sqlite3_column_int64(st, 0);
        const unsigned char* u = sqlite3_column_text(st, 1);
        outName = u ? reinterpret_cast<const char*>(u) : "";
        outDisabled = sqlite3_column_int(st, 2) != 0;
        found = true;
    }
    sqlite3_finalize(st);
    return found;
}

static void accountTouchLogin(long long id) {
    if (!g_db) return;
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db, "UPDATE accounts SET last_login_at=? WHERE id=?;", -1, &st, nullptr) != SQLITE_OK) return;
    sqlite3_bind_int64(st, 1, static_cast<sqlite3_int64>(time(nullptr)));
    sqlite3_bind_int64(st, 2, id);
    sqlite3_step(st); sqlite3_finalize(st);
}

static bool accountExec1(const char* sql, long long id) {   // one-param id mutation
    if (!g_db) return false;
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db, sql, -1, &st, nullptr) != SQLITE_OK) return false;
    sqlite3_bind_int64(st, 1, id);
    int rc = sqlite3_step(st);
    sqlite3_finalize(st);
    return rc == SQLITE_DONE && sqlite3_changes(g_db) > 0;
}
static bool accountSetDisabled(long long id, bool disabled) {
    return accountExec1(disabled ? "UPDATE accounts SET disabled=1 WHERE id=?;"
                                 : "UPDATE accounts SET disabled=0, hwid_banned=0, ban_reason=NULL, banned_at=NULL WHERE id=?;", id);
}
static bool accountDelete(long long id) {
    if (!accountExec1("DELETE FROM accounts WHERE id=?;", id)) return false;
    accountExec1("DELETE FROM account_hwids WHERE account_id=?;", id);
    accountExec1("DELETE FROM account_ips WHERE account_id=?;", id);
    accountExec1("DELETE FROM account_tamper WHERE account_id=?;", id);
    return true;
}

static bool accountRegen(long long id, std::string& outToken, std::string& outErr) {
    if (!g_db) { outErr = "account DB not available"; return false; }
    std::string token = genToken();
    if (token.empty()) { outErr = "RNG failure"; return false; }
    std::string hash = sha256Hex(token);
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db, "UPDATE accounts SET token_hash=? WHERE id=?;", -1, &st, nullptr) != SQLITE_OK) {
        outErr = sqlite3_errmsg(g_db); return false;
    }
    sqlite3_bind_text (st, 1, hash.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(st, 2, id);
    int rc = sqlite3_step(st); sqlite3_finalize(st);
    if (rc != SQLITE_DONE || sqlite3_changes(g_db) == 0) { outErr = "no such account"; return false; }
    outToken = token;
    return true;
}

// ---- match history + stats --------------------------------------------------
// Record a match that just reached START; returns its row id (0 on failure) and
// snapshots its players into match_players. The row's ended_at is stamped later when
// the session empties (matchRecordEnd).
static long long matchRecordStart(uint32_t sid) {
    if (!g_db) return 0;
    const Client* rep = nullptr; int count = 0;
    for (const auto& c : g_clients) if (!c.dead && c.session == sid) { if (!rep) rep = &c; ++count; }
    if (!rep || count == 0) return 0;
    uint8_t mapId = rep->matchMap, relayIdx = rep->matchRelayIdx;
    const char* mapName = (mapId < g_mapCount) ? g_maps[mapId].name : "?";
    const char* relayIp = (relayIdx < g_relays.size()) ? g_relays[relayIdx].ip.c_str() : "";

    // One transaction for the match row + its player rows: 1 fsync instead of 1+N
    // (autocommit fsyncs per INSERT, on the event-loop thread), and the history can
    // never hold a match row with a half-written roster.
    sqlite3_exec(g_db, "BEGIN;", nullptr, nullptr, nullptr);

    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db,
            "INSERT INTO matches (started_at,map,map_name,relay_idx,relay_ip,player_count) VALUES (?,?,?,?,?,?);",
            -1, &st, nullptr) != SQLITE_OK) {
        sqlite3_exec(g_db, "ROLLBACK;", nullptr, nullptr, nullptr);
        return 0;
    }
    sqlite3_bind_int64(st, 1, static_cast<sqlite3_int64>(time(nullptr)));
    sqlite3_bind_int  (st, 2, mapId);
    sqlite3_bind_text (st, 3, mapName, -1, SQLITE_TRANSIENT);
    sqlite3_bind_int  (st, 4, relayIdx);
    sqlite3_bind_text (st, 5, relayIp, -1, SQLITE_TRANSIENT);
    sqlite3_bind_int  (st, 6, count);
    int rc = sqlite3_step(st);
    sqlite3_finalize(st);
    if (rc != SQLITE_DONE) {
        sqlite3_exec(g_db, "ROLLBACK;", nullptr, nullptr, nullptr);
        return 0;
    }
    long long matchId = sqlite3_last_insert_rowid(g_db);

    sqlite3_stmt* ps = nullptr;   // prepared once, re-bound per player
    if (sqlite3_prepare_v2(g_db,
            "INSERT INTO match_players (match_id,account_id,username,team,slot) VALUES (?,?,?,?,?);",
            -1, &ps, nullptr) == SQLITE_OK) {
        for (const auto& c : g_clients) {
            if (c.dead || c.session != sid) continue;
            sqlite3_reset(ps);
            sqlite3_bind_int64(ps, 1, matchId);
            sqlite3_bind_int64(ps, 2, c.accountId);
            sqlite3_bind_text (ps, 3, c.name, -1, SQLITE_TRANSIENT);
            sqlite3_bind_int  (ps, 4, c.matchTeam);
            sqlite3_bind_int  (ps, 5, c.matchSlot);
            sqlite3_step(ps);
        }
        sqlite3_finalize(ps);
    }
    sqlite3_exec(g_db, "COMMIT;", nullptr, nullptr, nullptr);
    return matchId;
}

static void matchRecordEnd(long long rowId) {
    if (!g_db || rowId == 0) return;
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db, "UPDATE matches SET ended_at=? WHERE id=? AND ended_at IS NULL;",
                           -1, &st, nullptr) != SQLITE_OK) return;
    sqlite3_bind_int64(st, 1, static_cast<sqlite3_int64>(time(nullptr)));
    sqlite3_bind_int64(st, 2, rowId);
    sqlite3_step(st); sqlite3_finalize(st);
}

// Record the winning team (0=Seraphites, 1=WLF, 2=draw) for a match, once.
static void matchSetWinner(long long rowId, int winner) {
    if (!g_db || rowId == 0) return;
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db, "UPDATE matches SET winner_team=? WHERE id=? AND winner_team IS NULL;",
                           -1, &st, nullptr) != SQLITE_OK) return;
    sqlite3_bind_int  (st, 1, winner);
    sqlite3_bind_int64(st, 2, rowId);
    sqlite3_step(st); sqlite3_finalize(st);
}

// Per-account derived stats from history: matches played, total playtime, and W/L (a
// draw is neither a win nor a loss). Winner 2 = draw. Computed for EVERY account in one
// grouped scan; the snapshot needs all of them every second while a panel is attached.
struct AccountStatsRow { long long matches = 0, playtimeSec = 0, wins = 0, losses = 0; };

static void allAccountStats(std::map<long long, AccountStatsRow>& out) {
    out.clear();
    if (!g_db) return;
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db,
            "SELECT mp.account_id, COUNT(*),"
            " IFNULL(SUM(CASE WHEN m.ended_at IS NOT NULL THEN m.ended_at-m.started_at ELSE 0 END),0),"
            " IFNULL(SUM(CASE WHEN m.winner_team IS NOT NULL AND m.winner_team!=2 AND m.winner_team=mp.team THEN 1 ELSE 0 END),0),"
            " IFNULL(SUM(CASE WHEN m.winner_team IS NOT NULL AND m.winner_team!=2 AND m.winner_team!=mp.team THEN 1 ELSE 0 END),0)"
            " FROM match_players mp JOIN matches m ON m.id=mp.match_id"
            " WHERE mp.account_id != 0 GROUP BY mp.account_id;",
            -1, &st, nullptr) != SQLITE_OK) return;
    while (sqlite3_step(st) == SQLITE_ROW) {
        AccountStatsRow r;
        long long id  = sqlite3_column_int64(st, 0);
        r.matches     = sqlite3_column_int64(st, 1);
        r.playtimeSec = sqlite3_column_int64(st, 2);
        r.wins        = sqlite3_column_int64(st, 3);
        r.losses      = sqlite3_column_int64(st, 4);
        out[id] = r;
    }
    sqlite3_finalize(st);
}

// ---- leaderboard: top players by elo (cached) -------------------------------
// Builds the MM_LEADERBOARD body and caches it: [u8 count][count*MMLeaderEntry] in
// rank order (highest elo first; wins, then name, break ties). The query aggregates
// ALL of match history, so it is rebuilt at most once per kLbCacheTtlMs regardless of
// how often clients request it. Elo is computed here, not in SQL: the bundled SQLite
// is built without SQLITE_ENABLE_MATH_FUNCTIONS, so it has no log10/log2.
static std::vector<uint8_t> g_lbBody;
static uint64_t             g_lbBuiltMs   = 0;
static const uint64_t       kLbCacheTtlMs = 30000;   // rebuild at most every 30s

static const std::vector<uint8_t>& leaderboardBody() {
    const uint64_t now = nowMs();
    if (!g_lbBody.empty() && now - g_lbBuiltMs < kLbCacheTtlMs)
        return g_lbBody;

    std::vector<MMLeaderEntry> all;
    uint8_t count = 0;
    if (g_db) {
        sqlite3_stmt* st = nullptr;
        if (sqlite3_prepare_v2(g_db,
                "SELECT a.username,"
                " IFNULL(SUM(CASE WHEN m.winner_team IS NOT NULL AND m.winner_team!=2 AND m.winner_team=mp.team  THEN 1 ELSE 0 END),0) AS wins,"
                " IFNULL(SUM(CASE WHEN m.winner_team IS NOT NULL AND m.winner_team!=2 AND m.winner_team!=mp.team THEN 1 ELSE 0 END),0) AS losses"
                " FROM accounts a"
                " JOIN match_players mp ON mp.account_id=a.id"
                " JOIN matches m ON m.id=mp.match_id"
                " GROUP BY a.id;", -1, &st, nullptr) == SQLITE_OK) {
            while (sqlite3_step(st) == SQLITE_ROW) {
                MMLeaderEntry e;
                memset(&e, 0, sizeof(e));                       // nul-pad the name field
                const unsigned char* un = sqlite3_column_text(st, 0);
                if (un) {
                    size_t n = strlen(reinterpret_cast<const char*>(un));
                    if (n > MM_NAME_LEN - 1) n = MM_NAME_LEN - 1;
                    memcpy(e.name, un, n);
                }
                e.wins   = static_cast<uint32_t>(sqlite3_column_int64(st, 1));
                e.losses = static_cast<uint32_t>(sqlite3_column_int64(st, 2));

                const double w = e.wins, l = e.losses;
                const double p = (w + 10.0) / (w + l + 20.0);
                const double elo = 1000.0 + 400.0 * std::log10(p / (1.0 - p))
                                          +  60.0 * std::log2(1.0 + (w + l) / 25.0);
                e.winloss_ratio = static_cast<float>(l > 0.0 ? w / l : w);
                e.elo = static_cast<uint32_t>(elo > 0.0 ? elo : 0.0);
                all.push_back(e);
            }
            sqlite3_finalize(st);
        }
    }

    const size_t keep = all.size() < MM_LEADERBOARD_MAX ? all.size() : MM_LEADERBOARD_MAX;
    std::partial_sort(all.begin(), all.begin() + keep, all.end(),
                      [](const MMLeaderEntry& a, const MMLeaderEntry& b) {
                          if (a.elo  != b.elo)  return a.elo  > b.elo;
                          if (a.wins != b.wins) return a.wins > b.wins;
                          return strncmp(a.name, b.name, MM_NAME_LEN) < 0;
                      });
    count = static_cast<uint8_t>(keep);

    g_lbBody.clear();
    g_lbBody.push_back(count);
    g_lbBody.insert(g_lbBody.end(),
                    reinterpret_cast<const uint8_t*>(all.data()),
                    reinterpret_cast<const uint8_t*>(all.data()) + count * sizeof(MMLeaderEntry));
    g_lbBuiltMs = now;
    return g_lbBody;
}

// ---- online player count ----------------------------------------------------
// Everyone connected AND authenticated right now: in menu, searching, or in a live
// match (the client keeps this connection alive the whole time). No DB, so it is
// computed fresh per request.
static uint32_t onlineCount() {
    uint32_t n = 0;
    for (const auto& c : g_clients) if (c.authed && !c.dead) ++n;
    return n;
}

// Recent matches for the panel: last `limit`, newest first, each with its players.
static void matchesJson(std::string& o, int limit) {
    o += '[';
    if (g_db) {
        // The per-match player query is prepared ONCE and re-bound per row; this runs
        // every second while a panel is attached.
        sqlite3_stmt* ps = nullptr;
        sqlite3_prepare_v2(g_db,
                "SELECT username,team,slot FROM match_players WHERE match_id=? ORDER BY slot;",
                -1, &ps, nullptr);
        sqlite3_stmt* st = nullptr;
        if (sqlite3_prepare_v2(g_db,
                "SELECT id,started_at,ended_at,map_name,relay_idx,relay_ip,player_count,winner_team"
                " FROM matches ORDER BY id DESC LIMIT ?;", -1, &st, nullptr) == SQLITE_OK) {
            sqlite3_bind_int(st, 1, limit);
            bool first = true;
            while (sqlite3_step(st) == SQLITE_ROW) {
                long long id        = sqlite3_column_int64(st, 0);
                long long startedAt = sqlite3_column_int64(st, 1);
                long long endedAt   = (sqlite3_column_type(st, 2) == SQLITE_NULL) ? 0 : sqlite3_column_int64(st, 2);
                const unsigned char* mapName = sqlite3_column_text(st, 3);
                int relayIdx = sqlite3_column_int(st, 4);
                const unsigned char* relayIp = sqlite3_column_text(st, 5);
                int pc = sqlite3_column_int(st, 6);
                int winner = (sqlite3_column_type(st, 7) == SQLITE_NULL) ? -1 : sqlite3_column_int(st, 7);
                if (!first) o += ','; first = false;
                char t[224];
                snprintf(t, sizeof(t),
                    "{\"id\":%lld,\"startedAt\":%lld,\"endedAt\":%lld,\"relayIdx\":%d,\"playerCount\":%d,\"winnerTeam\":%d,\"mapName\":",
                    id, startedAt, endedAt, relayIdx, pc, winner);
                o += t;
                jStr(o, mapName ? reinterpret_cast<const char*>(mapName) : "?");
                o += ",\"relayIp\":"; jStr(o, relayIp ? reinterpret_cast<const char*>(relayIp) : "");
                o += ",\"players\":[";
                if (ps) {
                    sqlite3_reset(ps);
                    sqlite3_bind_int64(ps, 1, id);
                    bool pf = true;
                    while (sqlite3_step(ps) == SQLITE_ROW) {
                        const unsigned char* un = sqlite3_column_text(ps, 0);
                        int team = sqlite3_column_int(ps, 1);
                        int slot = sqlite3_column_int(ps, 2);
                        if (!pf) o += ','; pf = false;
                        char pt[64]; snprintf(pt, sizeof(pt), "{\"team\":%d,\"slot\":%d,\"name\":", team, slot);
                        o += pt; jStr(o, un ? reinterpret_cast<const char*>(un) : "?"); o += '}';
                    }
                }
                o += "]}";
            }
            sqlite3_finalize(st);
        }
        if (ps) sqlite3_finalize(ps);
    }
    o += ']';
}

// Server metrics object: live counters + a few DB-derived aggregates.
static void metricsJson(std::string& o, int connectedNow) {
    long long avgQueueMs = g_mQueueWaitCount ? static_cast<long long>(g_mQueueWaitSumMs / g_mQueueWaitCount) : 0;
    long long totalMatches = 0, avgDurSec = 0, matches24h = 0;
    if (g_db) {
        sqlite3_stmt* st = nullptr;
        if (sqlite3_prepare_v2(g_db,
                "SELECT COUNT(*), IFNULL(AVG(CASE WHEN ended_at IS NOT NULL THEN ended_at-started_at END),0),"
                " SUM(CASE WHEN started_at>=? THEN 1 ELSE 0 END) FROM matches;", -1, &st, nullptr) == SQLITE_OK) {
            sqlite3_bind_int64(st, 1, static_cast<sqlite3_int64>(time(nullptr) - 24 * 3600));
            if (sqlite3_step(st) == SQLITE_ROW) {
                totalMatches = sqlite3_column_int64(st, 0);
                avgDurSec    = static_cast<long long>(sqlite3_column_double(st, 1));
                matches24h   = (sqlite3_column_type(st, 2) == SQLITE_NULL) ? 0 : sqlite3_column_int64(st, 2);
            }
            sqlite3_finalize(st);
        }
    }
    char t[256];
    snprintf(t, sizeof(t),
        "{\"peakConnected\":%d,\"matchesStarted\":%llu,\"aborts\":%llu,\"avgQueueMs\":%lld,"
        "\"totalMatches\":%lld,\"avgDurationSec\":%lld,\"matches24h\":%lld,\"connectedNow\":%d}",
        g_mPeakConnected, static_cast<unsigned long long>(g_mMatchesStarted),
        static_cast<unsigned long long>(g_mAborts), avgQueueMs,
        totalMatches, avgDurSec, matches24h, connectedNow);
    o += t;
}

// Append the accounts array to the snapshot JSON. onlineIds = accounts with a live
// authed connection right now.
struct HwidComponent { uint8_t tag = 0; std::string hex; };

struct HwidLogin {
    bool    present   = false;
    bool    malformed = false;
    uint8_t flags     = 0;
    int     reported  = 0;
    int     matched   = 0;
    int     added     = 0;
};

static std::map<long long, HwidLogin> g_lastHwidLogin;

static std::string hexEncode(const uint8_t* p, size_t n) {
    static const char* digits = "0123456789abcdef";
    std::string s;
    s.reserve(n * 2);
    for (size_t i = 0; i < n; ++i) { s += digits[p[i] >> 4]; s += digits[p[i] & 0xF]; }
    return s;
}

static bool parseHwidBlock(const uint8_t* p, size_t len, uint8_t& outFlags, std::vector<HwidComponent>& out) {
    if (len < sizeof(MMHwidBlock)) return false;
    MMHwidBlock h; memcpy(&h, p, sizeof(h));
    if (h.blockVersion != MM_HWID_BLOCK_VERSION) return false;
    if (h.count > MM_HWID_MAX_COMPONENTS) return false;
    if (len < sizeof(MMHwidBlock) + static_cast<size_t>(h.count) * sizeof(MMHwidComponent)) return false;
    outFlags = h.flags;
    p += sizeof(h);
    for (int i = 0; i < h.count; ++i, p += sizeof(MMHwidComponent)) {
        MMHwidComponent c; memcpy(&c, p, sizeof(c));
        if (c.tag < MM_HWID_TAG_MACHINE_GUID || c.tag > MM_HWID_TAG_MAC) return false;
        HwidComponent hc;
        hc.tag = c.tag;
        hc.hex = hexEncode(c.hash, sizeof(c.hash));
        out.push_back(std::move(hc));
    }
    return true;
}

static void accountRecordHwids(long long id, const std::vector<HwidComponent>& comps, HwidLogin& r) {
    if (!g_db || comps.empty()) return;
    const sqlite3_int64 now = static_cast<sqlite3_int64>(time(nullptr));
    if (sqlite3_exec(g_db, "BEGIN IMMEDIATE;", nullptr, nullptr, nullptr) != SQLITE_OK) return;
    sqlite3_stmt* upd = nullptr;
    sqlite3_stmt* ins = nullptr;
    bool ok =
        sqlite3_prepare_v2(g_db,
            "UPDATE account_hwids SET last_seen_at=?, seen_count=seen_count+1"
            " WHERE account_id=? AND tag=? AND hash=?;", -1, &upd, nullptr) == SQLITE_OK &&
        sqlite3_prepare_v2(g_db,
            "INSERT INTO account_hwids(account_id,tag,hash,first_seen_at,last_seen_at,seen_count)"
            " VALUES(?,?,?,?,?,1);", -1, &ins, nullptr) == SQLITE_OK;
    for (size_t i = 0; ok && i < comps.size(); ++i) {
        const HwidComponent& c = comps[i];
        sqlite3_reset(upd);
        sqlite3_bind_int64(upd, 1, now);
        sqlite3_bind_int64(upd, 2, id);
        sqlite3_bind_int(upd, 3, c.tag);
        sqlite3_bind_text(upd, 4, c.hex.c_str(), -1, SQLITE_TRANSIENT);
        if (sqlite3_step(upd) != SQLITE_DONE) { ok = false; break; }
        if (sqlite3_changes(g_db) > 0) { ++r.matched; continue; }
        sqlite3_reset(ins);
        sqlite3_bind_int64(ins, 1, id);
        sqlite3_bind_int(ins, 2, c.tag);
        sqlite3_bind_text(ins, 3, c.hex.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_int64(ins, 4, now);
        sqlite3_bind_int64(ins, 5, now);
        if (sqlite3_step(ins) != SQLITE_DONE) { ok = false; break; }
        ++r.added;
    }
    if (upd) sqlite3_finalize(upd);
    if (ins) sqlite3_finalize(ins);
    if (ok) sqlite3_exec(g_db, "COMMIT;", nullptr, nullptr, nullptr);
    else {
        sqlite3_exec(g_db, "ROLLBACK;", nullptr, nullptr, nullptr);
        logf("HWID     warning: recording components for account #%lld failed: %s", id, sqlite3_errmsg(g_db));
        r.matched = 0; r.added = 0;
    }
}

static void accountRecordIp(long long id, const char* ip) {
    if (!g_db || !ip || !ip[0]) return;
    const sqlite3_int64 now = static_cast<sqlite3_int64>(time(nullptr));
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db,
            "UPDATE account_ips SET last_seen_at=?, login_count=login_count+1 WHERE account_id=? AND ip=?;",
            -1, &st, nullptr) != SQLITE_OK) return;
    sqlite3_bind_int64(st, 1, now);
    sqlite3_bind_int64(st, 2, id);
    sqlite3_bind_text(st, 3, ip, -1, SQLITE_TRANSIENT);
    const bool stepped = sqlite3_step(st) == SQLITE_DONE;
    sqlite3_finalize(st);
    if (!stepped || sqlite3_changes(g_db) > 0) return;
    if (sqlite3_prepare_v2(g_db,
            "INSERT INTO account_ips(account_id,ip,first_seen_at,last_seen_at,login_count) VALUES(?,?,?,?,1);",
            -1, &st, nullptr) != SQLITE_OK) return;
    sqlite3_bind_int64(st, 1, id);
    sqlite3_bind_text(st, 2, ip, -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(st, 3, now);
    sqlite3_bind_int64(st, 4, now);
    sqlite3_step(st);
    sqlite3_finalize(st);
}

static const int kTamperMaxRowsPerAccount = 64;
static const int kTamperMaxMsgsPerConn    = 64;

static void sanitizeTamperDetail(char* s, size_t cap) {
    if (!s || cap == 0) return;
    s[cap - 1] = 0;
    for (size_t i = 0; i < cap && s[i]; ++i) {
        const unsigned char ch = static_cast<unsigned char>(s[i]);
        if (ch < 0x20 || ch >= 0x7F) s[i] = '?';
    }
}

static long long accountTamperRowCount(long long id) {
    if (!g_db) return 0;
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db, "SELECT COUNT(*) FROM account_tamper WHERE account_id=?;", -1, &st, nullptr) != SQLITE_OK) return 0;
    sqlite3_bind_int64(st, 1, id);
    long long n = 0;
    if (sqlite3_step(st) == SQLITE_ROW) n = sqlite3_column_int64(st, 0);
    sqlite3_finalize(st);
    return n;
}

static bool accountRecordTamper(long long id, int kind, unsigned flags, unsigned pid, long long matchId, const char* detail) {
    if (!g_db || !detail) return false;
    const sqlite3_int64 now = static_cast<sqlite3_int64>(time(nullptr));
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db,
            "UPDATE account_tamper SET last_seen_at=?, seen_count=seen_count+1, flags=?, pid=?,"
            " last_match_id=COALESCE(?, last_match_id) WHERE account_id=? AND kind=? AND detail=?;",
            -1, &st, nullptr) != SQLITE_OK) return false;
    sqlite3_bind_int64(st, 1, now);
    sqlite3_bind_int(st, 2, static_cast<int>(flags));
    sqlite3_bind_int64(st, 3, static_cast<sqlite3_int64>(pid));
    if (matchId > 0) sqlite3_bind_int64(st, 4, matchId); else sqlite3_bind_null(st, 4);
    sqlite3_bind_int64(st, 5, id);
    sqlite3_bind_int(st, 6, kind);
    sqlite3_bind_text(st, 7, detail, -1, SQLITE_TRANSIENT);
    const bool stepped = sqlite3_step(st) == SQLITE_DONE;
    sqlite3_finalize(st);
    if (!stepped) return false;
    if (sqlite3_changes(g_db) > 0) return true;
    if (accountTamperRowCount(id) >= kTamperMaxRowsPerAccount) return false;
    if (sqlite3_prepare_v2(g_db,
            "INSERT INTO account_tamper(account_id,kind,detail,flags,pid,last_match_id,first_seen_at,last_seen_at,seen_count)"
            " VALUES(?,?,?,?,?,?,?,?,1);",
            -1, &st, nullptr) != SQLITE_OK) return false;
    sqlite3_bind_int64(st, 1, id);
    sqlite3_bind_int(st, 2, kind);
    sqlite3_bind_text(st, 3, detail, -1, SQLITE_TRANSIENT);
    sqlite3_bind_int(st, 4, static_cast<int>(flags));
    sqlite3_bind_int64(st, 5, static_cast<sqlite3_int64>(pid));
    if (matchId > 0) sqlite3_bind_int64(st, 6, matchId); else sqlite3_bind_null(st, 6);
    sqlite3_bind_int64(st, 7, now);
    sqlite3_bind_int64(st, 8, now);
    const bool inserted = sqlite3_step(st) == SQLITE_DONE;
    sqlite3_finalize(st);
    return inserted;
}

static bool accountExists(long long id) {
    if (!g_db) return false;
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db, "SELECT 1 FROM accounts WHERE id=?;", -1, &st, nullptr) != SQLITE_OK) return false;
    sqlite3_bind_int64(st, 1, id);
    const bool found = sqlite3_step(st) == SQLITE_ROW;
    sqlite3_finalize(st);
    return found;
}

static int accountClearTable(const char* sql, long long id) {
    if (!g_db) return -1;
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db, sql, -1, &st, nullptr) != SQLITE_OK) return -1;
    sqlite3_bind_int64(st, 1, id);
    const int rc = sqlite3_step(st);
    sqlite3_finalize(st);
    return rc == SQLITE_DONE ? sqlite3_changes(g_db) : -1;
}

static void sharedAccountsJson(std::string& o, const char* sql, long long id, const char* key, int tag) {
    o += '[';
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db, sql, -1, &st, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(st, 1, key, -1, SQLITE_TRANSIENT);
        int idx = 2;
        if (tag >= 0) sqlite3_bind_int(st, idx++, tag);
        sqlite3_bind_int64(st, idx, id);
        bool first = true;
        while (sqlite3_step(st) == SQLITE_ROW) {
            if (!first) o += ',';
            first = false;
            o += std::to_string(sqlite3_column_int64(st, 0));
        }
        sqlite3_finalize(st);
    }
    o += ']';
}

static void accountHwidsJson(std::string& o, long long id) {
    o += '[';
    if (g_db) {
        sqlite3_stmt* st = nullptr;
        if (sqlite3_prepare_v2(g_db,
                "SELECT tag, hash, first_seen_at, last_seen_at, seen_count FROM account_hwids"
                " WHERE account_id=? ORDER BY tag, first_seen_at;", -1, &st, nullptr) == SQLITE_OK) {
            sqlite3_bind_int64(st, 1, id);
            bool first = true;
            while (sqlite3_step(st) == SQLITE_ROW) {
                if (!first) o += ',';
                first = false;
                const int tag = sqlite3_column_int(st, 0);
                const unsigned char* hash = sqlite3_column_text(st, 1);
                const char* hs = hash ? reinterpret_cast<const char*>(hash) : "";
                char t[160];
                snprintf(t, sizeof(t), "{\"tag\":%d,\"firstSeen\":%lld,\"lastSeen\":%lld,\"seen\":%lld,\"hash\":",
                         tag, sqlite3_column_int64(st, 2), sqlite3_column_int64(st, 3), sqlite3_column_int64(st, 4));
                o += t;
                jStr(o, hs);
                o += ",\"sharedWith\":";
                sharedAccountsJson(o,
                    "SELECT DISTINCT account_id FROM account_hwids WHERE hash=? AND tag=? AND account_id<>? ORDER BY account_id;",
                    id, hs, tag);
                o += '}';
            }
            sqlite3_finalize(st);
        }
    }
    o += ']';
}

static void accountIpsJson(std::string& o, long long id) {
    o += '[';
    if (g_db) {
        sqlite3_stmt* st = nullptr;
        if (sqlite3_prepare_v2(g_db,
                "SELECT ip, first_seen_at, last_seen_at, login_count FROM account_ips"
                " WHERE account_id=? ORDER BY last_seen_at DESC;", -1, &st, nullptr) == SQLITE_OK) {
            sqlite3_bind_int64(st, 1, id);
            bool first = true;
            while (sqlite3_step(st) == SQLITE_ROW) {
                if (!first) o += ',';
                first = false;
                const unsigned char* ip = sqlite3_column_text(st, 0);
                const char* ips = ip ? reinterpret_cast<const char*>(ip) : "";
                char t[128];
                snprintf(t, sizeof(t), "{\"firstSeen\":%lld,\"lastSeen\":%lld,\"logins\":%lld,\"ip\":",
                         sqlite3_column_int64(st, 1), sqlite3_column_int64(st, 2), sqlite3_column_int64(st, 3));
                o += t;
                jStr(o, ips);
                o += ",\"sharedWith\":";
                sharedAccountsJson(o,
                    "SELECT DISTINCT account_id FROM account_ips WHERE ip=? AND account_id<>? ORDER BY account_id;",
                    id, ips, -1);
                o += '}';
            }
            sqlite3_finalize(st);
        }
    }
    o += ']';
}

static void accountTamperJson(std::string& o, long long id) {
    o += '[';
    if (g_db) {
        sqlite3_stmt* st = nullptr;
        if (sqlite3_prepare_v2(g_db,
                "SELECT kind, detail, flags, pid, last_match_id, first_seen_at, last_seen_at, seen_count FROM account_tamper"
                " WHERE account_id=? ORDER BY last_seen_at DESC;", -1, &st, nullptr) == SQLITE_OK) {
            sqlite3_bind_int64(st, 1, id);
            bool first = true;
            while (sqlite3_step(st) == SQLITE_ROW) {
                if (!first) o += ',';
                first = false;
                const unsigned char* d = sqlite3_column_text(st, 1);
                char detail[MM_TAMPER_DETAIL_LEN];
                snprintf(detail, sizeof(detail), "%s", d ? reinterpret_cast<const char*>(d) : "");
                sanitizeTamperDetail(detail, sizeof(detail));
                const long long matchId = (sqlite3_column_type(st, 4) == SQLITE_NULL) ? 0 : sqlite3_column_int64(st, 4);
                char t[200];
                snprintf(t, sizeof(t), "{\"kind\":%d,\"flags\":%d,\"pid\":%lld,\"matchId\":%lld,\"firstSeen\":%lld,\"lastSeen\":%lld,\"seen\":%lld,\"detail\":",
                         sqlite3_column_int(st, 0), sqlite3_column_int(st, 2), sqlite3_column_int64(st, 3), matchId,
                         sqlite3_column_int64(st, 5), sqlite3_column_int64(st, 6), sqlite3_column_int64(st, 7));
                o += t;
                jStr(o, detail);
                o += '}';
            }
            sqlite3_finalize(st);
        }
    }
    o += ']';
}

struct AccountIdentityRow { long long hwids = 0, hwidShared = 0, ips = 0, ipShared = 0, tamper = 0, tamperLast = 0; };

static void allAccountIdentity(std::map<long long, AccountIdentityRow>& out) {
    if (!g_db) return;
    struct Q { const char* sql; long long AccountIdentityRow::* field; };
    const Q qs[] = {
        { "SELECT account_id, COUNT(*) FROM account_tamper GROUP BY account_id;", &AccountIdentityRow::tamper },
        { "SELECT account_id, MAX(last_seen_at) FROM account_tamper GROUP BY account_id;", &AccountIdentityRow::tamperLast },
        { "SELECT account_id, COUNT(*) FROM account_hwids GROUP BY account_id;", &AccountIdentityRow::hwids },
        { "SELECT a.account_id, COUNT(DISTINCT b.account_id) FROM account_hwids a"
          " JOIN account_hwids b ON a.hash=b.hash AND a.tag=b.tag AND a.account_id<>b.account_id"
          " GROUP BY a.account_id;", &AccountIdentityRow::hwidShared },
        { "SELECT account_id, COUNT(*) FROM account_ips GROUP BY account_id;", &AccountIdentityRow::ips },
        { "SELECT a.account_id, COUNT(DISTINCT b.account_id) FROM account_ips a"
          " JOIN account_ips b ON a.ip=b.ip AND a.account_id<>b.account_id"
          " GROUP BY a.account_id;", &AccountIdentityRow::ipShared },
    };
    for (const Q& q : qs) {
        sqlite3_stmt* st = nullptr;
        if (sqlite3_prepare_v2(g_db, q.sql, -1, &st, nullptr) != SQLITE_OK) continue;
        while (sqlite3_step(st) == SQLITE_ROW)
            out[sqlite3_column_int64(st, 0)].*q.field = sqlite3_column_int64(st, 1);
        sqlite3_finalize(st);
    }
}

static void hwidLastJson(std::string& o, long long id) {
    auto it = g_lastHwidLogin.find(id);
    if (it == g_lastHwidLogin.end()) { o += "\"\""; return; }
    const HwidLogin& h = it->second;
    if (!h.present)   { o += "\"legacy\""; return; }
    if (h.malformed)  { o += "\"malformed\""; return; }
    char t[80];
    snprintf(t, sizeof(t), "\"%d/%d%s%s%s%s\"", h.matched, h.reported,
             h.added > 0 ? " +" : "", h.added > 0 ? std::to_string(h.added).c_str() : "",
             (h.flags & MM_HWID_FLAG_HYPERVISOR) ? " hv" : "",
             (h.flags & MM_HWID_FLAG_INCOMPLETE) ? " partial" : "");
    o += t;
}

static const double kHwidBanMinRatio      = 0.5;
static const int    kHwidBanMinMatches    = 2;
static const int    kHwidBanMinHardware   = 1;

struct HwidBanVerdict {
    bool      ban        = false;
    long long matchId    = 0;
    std::string matchName;
    int       matched    = 0;
    int       hardware   = 0;
    int       total      = 0;
    bool      ipMatched  = false;
};

static void hwidBanTally(const char* sql, std::map<long long, std::pair<int, bool>>& tally,
                         long long selfId, const char* key, int tag, bool isIp) {
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db, sql, -1, &st, nullptr) != SQLITE_OK) return;
    sqlite3_bind_text(st, 1, key, -1, SQLITE_TRANSIENT);
    int idx = 2;
    if (tag >= 0) sqlite3_bind_int(st, idx++, tag);
    sqlite3_bind_int64(st, idx, selfId);
    while (sqlite3_step(st) == SQLITE_ROW) {
        auto& e = tally[sqlite3_column_int64(st, 0)];
        if (isIp) e.second = true; else e.first++;
    }
    sqlite3_finalize(st);
}

static HwidBanVerdict accountEvaluateHwidBan(long long id, const std::vector<HwidComponent>& comps, const char* ip) {
    HwidBanVerdict v;
    if (!g_db) return v;
    v.total = static_cast<int>(comps.size()) + ((ip && ip[0]) ? 1 : 0);
    if (v.total == 0) return v;

    std::map<long long, std::pair<int, bool>> tally;
    for (const HwidComponent& c : comps)
        hwidBanTally("SELECT DISTINCT h.account_id FROM account_hwids h JOIN accounts a ON a.id=h.account_id"
                     " WHERE h.hash=? AND h.tag=? AND h.account_id<>? AND a.disabled=1;",
                     tally, id, c.hex.c_str(), c.tag, false);
    if (ip && ip[0])
        hwidBanTally("SELECT DISTINCT i.account_id FROM account_ips i JOIN accounts a ON a.id=i.account_id"
                     " WHERE i.ip=? AND i.account_id<>? AND a.disabled=1;",
                     tally, id, ip, -1, true);

    for (const auto& kv : tally) {
        const int hardware = kv.second.first;
        const int matched  = hardware + (kv.second.second ? 1 : 0);
        if (matched > v.matched) {
            v.matchId   = kv.first;
            v.matched   = matched;
            v.hardware  = hardware;
            v.ipMatched = kv.second.second;
        }
    }
    if (v.matchId == 0) return v;

    const double ratio = static_cast<double>(v.matched) / static_cast<double>(v.total);
    v.ban = v.matched >= kHwidBanMinMatches && v.hardware >= kHwidBanMinHardware && ratio >= kHwidBanMinRatio;

    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db, "SELECT username FROM accounts WHERE id=?;", -1, &st, nullptr) == SQLITE_OK) {
        sqlite3_bind_int64(st, 1, v.matchId);
        if (sqlite3_step(st) == SQLITE_ROW) {
            const unsigned char* u = sqlite3_column_text(st, 0);
            v.matchName = u ? reinterpret_cast<const char*>(u) : "";
        }
        sqlite3_finalize(st);
    }
    return v;
}

static void accountMarkHwidBanned(long long id, const std::string& reason) {
    if (!g_db) return;
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(g_db,
            "UPDATE accounts SET disabled=1, hwid_banned=1, ban_reason=?, banned_at=? WHERE id=?;",
            -1, &st, nullptr) != SQLITE_OK) return;
    sqlite3_bind_text(st, 1, reason.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(st, 2, static_cast<sqlite3_int64>(time(nullptr)));
    sqlite3_bind_int64(st, 3, id);
    sqlite3_step(st);
    sqlite3_finalize(st);
}

static void accountsJson(std::string& o, const std::vector<long long>& onlineIds) {
    o += '[';
    if (g_db) {
        std::map<long long, AccountStatsRow> stats;
        allAccountStats(stats);   // one grouped scan for every account's history stats
        std::map<long long, AccountIdentityRow> ident;
        allAccountIdentity(ident);
        sqlite3_stmt* st = nullptr;
        if (sqlite3_prepare_v2(g_db,
                "SELECT id, username, disabled, last_login_at, hwid_banned, ban_reason FROM accounts ORDER BY username COLLATE NOCASE;",
                -1, &st, nullptr) == SQLITE_OK) {
            bool first = true;
            while (sqlite3_step(st) == SQLITE_ROW) {
                long long id = sqlite3_column_int64(st, 0);
                const unsigned char* uname = sqlite3_column_text(st, 1);
                bool disabled = sqlite3_column_int(st, 2) != 0;
                long long last = (sqlite3_column_type(st, 3) == SQLITE_NULL) ? 0 : sqlite3_column_int64(st, 3);
                bool hwidBanned = sqlite3_column_int(st, 4) != 0;
                const unsigned char* banReason = sqlite3_column_text(st, 5);
                bool online = false;
                for (long long oid : onlineIds) if (oid == id) { online = true; break; }
                auto sit = stats.find(id);
                long long matches  = (sit != stats.end()) ? sit->second.matches     : 0;
                long long playtime = (sit != stats.end()) ? sit->second.playtimeSec : 0;
                long long wins     = (sit != stats.end()) ? sit->second.wins        : 0;
                long long losses   = (sit != stats.end()) ? sit->second.losses      : 0;
                auto iit = ident.find(id);
                const AccountIdentityRow idr = (iit != ident.end()) ? iit->second : AccountIdentityRow{};
                if (!first) o += ','; first = false;
                char t[512];
                snprintf(t, sizeof(t),
                         "{\"id\":%lld,\"disabled\":%s,\"online\":%s,\"lastLogin\":%lld,"
                         "\"matches\":%lld,\"playtimeSec\":%lld,\"wins\":%lld,\"losses\":%lld,"
                         "\"hwids\":%lld,\"hwidShared\":%lld,\"ips\":%lld,\"ipShared\":%lld,"
                         "\"tamper\":%lld,\"tamperLast\":%lld,\"hwidLast\":",
                         id, disabled ? "true" : "false", online ? "true" : "false", last,
                         matches, playtime, wins, losses,
                         idr.hwids, idr.hwidShared, idr.ips, idr.ipShared,
                         idr.tamper, idr.tamperLast);
                o += t;
                hwidLastJson(o, id);
                o += hwidBanned ? ",\"hwidBanned\":true,\"banReason\":" : ",\"hwidBanned\":false,\"banReason\":";
                jStr(o, banReason ? reinterpret_cast<const char*>(banReason) : "");
                o += ",\"username\":";
                jStr(o, uname ? reinterpret_cast<const char*>(uname) : "");
                o += '}';
            }
            sqlite3_finalize(st);
        }
    }
    o += ']';
}

// Build one full-state JSON snapshot. Read-only walk of the live server state; no side
// effects. Kept compact and allocation-light (one growing string).
static void buildAdminSnapshot(std::string& o, uint64_t now)
{
    char t[256];
    o.clear();
    o += '{';
    snprintf(t, sizeof(t),
             "\"type\":\"snapshot\",\"t\":%llu,\"uptimeSec\":%llu,\"version\":%d,\"matchSize\":%d,\"holdMs\":%llu,\"pingCeilingMs\":%ld",
             static_cast<unsigned long long>(now),
             static_cast<unsigned long long>((now - g_bootMs) / 1000),
             MM_PROTOCOL_VERSION, kMatchSize,
             static_cast<unsigned long long>(kHoldMs), kPingQualityCeilingMs);
    o += t;

    // Tally + collect distinct live session ids + which accounts are online, in one pass.
    int connected = 0, queued = 0;
    std::vector<uint32_t>  sids;
    std::vector<long long> onlineIds;
    for (auto& c : g_clients) {
        if (c.dead) continue;
        ++connected;
        if (c.authed && c.accountId != 0) onlineIds.push_back(c.accountId);
        if (c.queued && c.session == 0) ++queued;
        if (c.session != 0) {
            bool seen = false;
            for (uint32_t s : sids) if (s == c.session) { seen = true; break; }
            if (!seen) sids.push_back(c.session);
        }
    }
    snprintf(t, sizeof(t), ",\"stats\":{\"connected\":%d,\"queued\":%d,\"sessions\":%zu}",
             connected, queued, sids.size());
    o += t;

    // relays
    o += ",\"relays\":[";
    for (size_t i = 0; i < g_relays.size(); ++i) {
        if (i) o += ',';
        o += "{\"idx\":"; o += std::to_string(i);
        o += ",\"ip\":"; jStr(o, g_relays[i].ip.c_str());
        snprintf(t, sizeof(t), ",\"port\":%u,\"default\":%s,\"healthy\":%s,\"probeable\":%s}",
                 g_relays[i].port, i == 0 ? "true" : "false",
                 relayHealthy(g_relays[i], now) ? "true" : "false",
                 g_relays[i].addrValid ? "true" : "false");
        o += t;
    }
    o += ']';

    // queue (searching, not yet in a session)
    o += ",\"queue\":[";
    bool firstQ = true;
    for (auto& c : g_clients) {
        if (c.dead || !c.queued || c.session != 0) continue;
        if (!firstQ) o += ',';
        firstQ = false;
        uint64_t forMs = (now >= c.queuedAtMs) ? now - c.queuedAtMs : 0;
        snprintf(t, sizeof(t), "{\"clientId\":\"%016llx\",",
                 static_cast<unsigned long long>(c.clientId));
        o += t;
        o += "\"name\":"; jStr(o, safeName(c));
        o += ",\"ip\":"; jStr(o, c.ip);
        snprintf(t, sizeof(t), ",\"mode\":%u,\"map\":%u,\"queuedForMs\":%llu,\"eligible\":%s,\"pings\":[",
                 c.mode, c.map, static_cast<unsigned long long>(forMs),
                 isRipe(c, now) ? "true" : "false");
        o += t;
        for (int r = 0; r < static_cast<int>(g_relays.size()) && r < MM_MAX_RELAYS; ++r) {
            if (r) o += ',';
            o += std::to_string(c.relayPing[r]);
        }
        o += "]}";
    }
    o += ']';

    // sessions (lobby / loading / live)
    o += ",\"sessions\":[";
    for (size_t si = 0; si < sids.size(); ++si) {
        uint32_t sid = sids[si];
        if (si) o += ',';

        const Client* rep = nullptr;
        int count = 0, ready = 0;
        for (auto& c : g_clients)
            if (!c.dead && c.session == sid) { if (!rep) rep = &c; ++count; if (c.ready) ++ready; }

        const char* phase = g_loadDeadline.count(sid) ? "loading"
                          : (g_lobby.count(sid)       ? "lobby" : "live");

        int lobbyPhase = -1, cd = 0;
        auto lit = g_lobby.find(sid);
        if (lit != g_lobby.end()) {
            // Same unsigned-underflow guard as pumpLobbies: formedMs can exceed now on a
            // just-formed lobby.
            int elapsed = (now <= lit->second.formedMs)
                            ? 0
                            : static_cast<int>((now - lit->second.formedMs) / 1000);
            if (elapsed < kLobbyFoundSecs)                             { lobbyPhase = 0; cd = 0; }
            else if (elapsed < kLobbyFoundSecs + kLobbyMapShownSecs)   { lobbyPhase = 1; cd = 0; }
            else {
                int into = elapsed - (kLobbyFoundSecs + kLobbyMapShownSecs);
                lobbyPhase = 2;
                cd = (into < kLobbyCountdownSecs) ? (kLobbyCountdownSecs - into) : 0;
            }
        }

        uint8_t relayIdx  = rep ? rep->matchRelayIdx : 0;
        const char* relayIp = (relayIdx < g_relays.size()) ? g_relays[relayIdx].ip.c_str() : "";
        uint8_t mapId     = rep ? rep->matchMap : 0;
        const char* mapNm = (mapId < g_mapCount) ? g_maps[mapId].name : "?";
        uint64_t ageMs    = (rep && now >= rep->matchFormedMs) ? now - rep->matchFormedMs : 0;

        snprintf(t, sizeof(t), "{\"id\":%u,\"phase\":\"%s\",\"relayIdx\":%u,", sid, phase, relayIdx);
        o += t;
        o += "\"relayIp\":"; jStr(o, relayIp);
        snprintf(t, sizeof(t), ",\"map\":%u,", mapId); o += t;
        o += "\"mapName\":"; jStr(o, mapNm);
        snprintf(t, sizeof(t),
                 ",\"ageMs\":%llu,\"lobbyPhase\":%d,\"countdown\":%d,\"ready\":%d,\"count\":%d,\"players\":[",
                 static_cast<unsigned long long>(ageMs), lobbyPhase, cd, ready, count);
        o += t;

        bool firstP = true;
        for (auto& c : g_clients) {
            if (c.dead || c.session != sid) continue;
            if (!firstP) o += ',';
            firstP = false;
            snprintf(t, sizeof(t), "{\"slot\":%u,\"clientId\":\"%016llx\",",
                     c.matchSlot, static_cast<unsigned long long>(c.clientId));
            o += t;
            o += "\"name\":"; jStr(o, safeName(c));
            o += ",\"ip\":"; jStr(o, c.ip);
            snprintf(t, sizeof(t),
                     ",\"team\":%u,\"teamName\":\"%s\",\"spawn\":%u,\"ready\":%s,\"pings\":[",
                     c.matchTeam, MMTeamName(c.matchTeam), c.matchSpawn, c.ready ? "true" : "false");
            o += t;
            for (int r = 0; r < static_cast<int>(g_relays.size()) && r < MM_MAX_RELAYS; ++r) {
                if (r) o += ',';
                o += std::to_string(c.relayPing[r]);
            }
            o += "]}";
        }
        o += "]}";
    }
    o += ']';

    // menu (present at the MP menu, idle - said HELLO, not searching, not in a session)
    o += ",\"menu\":[";
    bool firstM = true;
    for (auto& c : g_clients) {
        if (c.dead || !c.hello || c.queued || c.session != 0) continue;
        if (!firstM) o += ',';
        firstM = false;
        snprintf(t, sizeof(t), "{\"clientId\":\"%016llx\",",
                 static_cast<unsigned long long>(c.clientId));
        o += t;
        o += "\"name\":"; jStr(o, safeName(c));
        o += ",\"ip\":"; jStr(o, c.ip);
        o += '}';
    }
    o += ']';

    // accounts (the full account list from the store; online = has a live authed conn)
    o += ",\"accounts\":";
    accountsJson(o, onlineIds);

    // recent match history + server metrics
    o += ",\"matches\":";
    matchesJson(o, 25);
    o += ",\"metrics\":";
    metricsJson(o, connected);

    o += '}';
}

// Accept new control-panel watchers (loopback listener). Non-blocking; drains the
// backlog. Watcher sockets are non-blocking with a queued writer (see AdminClient.tx),
// so a wedged watcher cannot stall the game loop; one whose queue overflows is reaped.
// Queues an immediate snapshot so the panel populates at once.
static void acceptAdminClients()
{
    if (g_adminListen == INVALID_SOCKET) return;
    for (;;) {
        sockaddr_in from; socklen_t fl = sizeof(from);
        SOCKET cs = accept(g_adminListen, reinterpret_cast<sockaddr*>(&from), &fl);
        if (cs == INVALID_SOCKET) break;
        setNonBlocking(cs);   // accepted sockets do NOT inherit the listener's O_NONBLOCK
        std::string snap; buildAdminSnapshot(snap, nowMs()); snap.push_back('\n');
        AdminClient a; a.fd = cs;
        g_adminClients.push_back(std::move(a));
        adminSend(g_adminClients.back(), snap.data(), snap.size());
        logf("ADMIN    watcher connected (%zu total)", g_adminClients.size());
    }
}

// Queue one snapshot to every watcher; reap any whose queue overflowed/errored.
static void pushAdminSnapshots(uint64_t now)
{
    if (g_adminClients.empty()) return;
    std::string snap; buildAdminSnapshot(snap, now); snap.push_back('\n');
    for (auto& a : g_adminClients)
        adminSend(a, snap.data(), snap.size());
    for (size_t i = 0; i < g_adminClients.size(); ) {
        if (g_adminClients[i].dead) {
            CLOSESOCK(g_adminClients[i].fd);
            g_adminClients.erase(g_adminClients.begin() + i);
            logf("ADMIN    watcher disconnected (%zu left)", g_adminClients.size());
        } else {
            ++i;
        }
    }
}

// ---- admin account commands (control-panel -> matchmaker) -------------------
// The panel sends newline-delimited text commands over the same loopback connection it
// reads snapshots on: CREATE <username> | DISABLE <id> | ENABLE <id> | REGEN <id> |
// DELETE <id> | KICK <id> | BROADCAST <msg> | HWIDS <id> | IPS <id> | HWRESET <id> |
// IPRESET <id> | TAMPER <id> | TAMPERRESET <id>. Each gets one JSON line back, tagged
// {"type":"reply",...}; snapshots are tagged {"type":"snapshot",...}, so the panel routes
// by type.
static void sendAdminLine(AdminClient& a, std::string line)
{
    line.push_back('\n');
    adminSend(a, line.data(), line.size());
}

// Drop any live authenticated connection on this account, so disable / delete /
// token-regen take effect at once. Returns how many connections were dropped (KICK
// reports it; the other callers ignore it).
static int kickAccount(long long accId, const char* why = "account revoked")
{
    int n = 0;
    for (auto& o : g_clients)
        if (!o.dead && o.authed && o.accountId == accId) { o.dead = true; o.deadWhy = why; ++n; }
    return n;
}

static void handleAdminCommand(AdminClient& a, std::string line)
{
    while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
    if (line.empty()) return;

    size_t sp = line.find(' ');
    std::string verb = (sp == std::string::npos) ? line : line.substr(0, sp);
    std::string arg  = (sp == std::string::npos) ? std::string() : line.substr(sp + 1);
    while (!arg.empty() && arg.front() == ' ') arg.erase(arg.begin());

    auto ok = [&](const char* cmd, const std::string& extra) {
        std::string o = "{\"type\":\"reply\",\"cmd\":\""; o += cmd;
        o += "\",\"ok\":true"; o += extra; o += "}";
        sendAdminLine(a, o);
    };
    auto err = [&](const char* cmd, const std::string& msg) {
        std::string o = "{\"type\":\"reply\",\"cmd\":\""; o += cmd;
        o += "\",\"ok\":false,\"error\":"; jStr(o, msg.c_str()); o += "}";
        sendAdminLine(a, o);
    };

    if (verb == "CREATE") {
        long long id = 0; std::string token, e;
        if (accountCreate(arg, id, token, e)) {
            std::string extra = ",\"id\":" + std::to_string(id) + ",\"token\":";
            jStr(extra, token.c_str());
            extra += ",\"username\":"; jStr(extra, arg.c_str());
            ok("create", extra);
            logf("ADMIN    created account #%lld \"%s\"", id, arg.c_str());
        } else err("create", e);
    } else if (verb == "DISABLE" || verb == "ENABLE") {
        bool dis = (verb == "DISABLE");
        long long id = atoll(arg.c_str());
        if (accountSetDisabled(id, dis)) {
            if (dis) kickAccount(id);
            ok(dis ? "disable" : "enable", ",\"id\":" + std::to_string(id));
            logf("ADMIN    %s account #%lld", dis ? "disabled" : "enabled", id);
        } else err(dis ? "disable" : "enable", "no such account");
    } else if (verb == "REGEN") {
        long long id = atoll(arg.c_str());
        std::string token, e;
        if (accountRegen(id, token, e)) {
            kickAccount(id);   // the old token is now invalid
            std::string extra = ",\"id\":" + std::to_string(id) + ",\"token\":";
            jStr(extra, token.c_str());
            ok("regen", extra);
            logf("ADMIN    regenerated token for account #%lld", id);
        } else err("regen", e);
    } else if (verb == "DELETE") {
        long long id = atoll(arg.c_str());
        if (accountDelete(id)) {
            kickAccount(id);
            ok("delete", ",\"id\":" + std::to_string(id));
            logf("ADMIN    deleted account #%lld", id);
        } else err("delete", "no such account");
    } else if (verb == "KICK") {
        // Drop the account's live connection(s) without touching the account itself: the
        // token stays valid and the account can reconnect at once. This tick's dissolve
        // pass tears the match down by phase (re-queue / abort / end).
        long long id = atoll(arg.c_str());
        int n = kickAccount(id, "kicked by admin");
        if (n > 0) {
            ok("kick", ",\"id\":" + std::to_string(id) + ",\"kicked\":" + std::to_string(n));
            logf("ADMIN    kicked account #%lld (%d connection(s))", id, n);
        } else err("kick", "no live connection on that account");
    } else if (verb == "BROADCAST") {
        // arg is the whole message (may contain spaces). Push it to every authed client
        // as MM_BROADCAST; older clients that don't handle it simply ignore it.
        if (arg.empty()) { err("broadcast", "empty message"); }
        else {
            std::string msg = arg;
            if (msg.size() > MM_BROADCAST_MAX) msg.resize(MM_BROADCAST_MAX);
            int sent = 0;
            for (auto& c : g_clients) {
                if (c.dead || !c.authed) continue;
                if (sendFramed(c, MM_BROADCAST, msg.data(), static_cast<uint16_t>(msg.size()))) ++sent;
                else { c.dead = true; c.deadWhy = "send failed"; }
            }
            ok("broadcast", ",\"sent\":" + std::to_string(sent));
            logf("ADMIN    broadcast to %d client(s): \"%s\"", sent, msg.c_str());
        }
    } else if (verb == "HWIDS") {
        long long id = atoll(arg.c_str());
        if (!accountExists(id)) { err("hwids", "no such account"); }
        else {
            std::string extra = ",\"id\":" + std::to_string(id) + ",\"components\":";
            accountHwidsJson(extra, id);
            ok("hwids", extra);
        }
    } else if (verb == "IPS") {
        long long id = atoll(arg.c_str());
        if (!accountExists(id)) { err("ips", "no such account"); }
        else {
            std::string extra = ",\"id\":" + std::to_string(id) + ",\"ips\":";
            accountIpsJson(extra, id);
            ok("ips", extra);
        }
    } else if (verb == "HWRESET") {
        long long id = atoll(arg.c_str());
        if (!accountExists(id)) { err("hwreset", "no such account"); }
        else {
            const int n = accountClearTable("DELETE FROM account_hwids WHERE account_id=?;", id);
            if (n < 0) err("hwreset", sqlite3_errmsg(g_db));
            else {
                g_lastHwidLogin.erase(id);
                ok("hwreset", ",\"id\":" + std::to_string(id) + ",\"deleted\":" + std::to_string(n));
                logf("ADMIN    cleared %d hwid component(s) for account #%lld", n, id);
            }
        }
    } else if (verb == "TAMPER") {
        long long id = atoll(arg.c_str());
        if (!accountExists(id)) { err("tamper", "no such account"); }
        else {
            std::string extra = ",\"id\":" + std::to_string(id) + ",\"tamper\":";
            accountTamperJson(extra, id);
            ok("tamper", extra);
        }
    } else if (verb == "TAMPERRESET") {
        long long id = atoll(arg.c_str());
        if (!accountExists(id)) { err("tamperreset", "no such account"); }
        else {
            const int n = accountClearTable("DELETE FROM account_tamper WHERE account_id=?;", id);
            if (n < 0) err("tamperreset", sqlite3_errmsg(g_db));
            else {
                ok("tamperreset", ",\"id\":" + std::to_string(id) + ",\"deleted\":" + std::to_string(n));
                logf("ADMIN    cleared %d tamper record(s) for account #%lld", n, id);
            }
        }
    } else if (verb == "IPRESET") {
        long long id = atoll(arg.c_str());
        if (!accountExists(id)) { err("ipreset", "no such account"); }
        else {
            const int n = accountClearTable("DELETE FROM account_ips WHERE account_id=?;", id);
            if (n < 0) err("ipreset", sqlite3_errmsg(g_db));
            else {
                ok("ipreset", ",\"id\":" + std::to_string(id) + ",\"deleted\":" + std::to_string(n));
                logf("ADMIN    cleared %d ip(s) for account #%lld", n, id);
            }
        }
    } else {
        err("unknown", "unknown command");
    }
}

// Read available bytes from a watcher (gated on poll readability) and dispatch every
// complete command line.
static void handleAdminData(AdminClient& a)
{
    uint8_t tmp[1024];
    int n = recv(a.fd, reinterpret_cast<char*>(tmp), sizeof(tmp), 0);
    if (n == 0) { a.dead = true; return; }
    if (n < 0) {
        if (lastErrWouldBlock()) return;   // spurious wakeup on a non-blocking socket
        a.dead = true; return;
    }
    a.rx.insert(a.rx.end(), tmp, tmp + n);
    if (a.rx.size() > 8192) { a.dead = true; return; }   // command-flood guard
    for (;;) {
        auto nl = std::find(a.rx.begin(), a.rx.end(), static_cast<uint8_t>('\n'));
        if (nl == a.rx.end()) break;
        std::string line(a.rx.begin(), nl);
        a.rx.erase(a.rx.begin(), nl + 1);
        handleAdminCommand(a, line);
        if (a.dead) return;
    }
}

// ---- message handling -------------------------------------------------------
static void handleMsg(Client& c, uint8_t type, const uint8_t* body, uint16_t bodyLen)
{
    // AUTH GATE: only MM_AUTH and MM_PING (heartbeat) are accepted while the connection
    // is unauthenticated; anything else is refused with MM_REJECT_INVALID_TOKEN. The
    // connecting page reaches this checkpoint first, so a bad token surfaces there as
    // "INVALID TOKEN".
    if (!c.authed && type != MM_AUTH && type != MM_PING) {
        sendReject(c, MM_REJECT_INVALID_TOKEN);
        return;
    }

    switch (type) {
        case MM_AUTH: {
            if (bodyLen < sizeof(MMAuth)) { c.dead = true; c.deadWhy = "short auth"; break; }
            MMAuth a; memcpy(&a, body, sizeof(a));
            if (a.version != MM_PROTOCOL_VERSION) {
                logf("REJECT   %s auth wire v%u (server v%u) - version mismatch",
                     c.ip, a.version, MM_PROTOCOL_VERSION);
                sendReject(c, MM_REJECT_VERSION);
                break;
            }
            // The token field is fixed-width; take its printable prefix (hex chars).
            std::string token;
            for (int i = 0; i < MM_TOKEN_LEN; ++i) {
                char ch = a.token[i];
                if (ch == '\0' || ch == ' ') break;
                token += ch;
            }
            long long accId = 0; std::string uname; bool disabled = true;
            bool found = accountResolveToken(token, accId, uname, disabled);
            if (!found || disabled) {
                logf("REJECT   %s auth ip=%s - %s", uname.empty() ? "?" : uname.c_str(),
                     c.ip, !found ? "invalid token" : "account disabled");
                sendReject(c, MM_REJECT_INVALID_TOKEN);
                break;   // leave the connection; the client shows INVALID TOKEN and closes
            }
            accountRecordIp(accId, c.ip);

            HwidLogin hl;
            std::vector<HwidComponent> comps;
            if (bodyLen > sizeof(MMAuth)) {
                hl.present = true;
                if (parseHwidBlock(body + sizeof(MMAuth), bodyLen - sizeof(MMAuth), hl.flags, comps)) {
                    hl.reported = static_cast<int>(comps.size());
                    accountRecordHwids(accId, comps, hl);
                } else {
                    hl.malformed = true;
                    comps.clear();
                }
            }
            g_lastHwidLogin[accId] = hl;
            c.hwidReported  = hl.present && !hl.malformed ? hl.reported : -1;
            c.hwidMatched   = hl.matched;
            c.hwidAdded     = hl.added;
            c.hwidFlags     = hl.flags;
            c.hwidMalformed = hl.malformed;

            const HwidBanVerdict verdict = accountEvaluateHwidBan(accId, comps, c.ip);
            if (verdict.ban) {
                char reason[160];
                snprintf(reason, sizeof(reason), "hwid match %d/%d%s with banned #%lld %s",
                         verdict.matched, verdict.total, verdict.ipMatched ? " (incl. ip)" : "",
                         verdict.matchId, verdict.matchName.c_str());
                accountMarkHwidBanned(accId, reason);
                kickAccount(accId, "hwid banned");
                logf("HWBAN    %s (#%lld) ip=%s -> %s", uname.c_str(), accId, c.ip, reason);
                sendReject(c, MM_REJECT_INVALID_TOKEN);
                break;
            }
            if (verdict.matchId != 0)
                logf("HWID     %s (#%lld) overlaps banned #%lld %s: %d/%d%s (below threshold)",
                     uname.c_str(), accId, verdict.matchId, verdict.matchName.c_str(),
                     verdict.matched, verdict.total, verdict.ipMatched ? " incl. ip" : "");

            // Single session per account: drop any other live connection on this account.
            // The dead client's match is re-queued/aborted by the dissolve pass this tick.
            for (auto& o : g_clients) {
                if (&o == &c || o.dead) continue;
                if (o.authed && o.accountId == accId) { o.dead = true; o.deadWhy = "replaced"; }
            }
            c.authed    = true;
            c.accountId = accId;
            copyStr(c.name, sizeof(c.name), uname.c_str());   // authoritative name = account username
            accountTouchLogin(accId);

            MMAuthOk ok; memset(&ok, 0, sizeof(ok));
            copyStr(ok.username, sizeof(ok.username), uname.c_str());
            if (!sendFramed(c, MM_AUTH_OK, &ok, sizeof(ok))) { c.dead = true; c.deadWhy = "authok send failed"; }
            logf("AUTH     %s (account #%lld) ip=%s", uname.c_str(), accId, c.ip);
            if (!hl.present)
                logf("HWID     %s (#%lld) legacy client, no hwid block", uname.c_str(), accId);
            else if (hl.malformed)
                logf("HWID     %s (#%lld) malformed hwid block (%u bytes)", uname.c_str(), accId,
                     static_cast<unsigned>(bodyLen - sizeof(MMAuth)));
            else
                logf("HWID     %s (#%lld) components=%d matched=%d new=%d hv=%d partial=%d",
                     uname.c_str(), accId, hl.reported, hl.matched, hl.added,
                     (hl.flags & MM_HWID_FLAG_HYPERVISOR) ? 1 : 0,
                     (hl.flags & MM_HWID_FLAG_INCOMPLETE) ? 1 : 0);
            break;
        }
        case MM_QUEUE: {
            if (bodyLen < sizeof(MMQueue)) { c.dead = true; c.deadWhy = "short queue"; break; }
            MMQueue q; memcpy(&q, body, sizeof(q));

            // Identity (name, account) is fixed by MM_AUTH; the client-sent name and
            // clientId are ignored. Only the match preferences and measured pings are read.
            c.mode = q.mode;
            c.map  = q.map;
            c.primaryWeapon   = q.primaryWeapon;
            c.secondaryWeapon = q.secondaryWeapon;
            memcpy(c.relayPing, q.relayPing, sizeof(c.relayPing));   // per-relay RTT for the picker
            c.queuedAtMs = nowMs();                                  // (re)start this player's strict hold

            // Already in a match: dissolve before re-queuing so the old peer is never
            // stranded. Routed through memberGone, not leaveMatch: a loading match must
            // abort and a LIVE match must end via endLiveMatch, since re-queuing mid-game
            // peers would let this tick's former pair them into a phantom rematch.
            if (c.session != 0) memberGone(c, "requeue");

            c.queued = true;
            if (!sendFramed(c, MM_QUEUED, nullptr, 0)) { c.dead = true; c.deadWhy = "send failed"; }
            {
                // Log the reported pings so relay choices are auditable on the console.
                char pings[64]; int off = 0;
                for (int r = 0; r < static_cast<int>(g_relays.size()) &&
                                r < MM_MAX_RELAYS && off < static_cast<int>(sizeof(pings)) - 8; ++r) {
                    uint16_t p = q.relayPing[r];
                    if (p >= MM_PING_UNREACHABLE)
                        off += snprintf(pings + off, sizeof(pings) - off, "%s#%d:--", r ? " " : "", r);
                    else
                        off += snprintf(pings + off, sizeof(pings) - off, "%s#%d:%u", r ? " " : "", r, p);
                }
                logf("QUEUE    %s (account #%lld, mode=%u map=%u) pings=[%s]",
                     safeName(c), c.accountId, c.mode, c.map, g_relays.empty() ? "" : pings);
            }
            break;
        }
        case MM_HELLO: {
            // Presence at the MP menu. Identity comes from MM_AUTH; the body's
            // name/clientId are ignored and may be short or absent.
            c.hello = true;
            logf("HELLO    %s (account #%lld) ip=%s (at menu)", safeName(c), c.accountId, c.ip);
            break;
        }
        case MM_CANCEL: {
            if (c.session != 0) memberGone(c, "cancel");   // matched -> dissolve or abort
            else                logf("CANCEL   %s (left queue)", safeName(c));
            c.queued = false;
            break;
        }
        case MM_PING: {
            // Reap on failure: this is the highest-volume send in the server and is
            // reachable BEFORE auth, so an unchecked result lets a peer that stopped
            // reading pile pongs up unboundedly.
            if (!sendFramed(c, MM_PONG, nullptr, 0)) { c.dead = true; c.deadWhy = "send failed"; }
            break;
        }
        case MM_GET_CONFIG: {
            // Auth-gated already: MM_AUTH validated both the version and the token.
            std::vector<uint8_t> cfg;
            buildConfigBody(cfg);
            if (!sendFramed(c, MM_CONFIG, cfg.data(), static_cast<uint16_t>(cfg.size())))
                { c.dead = true; c.deadWhy = "config send failed"; }
            logf("CONFIG   -> %s (%d maps, %u bytes)",
                 safeName(c), g_mapCount, static_cast<unsigned>(cfg.size()));
            break;
        }
        case MM_READY: {
            if (c.session == 0) break;                    // not in a match -> ignore
            uint32_t sid = c.session;
            if (g_startedSessions.count(sid)) break;      // already live -> ignore stray readies
            // A READY is valid only after the lobby's launch cue (MM_LOBBY phase 2 /
            // countdown 0). An earlier one would arm the load barrier, and could start the
            // session, while pumpLobbies is still ticking the lobby, leaving a stale
            // g_lobby/g_loadDeadline pair that misroutes the live match's teardown into
            // MM_ABORT.
            if (g_lobby.count(sid)) break;
            c.ready = true;
            if (!g_loadDeadline.count(sid))               // first READY opens the load barrier
                g_loadDeadline[sid] = nowMs() + kLoadBarrierTimeoutMs;
            logf("READY    %s session=%u (%d/%d)", safeName(c), sid,
                 countSessionReady(sid), countSession(sid));
            if (countSessionReady(sid) >= countSession(sid))
                startSession(sid);                        // everyone loaded -> go
            break;
        }
        case MM_RESULT: {
            // The host reports the match winner. Only accept it from slot 0 (the host) of a
            // live match, and only once (matchSetWinner is guarded on winner_team IS NULL).
            if (c.session == 0 || bodyLen < 1 || c.matchSlot != 0) break;
            int winner = body[0];
            if (winner != MM_WINNER_SERAPHITES && winner != MM_WINNER_WLF && winner != MM_WINNER_DRAW) break;
            auto it = g_matchRow.find(c.session);
            if (it != g_matchRow.end()) {
                matchSetWinner(it->second, winner);
                logf("RESULT   session=%u winner=%d (%s)", c.session, winner, safeName(c));
            }
            break;
        }
        case MM_LEADERBOARD_REQ: {
            // Read-only public data, authed connections only. The DB work is cached
            // (leaderboardBody).
            if (!c.authed) break;
            const std::vector<uint8_t>& b = leaderboardBody();
            if (!sendFramed(c, MM_LEADERBOARD, b.data(), static_cast<uint16_t>(b.size())))
                { c.dead = true; c.deadWhy = "send failed"; }
            break;
        }
        case MM_ONLINE_REQ: {
            if (!c.authed) break;
            uint32_t n = onlineCount();
            if (!sendFramed(c, MM_ONLINE, &n, sizeof(n))) { c.dead = true; c.deadWhy = "send failed"; }
            break;
        }
        case MM_TAMPER: {
            if (c.accountId == 0 || bodyLen < sizeof(MMTamper)) break;
            if (c.tamperMsgs >= kTamperMaxMsgsPerConn) {
                if (!c.tamperFloodLogged) {
                    c.tamperFloodLogged = true;
                    logf("TAMPER   %s (#%lld) ip=%s flood - further reports on this connection dropped", safeName(c), c.accountId, c.ip);
                }
                break;
            }
            c.tamperMsgs++;
            MMTamper t; memcpy(&t, body, sizeof(t));
            if (t.kind != MM_TAMPER_DEBUGGER && t.kind != MM_TAMPER_PROCESS) break;
            char detail[MM_TAMPER_DETAIL_LEN];
            if (t.kind == MM_TAMPER_DEBUGGER) snprintf(detail, sizeof(detail), "0x%04x", static_cast<unsigned>(t.flags));
            else { memcpy(detail, t.detail, sizeof(detail)); sanitizeTamperDetail(detail, sizeof(detail)); }
            if (!detail[0]) break;
            long long matchId = 0;
            if (c.session != 0) { auto it = g_matchRow.find(c.session); if (it != g_matchRow.end()) matchId = it->second; }
            const bool stored = accountRecordTamper(c.accountId, t.kind, t.flags, t.pid, matchId, detail);
            logf("TAMPER   %s (#%lld) ip=%s kind=%s flags=0x%04x pid=%u detail=%s session=%u%s",
                 safeName(c), c.accountId, c.ip, t.kind == MM_TAMPER_DEBUGGER ? "debugger" : "process",
                 static_cast<unsigned>(t.flags), static_cast<unsigned>(t.pid), detail, c.session,
                 stored ? "" : " (not stored)");
            break;
        }
        default:
            break;  // unknown type: ignore (forward-compat)
    }
}

static void handleClientData(Client& c)
{
    uint8_t tmp[2048];
    int n = recv(c.fd, reinterpret_cast<char*>(tmp), sizeof(tmp), 0);
    if (n == 0) { c.dead = true; c.deadWhy = "closed";     return; }
    if (n <  0) {
        if (lastErrWouldBlock()) return;   // spurious wakeup on a non-blocking socket
        c.dead = true; c.deadWhy = "recv error"; return;
    }

    c.lastSeen = nowMs();                                  // any byte = alive
    c.rx.insert(c.rx.end(), tmp, tmp + n);
    if (c.rx.size() > static_cast<size_t>(kMaxRxBytes)) { c.dead = true; c.deadWhy = "rx overflow"; return; }

    while (c.rx.size() >= 2) {
        uint16_t total;
        memcpy(&total, c.rx.data(), 2);
        if (total == 0) { c.dead = true; c.deadWhy = "bad frame"; return; }
        if (c.rx.size() < static_cast<size_t>(2 + total)) break;
        uint8_t type = c.rx[2];
        handleMsg(c, type, c.rx.data() + 3, static_cast<uint16_t>(total - 1));
        c.rx.erase(c.rx.begin(), c.rx.begin() + 2 + total);
        if (c.dead) return;
    }
}

// ---- periodic status --------------------------------------------------------
static void logStatus()
{
    int conn = 0, queued = 0;
    std::vector<uint32_t> sessions;
    for (auto& c : g_clients) {
        if (c.dead) continue;
        ++conn;
        if (c.queued)      ++queued;
        if (c.session != 0) {
            bool seen = false;
            for (uint32_t s : sessions) if (s == c.session) { seen = true; break; }
            if (!seen) sessions.push_back(c.session);
        }
    }
    logf("STATUS   connected=%d queued=%d matches=%zu", conn, queued, sessions.size());
}

// ---- main -------------------------------------------------------------------
int main(int argc, char** argv)
{
    g_bootMs = nowMs();   // for uptime in the admin snapshot

#ifndef _WIN32
    // A send() to a peer that has closed (a game client that quit, or a closed control
    // panel) otherwise raises SIGPIPE, whose default action terminates the process.
    // Ignoring it makes send() return EPIPE, so only that one client is reaped.
    // (On Windows send() never raises a signal.)
    signal(SIGPIPE, SIG_IGN);
#endif

    int port      = (argc > 1) ? atoi(argv[1]) : kDefaultPort;
    if (port < 1 || port > 65534) {   // 65534: the admin port is port+1
        fprintf(stderr, "invalid listen port '%s' - using default %d\n",
                (argc > 1) ? argv[1] : "?", kDefaultPort);
        port = kDefaultPort;
    }
    g_adminPort   = port + 1;   // see g_adminPort: one instance per (listen, listen+1) pair
    std::string relay0Ip   = (argc > 2) ? argv[2] : "127.0.0.1";
    int relay0PortArg = (argc > 3) ? atoi(argv[3]) : 7000;
    if (relay0PortArg < 1 || relay0PortArg > 65535) relay0PortArg = 7000;
    uint16_t    relay0Port = static_cast<uint16_t>(relay0PortArg);
    int timeoutS  = (argc > 4) ? atoi(argv[4]) : kDefaultTimeoutS;
    if (timeoutS < 2) timeoutS = 2;
    g_clientTimeoutMs = static_cast<uint64_t>(timeoutS) * 1000ull;

    // Relay pool. The default relay is relayIp/relayPort (argv[2]/argv[3]); extra
    // relays are ip/port pairs from argv[5] onward, so the 4-arg invocation stays
    // valid and further relays are appended in pairs, e.g.
    //   ./matchmaker 7001 <ukIp> 7000 15 <usIp> 7000
    g_relays.push_back({ relay0Ip, relay0Port });
    for (int i = 5; i + 1 < argc && static_cast<int>(g_relays.size()) < MM_MAX_RELAYS; i += 2) {
        int rp = atoi(argv[i + 1]);
        if (rp < 1 || rp > 65535) {
            fprintf(stderr, "invalid relay port '%s' for relay %s - skipping\n", argv[i + 1], argv[i]);
            continue;
        }
        g_relays.push_back({ argv[i], static_cast<uint16_t>(rp) });
    }

#ifdef _WIN32
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) { fprintf(stderr, "WSAStartup failed\n"); return 1; }
#endif

    SOCKET listenSock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (listenSock == INVALID_SOCKET) { fprintf(stderr, "socket() failed\n"); return 1; }

    int yes = 1;
    setsockopt(listenSock, SOL_SOCKET, SO_REUSEADDR, reinterpret_cast<const char*>(&yes), sizeof(yes));

    // Non-blocking listen socket, so the whole accept backlog drains in one tick.
#ifdef _WIN32
    { u_long nb = 1; ioctlsocket(listenSock, FIONBIO, &nb); }
#else
    { int fl = fcntl(listenSock, F_GETFL, 0); fcntl(listenSock, F_SETFL, fl | O_NONBLOCK); }
#endif

    sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port        = htons(static_cast<uint16_t>(port));
    if (bind(listenSock, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0) {
        fprintf(stderr, "bind() to TCP %d failed\n", port); return 1;
    }
    if (listen(listenSock, 64) != 0) { fprintf(stderr, "listen() failed\n"); return 1; }

    logf("to1 matchmaker v%d on TCP %d  (match size %d, hold %llums, timeout %ds, %zu relay(s))",
         MM_PROTOCOL_VERSION, port, kMatchSize,
         static_cast<unsigned long long>(kHoldMs), timeoutS, g_relays.size());
    for (size_t i = 0; i < g_relays.size(); ++i)
        logf("  relay#%zu %s:%u%s", i, g_relays[i].ip.c_str(), g_relays[i].port,
             i == 0 ? "  (default)" : "");

    // ---- relay health setup --------------------------------------------------
    // Resolve each relay's address once and open a non-blocking UDP socket to probe them.
    // Every relay starts "healthy" (lastPongMs = now), so a live relay is not marked down
    // before the first probe round completes. Address resolution needs winsock started on
    // Windows, so this runs after WSAStartup.
    {
        uint64_t boot = nowMs();
        for (auto& r : g_relays) {
            memset(&r.addr, 0, sizeof(r.addr));
            r.addr.sin_family      = AF_INET;
            r.addr.sin_port        = htons(r.port);
            // inet_pton takes a strict dotted-quad; addrValid gates the health probes, so
            // a relay given as anything else is simply not probed.
            r.addrValid            = (inet_pton(AF_INET, r.ip.c_str(), &r.addr.sin_addr) == 1);
            r.lastPongMs           = boot;
            r.healthyLog           = true;
            if (!r.addrValid)
                logf("RELAY    warning: relay %s:%u is not a dotted IPv4 - health probes disabled for it",
                     r.ip.c_str(), r.port);
        }
        g_healthSock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (g_healthSock != INVALID_SOCKET) {
            setNonBlocking(g_healthSock);
#ifdef _WIN32
            // A probe to a dead relay port can bounce back as ICMP port-unreachable,
            // which Windows surfaces as WSAECONNRESET on the NEXT recvfrom, ending the
            // pong drain early. SIO_UDP_CONNRESET disables that behaviour. Not
            // applicable on Linux.
            { DWORD bytes = 0; BOOL off = FALSE;
              WSAIoctl(g_healthSock, SIO_UDP_CONNRESET, &off, sizeof(off),
                       nullptr, 0, &bytes, nullptr, nullptr); }
#endif
            sendHealthPings();   // kick off the first probe round immediately
        } else {
            logf("RELAY    warning: could not open health-probe socket - relay health checks disabled");
        }
    }

    // ---- admin telemetry listener (loopback only) ---------------------------
    // Bound to 127.0.0.1 and reached over an SSH tunnel. Best-effort: if it cannot bind,
    // the game server runs on without it.
    g_adminListen = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (g_adminListen != INVALID_SOCKET) {
        // On Windows SO_REUSEADDR permits another local process to co-bind this port and
        // take over watcher connections, so SO_EXCLUSIVEADDRUSE is used there. On POSIX
        // SO_REUSEADDR never allows two active listeners on the same address and eases a
        // fast restart.
#ifdef _WIN32
        int excl = 1;
        setsockopt(g_adminListen, SOL_SOCKET, SO_EXCLUSIVEADDRUSE, reinterpret_cast<const char*>(&excl), sizeof(excl));
        { u_long nb = 1; ioctlsocket(g_adminListen, FIONBIO, &nb); }
#else
        int ayes = 1;
        setsockopt(g_adminListen, SOL_SOCKET, SO_REUSEADDR, &ayes, sizeof(ayes));
        { int fl = fcntl(g_adminListen, F_GETFL, 0); fcntl(g_adminListen, F_SETFL, fl | O_NONBLOCK); }
#endif
        sockaddr_in aa; memset(&aa, 0, sizeof(aa));
        aa.sin_family      = AF_INET;
        aa.sin_addr.s_addr = htonl(INADDR_LOOPBACK);   // 127.0.0.1 - loopback only
        aa.sin_port        = htons(static_cast<uint16_t>(g_adminPort));
        if (bind(g_adminListen, reinterpret_cast<sockaddr*>(&aa), sizeof(aa)) != 0 ||
            listen(g_adminListen, 8) != 0) {
            logf("ADMIN    warning: could not bind telemetry on 127.0.0.1:%d - panel disabled", g_adminPort);
            CLOSESOCK(g_adminListen);
            g_adminListen = INVALID_SOCKET;
        } else {
            logf("ADMIN    telemetry on 127.0.0.1:%d (loopback only - SSH-tunnel to reach it)", g_adminPort);
        }
    }

    // Account store - a SQLite file in the working dir (~/matchmaker). Required for
    // auth: with no DB, accountResolveToken always fails, so every login is refused.
    accountsInit("accounts.db");

    uint64_t lastStatus       = nowMs();
    uint64_t lastHealthPing   = nowMs();
    uint64_t lastAdminSnapshot = nowMs();
    // Set when accept() fails for a reason OTHER than "no pending connection", typically
    // EMFILE (out of file descriptors). The pending connection stays in the backlog, so
    // poll() would report the listener readable again immediately and the loop would spin
    // at 100% CPU. Muting the listener briefly lets the rest of the tick (timeouts,
    // matchmaking, reaping) run and free descriptors.
    uint64_t acceptBackoffUntilMs = 0;
    static const uint64_t kAcceptBackoffMs = 200;
    std::vector<pollfd> pfds;

    for (;;) {
        // Rebuild the poll set: game listener, admin listener (if any), then clients.
        // Slot 0 is ALWAYS the game listener (code below indexes pfds[0]); during an
        // accept backoff it is registered with no events rather than omitted.
        pfds.clear();
        pollfd lp; memset(&lp, 0, sizeof(lp));
        lp.fd = listenSock;
        lp.events = (nowMs() < acceptBackoffUntilMs) ? 0 : static_cast<short>(POLLIN);
        pfds.push_back(lp);
        if (g_adminListen != INVALID_SOCKET) {
            pollfd ap; memset(&ap, 0, sizeof(ap));
            ap.fd = g_adminListen; ap.events = POLLIN;
            pfds.push_back(ap);
        }
        for (auto& c : g_clients) {
            if (c.dead) continue;
            pollfd p; memset(&p, 0, sizeof(p));
            p.fd = c.fd;
            // POLLOUT only while bytes are queued - registering it permanently would
            // make poll() return instantly every tick (sockets are almost always writable).
            p.events = static_cast<short>(POLLIN | (c.tx.size() > c.txOff ? POLLOUT : 0));
            pfds.push_back(p);
        }
        for (auto& a : g_adminClients) {   // watch panel connections for incoming commands
            if (a.dead) continue;
            pollfd p; memset(&p, 0, sizeof(p));
            p.fd = a.fd;
            p.events = static_cast<short>(POLLIN | (a.tx.size() > a.txOff ? POLLOUT : 0));
            pfds.push_back(p);
        }

        int ready = poll(pfds.data(), static_cast<unsigned>(pfds.size()), 250);
        if (ready < 0) {
#ifndef _WIN32
            if (errno == EINTR) continue;
#endif
            continue;
        }

        // New admin watchers (loopback). Found by fd so it is index-independent; the
        // client-service loop below harmlessly ignores this fd (it matches no client).
        if (g_adminListen != INVALID_SOCKET)
            for (size_t i = 0; i < pfds.size(); ++i)
                if (pfds[i].fd == g_adminListen && (pfds[i].revents & POLLIN)) { acceptAdminClients(); break; }

        // Drain the accept backlog.
        if (pfds[0].revents & POLLIN) {
            for (;;) {
                sockaddr_in from; socklen_t fl = sizeof(from);
                SOCKET cs = accept(listenSock, reinterpret_cast<sockaddr*>(&from), &fl);
                if (cs == INVALID_SOCKET) {
                    // EWOULDBLOCK is the normal exit: the backlog is drained. Anything
                    // else (EMFILE/ENFILE - out of descriptors) leaves the connection
                    // pending, so poll() would report the listener readable again at
                    // once; mute it briefly instead of spinning on it.
                    if (!lastErrWouldBlock()) {
                        acceptBackoffUntilMs = nowMs() + kAcceptBackoffMs;
                        static uint64_t lastAcceptErrLog = 0;
                        uint64_t t = nowMs();
                        if (t - lastAcceptErrLog > 5000) {
                            lastAcceptErrLog = t;
                            logf("CONNECT  accept() failed (out of descriptors?) - pausing accepts %llums",
                                 static_cast<unsigned long long>(kAcceptBackoffMs));
                        }
                    }
                    break;
                }

                // Connection cap: the port is internet-facing, and every Client costs
                // fds + buffers. Refuse the excess before allocating anything.
                size_t live = 0;
                for (auto& c : g_clients) if (!c.dead) ++live;
                if (live >= kMaxClients) {
                    CLOSESOCK(cs);
                    static uint64_t lastCapLog = 0;
                    uint64_t t = nowMs();
                    if (t - lastCapLog > 5000) {
                        lastCapLog = t;
                        logf("CONNECT  refused: at connection cap (%zu)", kMaxClients);
                    }
                    continue;
                }

                int one = 1;
                setsockopt(cs, IPPROTO_TCP, TCP_NODELAY, reinterpret_cast<const char*>(&one), sizeof(one));
                // NON-BLOCKING, always: accepted sockets do NOT inherit the listener's
                // O_NONBLOCK on Linux, and a blocking send to a stalled peer would freeze
                // this single-threaded loop. Unsent bytes queue on the client and drain on
                // POLLOUT instead.
                setNonBlocking(cs);
                char ip[INET_ADDRSTRLEN];
                inet_ntop(AF_INET, &from.sin_addr, ip, sizeof(ip));

                Client c;
                c.fd       = cs;
                c.name[0]  = 0;
                c.lastSeen = nowMs();              // grace until first message
                c.connectedAtMs = c.lastSeen;      // start the auth deadline
                copyStr(c.ip, sizeof(c.ip), ip);  // remember the source IP for the panel
                g_clients.push_back(std::move(c));

                logf("CONNECT  %s:%u", ip, ntohs(from.sin_port));
            }
        }

        // Client + watcher traffic: match poll slots back by fd and service. POLLOUT
        // drains a connection's queued outgoing bytes; POLLIN reads; HUP/ERR reaps.
        for (size_t i = 1; i < pfds.size(); ++i) {
            short re = pfds[i].revents;
            if (!(re & (POLLIN | POLLOUT | POLLHUP | POLLERR))) continue;
            if (pfds[i].fd == g_adminListen) continue;   // the listener was handled above
            bool matched = false;
            for (auto& c : g_clients) {
                if (!c.dead && c.fd == pfds[i].fd) {
                    if (re & (POLLHUP | POLLERR)) { c.dead = true; c.deadWhy = "hangup"; }
                    else {
                        if ((re & POLLOUT) && !txFlush(c.fd, c.tx, c.txOff))
                            { c.dead = true; c.deadWhy = "send failed"; }
                        if (!c.dead && (re & POLLIN)) handleClientData(c);
                    }
                    matched = true; break;
                }
            }
            if (matched) continue;
            for (auto& a : g_adminClients) {   // a panel connection sent a command
                if (!a.dead && a.fd == pfds[i].fd) {
                    if (re & (POLLHUP | POLLERR)) a.dead = true;
                    else {
                        if ((re & POLLOUT) && !txFlush(a.fd, a.tx, a.txOff)) a.dead = true;
                        if (!a.dead && (re & POLLIN)) handleAdminData(a);
                    }
                    break;
                }
            }
        }

        // Heartbeat timeout: reap connections that have gone silent. Also reap any
        // connection that hasn't authenticated within the grace window - otherwise an
        // unauthed peer could park a socket open forever by heartbeating.
        uint64_t now = nowMs();
        for (auto& c : g_clients) {
            if (c.dead) continue;
            if (now - c.lastSeen > g_clientTimeoutMs)            { c.dead = true; c.deadWhy = "timeout"; }
            else if (!c.authed && now - c.connectedAtMs > kAuthGraceMs) { c.dead = true; c.deadWhy = "auth timeout"; }
        }

        // Relay health: drain any pongs (cheap; non-blocking) and probe on a timer, then
        // log any UP/DOWN transition - all before matching, so the former routes on fresh
        // health this tick.
        drainHealthPongs(now);
        if (now - lastHealthPing >= kRelayHealthPingMs) { sendHealthPings(); lastHealthPing = now; }
        logHealthTransitions(now);

        // Dissolve every dead client's match BEFORE forming new ones, so survivors can
        // backfill immediately. In the lobby phase this re-queues the peers; once the
        // match is loading, memberGone aborts it for everyone.
        for (auto& c : g_clients)
            if (c.dead && c.session != 0) memberGone(c, c.deadWhy);

        // Load barrier: abort any loading match whose players haven't all signalled
        // READY in time (a player alive-but-stuck on a load that never completes).
        // Collect first - abortSession erases from g_loadDeadline as it goes.
        if (!g_loadDeadline.empty()) {
            std::vector<uint32_t> timedOut;
            // Any session still on the load barrier past its deadline is aborted. The test is
            // "past deadline and not started", with no ready < count condition: a session that
            // is committed, fully READY and still not started is the stuck case (startSession
            // refused it). An entry exists here only between the first MM_READY and start/abort.
            for (auto& kv : g_loadDeadline)
                if (now > kv.second && !g_startedSessions.count(kv.first))
                    timedOut.push_back(kv.first);
            for (uint32_t sid : timedOut) abortSession(sid, "load timeout", nullptr);
        }

        tryFormMatches(now);   // strict hold + relay-fair grouping

        pumpLobbies(now);   // broadcast the server-driven lobby countdown to forming matches

        pumpLobbyRosters(now);   // live "who is in the lobby" list for players still searching

        // Close out match-history rows whose session has emptied (match over), and
        // track the peak concurrent-connection metric.
        {
            int liveConns = 0;
            for (auto& c : g_clients) if (!c.dead) ++liveConns;
            if (liveConns > g_mPeakConnected) g_mPeakConnected = liveConns;
            for (auto it = g_startedSessions.begin(); it != g_startedSessions.end(); ) {
                if (countSession(*it) == 0) {                       // match over: everyone left
                    auto mr = g_matchRow.find(*it);
                    if (mr != g_matchRow.end()) { matchRecordEnd(mr->second); g_matchRow.erase(mr); }
                    g_sessionSize.erase(*it);
                    it = g_startedSessions.erase(it);
                } else ++it;
            }
        }

        if (now - lastStatus >= kStatusEveryMs) { logStatus(); lastStatus = now; }

        // Reap dead clients.
        for (size_t i = 0; i < g_clients.size(); ) {
            if (g_clients[i].dead) {
                CLOSESOCK(g_clients[i].fd);
                g_clients.erase(g_clients.begin() + i);
            } else {
                ++i;
            }
        }

        // Stream a fresh snapshot to any connected control-panel watchers (after the
        // reap, so the state is settled). No-op when nobody is watching.
        if (now - lastAdminSnapshot >= kAdminSnapshotMs) { pushAdminSnapshots(now); lastAdminSnapshot = now; }
    }

    CLOSESOCK(listenSock);
#ifdef _WIN32
    WSACleanup();
#endif
    return 0;
}
