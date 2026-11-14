// ============================================================================
//  matchmaker-protocol.h  -  T2R Online matchmaker control protocol
//
//  Wire format of the matchmaker control connection (TCP, one persistent
//  connection per player), shared by the standalone server, the test client and
//  the in-game net-matchmaking module. Every message is length-framed:
//
//      [ uint16_t bodyLen ][ uint8_t type ][ body (bodyLen-1 bytes) ]
//
//  bodyLen counts the type byte PLUS the fields after it, so a 4-byte body is
//  framed as bodyLen=5. All multi-byte fields are little-endian.
// ============================================================================
#ifndef T2R_MATCHMAKER_PROTOCOL_H
#define T2R_MATCHMAKER_PROTOCOL_H

#include <cstdint>
#include <stdint.h>

// Bump when the wire format changes incompatibly. A client whose version does not
// match is refused with MM_REJECT on both the config fetch and the queue.
#define MM_PROTOCOL_VERSION 28

// Message types.
enum {
    MM_QUEUE       = 1,   // client -> server : join/refresh the queue (MMQueue)
    MM_CANCEL      = 2,   // client -> server : leave queue/lobby (no body)
    MM_QUEUED      = 3,   // server -> client : the sender is in the pool / searching (no body)
    MM_MATCH_FOUND = 4,   // server -> client : matched (MMMatchFound + roster)
    MM_PING        = 5,   // client -> server : heartbeat (no body)
    MM_PONG        = 6,   // server -> client : heartbeat reply (no body)
    MM_GET_CONFIG  = 7,   // client -> server : request the map config (body: [u8 version])
    MM_CONFIG      = 8,   // server -> client : the map list (variable; see format below)
    MM_READY       = 9,   // client -> server : the match level finished loading (no body)
    MM_START       = 10,  // server -> client : everyone is loaded, begin the match (no body)
    MM_ABORT       = 11,  // server -> client : match aborted (a player dropped/hung) - to menu (no body)
    MM_LOBBY       = 12,  // server -> client : pre-match lobby state (body: MMLobby)
    MM_REJECT      = 13,  // server -> client : refused (version / invalid token) - to error (body: MMReject)
    MM_HELLO       = 14,  // client -> server : present at the MP menu, not (yet) searching (MMHello)
    MM_AUTH        = 15,  // client -> server : authenticate with the account token (MMAuth) - FIRST message
    MM_AUTH_OK     = 16,  // server -> client : authenticated; carries the account username (MMAuthOk)
    MM_BROADCAST   = 17,  // server -> client : admin announcement; body is the message text (no struct)
    MM_RESULT      = 18,  // client(host) -> server : match outcome; body is 1 byte (see MM_WINNER_* below)
    MM_LEADERBOARD_REQ = 19,  // client -> server : request the top-wins leaderboard (no body)
    MM_LEADERBOARD     = 20,  // server -> client : leaderboard rows ([u8 count][count*MMLeaderEntry], rank order)
    MM_ONLINE_REQ      = 21,  // client -> server : request the online player count (no body)
    MM_ONLINE          = 22,  // server -> client : online player count (body: uint32, little-endian)
    MM_LOBBY_ROSTER    = 23,  // server -> client : the members of the forming lobby.
                              // Broadcast to every member of a forming lobby whenever its
                              // membership changes.
                              // Body: [u8 count] then per player [u8 nameLen][name bytes].
                              // The receiver's OWN name is included in the list.
    MM_TAMPER          = 24,
};

// MM_CONFIG body: the server-owned map list, followed by the relay list.
//
//     [ u8 mapCount ]
//     repeated mapCount times:
//         [ u8 nameLen ][ name bytes ]
//         [ u8 pathLen ][ preview-path bytes ]
//         [ u8 taskLen ][ load-task bytes ]
//         [ u8 spawns ]                        per-level spawn-point count
//     [ u8 relayCount ]
//     repeated relayCount times:
//         [ u8 ipLen ][ dotted-IPv4 bytes ]    e.g. "1.2.3.4"
//         [ u16 port ]                         little-endian
//
// Strings are NOT nul-terminated on the wire; each is length-prefixed. The map index
// in MM_MATCH_FOUND indexes into this map list. The relay at index 0 is the DEFAULT
// relay (fallback and tie-break winner); the client pings each relay and reports
// relayPing[i] for relay i in MMQueue.

