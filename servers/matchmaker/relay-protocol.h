// ============================================================================
//  relay-protocol.h - wire format shared by the T2R relay server and the game.
//
//  The relay is a per-session packet switch: clients REGISTER a (session, slot),
//  which is how the relay learns their public address, then send DATA packets the
//  relay forwards to the other slots in the same session. Only this outer header
//  is inspected; the game payload is opaque to the relay.
//
//  Both ends are x86-64 little-endian, and sessionId is an opaque token minted
//  by the matchmaker (never interpreted arithmetically), so fields are sent as
//  raw bytes with no byte-swapping.
//
//  No game or SDK dependencies.
// ============================================================================
#ifndef T2R_RELAY_PROTOCOL_H
#define T2R_RELAY_PROTOCOL_H

#include <stdint.h>

// Message type - the first byte of every relay packet.
enum {
    RELAY_REGISTER     = 0,   // client -> relay : claim a (session, slot); also the keepalive
    RELAY_REGISTER_ACK = 1,   // relay  -> client: registration confirmed
    RELAY_DATA         = 2,   // client -> relay -> client(s): one game packet
    RELAY_PING         = 3,   // client -> relay : stateless latency probe (RelayPing); no session touched
    RELAY_PONG         = 4,   // relay  -> client: echo of the probe (RelayPing), for RTT measurement
};

// destSlot sentinel: forward to every active slot in the session except the sender.
#define RELAY_BROADCAST 0xFF

// Slots per session. The game uses slots 0..2; slot 0 is the host.
#define RELAY_MAX_SLOTS 8

// Max game payload (bytes) carried in one RELAY_DATA packet: the largest datagram
// is sizeof(RelayDataHeader) + RELAY_MAX_PAYLOAD. The client's kRelayMaxPayload in
// net-transport and the relay's recv buffer must both match this value; a smaller
// recv buffer truncates or drops oversized datagrams.
#define RELAY_MAX_PAYLOAD 4096

#pragma pack(push, 1)

typedef struct {
    uint8_t  type;        // = RELAY_REGISTER
    uint32_t sessionId;   // opaque token from the matchmaker
    uint8_t  slot;        // which slot this client occupies
} RelayRegister;

// RELAY_DATA: this header is immediately followed by the opaque game payload.
typedef struct {
    uint8_t  type;        // = RELAY_DATA
    uint32_t sessionId;   // which session to route within
    uint8_t  srcSlot;     // sender's slot; the relay overwrites this with the slot
                          //   it verified from the sender's address
    uint8_t  destSlot;    // a specific slot, or RELAY_BROADCAST
} RelayDataHeader;

// RELAY_PING / RELAY_PONG: stateless round-trip probe for measuring latency to this
// relay. Valid before any session exists; the relay echoes the packet back with type
// set to RELAY_PONG and creates or touches no session state. nonce is returned
// unchanged, pairing a reply with its probe so stale or duplicate pongs are ignored.
typedef struct {
    uint8_t  type;        // = RELAY_PING (request) or RELAY_PONG (reply)
    uint32_t nonce;       // opaque token echoed back unchanged
} RelayPing;

#pragma pack(pop)

#endif // T2R_RELAY_PROTOCOL_H