// MM_RESULT body: a single byte naming the winner of the host's current match. Reported
// once, by the HOST only, at match end.
enum {
    MM_WINNER_SERAPHITES = 0,   // == MM_TEAM_SERAPHITES
    MM_WINNER_WLF        = 1,   // == MM_TEAM_WLF
    MM_WINNER_DRAW       = 2,
};

// MM_BROADCAST body is just the message bytes (UTF-8, not nul-terminated).
#define MM_BROADCAST_MAX 240   // max message bytes, enforced on both ends

// MM_REJECT body - the server refused this client. serverVersion is meaningful only
// for a version mismatch; it is 0/ignored for other reasons.
#pragma pack(push, 1)
struct MMReject {
    uint8_t reason;          // see MM_REJECT_* below
    uint8_t serverVersion;   // the server's MM_PROTOCOL_VERSION (for version mismatches)
};
#pragma pack(pop)
enum {
    MM_REJECT_VERSION       = 1,   // wire/protocol version mismatch
    MM_REJECT_INVALID_TOKEN = 2,   // token missing / unknown / account disabled -> "INVALID TOKEN"
};

#define MM_TOKEN_LEN 64   // account token: 64 lowercase hex chars (256-bit), NOT nul-terminated on the wire

// MM_LOBBY body - the authoritative lobby timeline tick for a match.
#pragma pack(push, 1)
struct MMLobby {
    uint8_t phase;       // 0 = match-found hold, 1 = map shown, 2 = countdown
    uint8_t countdown;   // phase 2: seconds left (10..1); 0 in phase 2 = launch now
};
#pragma pack(pop)

// Team ids assigned by the matchmaker at match formation (see MMMatchFound.yourTeam
// and MMRosterEntry.team). Players are split evenly; 0 = Seraphites, 1 = WLF.
enum {
    MM_TEAM_SERAPHITES = 0,
    MM_TEAM_WLF        = 1,
};

// Human-readable team name for logs / UI labels. Unknown ids -> "?".
static inline const char* MMTeamName(uint8_t team)
{
    switch (team) {
        case MM_TEAM_SERAPHITES: return "SERAPHITES";
        case MM_TEAM_WLF:        return "WLF";
        default:                 return "?";
    }
}

#define MM_NAME_LEN   32  // fixed-width player name field (nul-padded)
#define MM_MAX_SLOTS   8  // hard ceiling on roster size (engine cap is 3)
#define MM_MAX_RELAYS  4  // hard ceiling on the relay pool the client pings / reports

// relayPing sentinel: this relay timed out or was never measured. The relay picker
// treats it as the worst possible latency, so a reachable relay always wins over an
// unreachable one; a group unreachable on every relay falls back to the default relay
// (index 0). A client that measured no pings at all sends every entry as this value.
#define MM_PING_UNREACHABLE 0xFFFF

#pragma pack(push, 1)

// ---- MM_HELLO body ----------------------------------------------------------
// Sent once, right after the connection completes, when the player is present at the
// MP menu but not searching. Identity fields only; mode/map/pings/loadout arrive with
// MM_QUEUE. The same clientId dedup as MM_QUEUE applies.
typedef struct {
    uint8_t  version;            // MM_PROTOCOL_VERSION
    uint64_t clientId;           // stable per-player id (0 = unknown/legacy)
    char     name[MM_NAME_LEN];  // display name; ignored - the account username is authoritative
} MMHello;                       // 41 bytes (packed)

// ---- MM_AUTH body -----------------------------------------------------------
// The FIRST message a client sends after connecting; until the connection is
// authenticated the server answers nothing but MM_AUTH and MM_PING. token is the raw
// account token, MM_TOKEN_LEN hex chars, nul/space-padded if shorter (the server
// trims). It is the only field trusted for identity.
typedef struct {
    uint8_t version;             // MM_PROTOCOL_VERSION
    char    token[MM_TOKEN_LEN]; // 64 hex chars
} MMAuth;                        // 65 bytes (packed)

#define MM_HWID_BLOCK_VERSION   1
#define MM_HWID_MAX_COMPONENTS  16
#define MM_HWID_HASH_LEN        32

enum {
    MM_HWID_TAG_MACHINE_GUID = 1,
    MM_HWID_TAG_SMBIOS_UUID  = 2,
    MM_HWID_TAG_DISK_SERIAL  = 3,
    MM_HWID_TAG_MAC          = 4,
};

enum {
    MM_HWID_FLAG_HYPERVISOR = 0x01,
    MM_HWID_FLAG_INCOMPLETE = 0x02,
};

typedef struct {
    uint8_t blockVersion;
    uint8_t flags;
    uint8_t count;
} MMHwidBlock;

typedef struct {
    uint8_t tag;
    uint8_t hash[MM_HWID_HASH_LEN];
} MMHwidComponent;

// ---- MM_AUTH_OK body --------------------------------------------------------
// Sent on successful auth: the account's authoritative username. This is the ONLY
// source of a player's name.
typedef struct {
    char username[MM_NAME_LEN];  // server-owned account username, nul-padded
} MMAuthOk;                      // 32 bytes (packed)

enum {
    MM_TAMPER_DEBUGGER = 1,
    MM_TAMPER_PROCESS  = 2,
};

#define MM_TAMPER_DETAIL_LEN 64

typedef struct {
    uint8_t  kind;
    uint16_t flags;
    uint32_t pid;
    char     detail[MM_TAMPER_DETAIL_LEN];
} MMTamper;
static_assert(sizeof(MMTamper) == 71, "MMTamper layout");

// ---- MM_QUEUE body ----------------------------------------------------------
// The player asks to be matched. mode/map are opaque ids agreed by the game;
// the matchmaker only groups players whose (mode, map) match. clientId is a
// stable per-player token used to dedup reconnects: a new connection carrying a
// clientId that already has an entry replaces that entry.
typedef struct {
    uint8_t  version;            // MM_PROTOCOL_VERSION
    uint64_t clientId;           // stable per-player id (0 = unknown/legacy)
    char     name[MM_NAME_LEN];  // display name, nul-padded
    uint8_t  mode;               // game mode id
    uint8_t  map;                // map id
    uint64_t primaryWeapon;      // SID hash of the chosen primary weapon (0 = server default)
    uint64_t secondaryWeapon;    // SID hash of the chosen secondary weapon (0 = server default)
    uint16_t relayPing[MM_MAX_RELAYS]; // measured RTT (ms) to each relay, indexed to the
                                       //   MM_CONFIG relay list; MM_PING_UNREACHABLE = unknown
} MMQueue;                       // 67 bytes (packed)

// ---- MM_MATCH_FOUND body ----------------------------------------------------
// Fixed part below, immediately followed by `playerCount` MMRosterEntry records.
typedef struct {
    char     relayIp[16];        // relay IPv4, dotted, nul-padded ("1.2.3.4")
    uint16_t relayPort;          // relay UDP port
    uint32_t sessionId;          // this match's session id on the relay
    uint8_t  map;                // server-selected map id (the matchmaker owns the choice)
    uint8_t  yourSlot;           // recipient's slot within the session (0 = host)
    uint8_t  playerCount;        // number of MMRosterEntry records that follow
    uint8_t  yourSpawn;          // assigned spawn point, 1-indexed ("to1-spawn-point-<n>"); 0 = none
    uint8_t  yourTeam;           // recipient's team for this match (0 = SERAPHITES, 1 = WLF)
} MMMatchFound;                  // 27 bytes

typedef struct {
    uint8_t  slot;               // slot index (0 = host)
    char     name[MM_NAME_LEN];  // that player's name, nul-padded
    uint64_t primaryWeapon;      // that player's chosen primary weapon SID (0 = server default)
    uint64_t secondaryWeapon;    // that player's chosen secondary weapon SID (0 = server default)
    uint8_t  team;               // that player's team (0 = SERAPHITES, 1 = WLF)
} MMRosterEntry;                 // 50 bytes

// ---- MM_LEADERBOARD body ----------------------------------------------------
// Top players by wins. Body = [uint8_t count][count * MMLeaderEntry] in rank
// order (index 0 = placement #1); count <= MM_LEADERBOARD_MAX.
#define MM_LEADERBOARD_MAX 10  // top-N rows returned / rendered
typedef struct {
    char     name[MM_NAME_LEN];  // account username, nul-padded
    uint32_t wins;
    uint32_t losses;
    float    winloss_ratio;
    uint32_t elo;
} MMLeaderEntry;                 // 48 bytes (packed)

#pragma pack(pop)

#endif // T2R_MATCHMAKER_PROTOCOL_H
