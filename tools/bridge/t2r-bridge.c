// t2r-bridge.exe — Twelve Weeks Steam bridge (Spacewar appid 480).
//
// Runs as a SEPARATE process from the game (game=2531310, bridge=480) so it
// never interferes with TLOU2's own Steam context. Two jobs:
//
//   PHASE A (name): SteamAPI_Init(480) -> read Steam persona name + SteamID64,
//     read the mod token from tlou-ii-mp.json, report {token,steamid,name} to
//     the daemon (opcode 0xF0). Daemon then echoes the real Steam name back to
//     the game in its 0x10 auth reply -> lobby shows the correct player name.
//
//   PHASE B (P2P data plane): local UDP <-> ISteamNetworkingMessages bridge.
//     The daemon hands us the matched peer's SteamID64 (0xF1). Gameplay UDP the
//     game sends to our LOCAL_UDP port is relayed to that peer over Steam P2P,
//     and Steam messages from the peer are written back to the game's UDP addr.
//     (Wiring the game's gameplay socket to LOCAL_UDP + the 0x14 peer handoff is
//     pending a live 2-player capture; the transport itself is implemented here.)
//
// Steam flat C API is resolved at runtime via GetProcAddress (no SDK headers).
// Build: build.sh (llvm-mingw). Run: run-bridge.sh (Proton, SteamAppId=480).

#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#define DAEMON_IP   "127.0.0.1"   // control-plane daemon (set to VPS IP for deploy)
#define DAEMON_PORT 7001
#define LOCAL_UDP   7777          // game gameplay UDP is redirected here (bridge)
#define P2P_CHANNEL 0
#define SEND_UNRELIABLE 0         // k_nSteamNetworkingSend_Unreliable
#define JSON_PATH "tlou-ii-mp.json"

// ---- Steam flat API function pointer typedefs ----
typedef int      (*fn_Init)(void);
typedef void     (*fn_Shutdown)(void);
typedef void     (*fn_RunCallbacks)(void);
typedef void*    (*fn_Friends)(void);
typedef void*    (*fn_User)(void);
typedef void*    (*fn_NetMsgs)(void);
typedef const char* (*fn_GetPersonaName)(void*);
typedef uint64_t (*fn_GetSteamID)(void*);
typedef void     (*fn_IdentClear)(void*);
typedef void     (*fn_IdentSetID64)(void*, uint64_t);
typedef int      (*fn_SendToUser)(void*, const void* ident, const void* data,
                                  uint32_t len, int flags, int channel);
typedef int      (*fn_RecvOnChannel)(void*, int channel, void** msgs, int maxMsgs);
typedef int      (*fn_AcceptSession)(void*, const void* ident);

static fn_RunCallbacks    RunCallbacks;
static fn_NetMsgs         GetNetMsgs;
static fn_IdentClear      IdentClear;
static fn_IdentSetID64    IdentSetID64;
static fn_SendToUser      SendToUser;
static fn_RecvOnChannel   RecvOnChannel;
static fn_AcceptSession   AcceptSession;

// SteamNetworkingMessage_t: we only touch m_pData(0x00), m_cbSize(0x08),
// m_identityPeer(0x10). Release via the flat helper.
typedef void (*fn_MsgRelease)(void*);
static fn_MsgRelease MsgRelease;
typedef uint64_t (*fn_IdentGetID64)(void*);
static fn_IdentGetID64 IdentGetID64;

static void* g_netmsgs = NULL;
static uint64_t g_peer = 0;       // matched peer SteamID64 (0 until 0xF1)

#define IDENT_SZ 256              // SteamNetworkingIdentity is 136B; over-allocate

static void logline(const char* s){ fprintf(stderr, "[bridge] %s\n", s); fflush(stderr); }

// read token (64 hex chars) from tlou-ii-mp.json  {"token":"...."}
static int read_token(char* out64){
    FILE* f = fopen(JSON_PATH, "rb");
    if(!f){ return 0; }
    char buf[512]; size_t n = fread(buf,1,sizeof(buf)-1,f); fclose(f); buf[n]=0;
    char* p = strstr(buf, "token");
    if(!p) return 0;
    p = strchr(p, ':'); if(!p) return 0;
    p = strchr(p, '"'); if(!p) return 0; p++;
    char* e = strchr(p, '"'); if(!e) return 0;
    size_t len = e - p; if(len != 64) return 0;
    memcpy(out64, p, 64); out64[64]=0;
    return 1;
}

// framed daemon message: [u16 len LE][u8 op][payload], len = 1+payloadlen
static int send_frame(SOCKET s, uint8_t op, const uint8_t* pl, uint16_t pln){
    uint8_t hdr[3]; uint16_t ln = (uint16_t)(1+pln);
    hdr[0]=ln&0xff; hdr[1]=(ln>>8)&0xff; hdr[2]=op;
    if(send(s,(char*)hdr,3,0)!=3) return 0;
    if(pln && send(s,(char*)pl,pln,0)!=pln) return 0;
    return 1;
}

// persistent control socket to daemon; returns connected SOCKET or INVALID
static SOCKET daemon_connect(void){
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if(s==INVALID_SOCKET) return s;
    struct sockaddr_in a; memset(&a,0,sizeof a);
    a.sin_family=AF_INET; a.sin_port=htons(DAEMON_PORT);
    inet_pton(AF_INET, DAEMON_IP, &a.sin_addr);
    if(connect(s,(struct sockaddr*)&a,sizeof a)!=0){ closesocket(s); return INVALID_SOCKET; }
    return s;
}

int main(void){
    WSADATA w; WSAStartup(MAKEWORD(2,2), &w);

    // force Spacewar appid so we never touch the game's Steam context
    SetEnvironmentVariableA("SteamAppId", "480");
    SetEnvironmentVariableA("SteamGameId", "480");

    HMODULE api = LoadLibraryA("steam_api64.dll");
    if(!api){ logline("LoadLibrary steam_api64.dll FAILED"); return 1; }

    fn_Init Init                 = (fn_Init)GetProcAddress(api,"SteamAPI_Init");
    fn_Shutdown Shutdown         = (fn_Shutdown)GetProcAddress(api,"SteamAPI_Shutdown");
    RunCallbacks                 = (fn_RunCallbacks)GetProcAddress(api,"SteamAPI_RunCallbacks");
    fn_Friends GetFriends        = (fn_Friends)GetProcAddress(api,"SteamAPI_SteamFriends_v017");
    fn_User    GetUser           = (fn_User)GetProcAddress(api,"SteamAPI_SteamUser_v023");
    GetNetMsgs                   = (fn_NetMsgs)GetProcAddress(api,"SteamAPI_SteamNetworkingMessages_SteamAPI_v002");
    fn_GetPersonaName GetName    = (fn_GetPersonaName)GetProcAddress(api,"SteamAPI_ISteamFriends_GetPersonaName");
    fn_GetSteamID GetID          = (fn_GetSteamID)GetProcAddress(api,"SteamAPI_ISteamUser_GetSteamID");
    IdentClear                   = (fn_IdentClear)GetProcAddress(api,"SteamAPI_SteamNetworkingIdentity_Clear");
    IdentSetID64                 = (fn_IdentSetID64)GetProcAddress(api,"SteamAPI_SteamNetworkingIdentity_SetSteamID64");
    IdentGetID64                 = (fn_IdentGetID64)GetProcAddress(api,"SteamAPI_SteamNetworkingIdentity_GetSteamID64");
    SendToUser                   = (fn_SendToUser)GetProcAddress(api,"SteamAPI_ISteamNetworkingMessages_SendMessageToUser");
    RecvOnChannel                = (fn_RecvOnChannel)GetProcAddress(api,"SteamAPI_ISteamNetworkingMessages_ReceiveMessagesOnChannel");
    AcceptSession                = (fn_AcceptSession)GetProcAddress(api,"SteamAPI_ISteamNetworkingMessages_AcceptSessionWithUser");
    MsgRelease                   = (fn_MsgRelease)GetProcAddress(api,"SteamAPI_SteamNetworkingMessage_t_Release");

    if(!Init || !GetFriends || !GetUser || !GetName || !GetID){
        logline("missing required Steam exports"); return 1;
    }
    if(!Init()){ logline("SteamAPI_Init FAILED (is Steam running? appid 480 owned?)"); return 1; }
    logline("SteamAPI_Init OK (appid 480)");

    void* friends = GetFriends();
    void* user    = GetUser();
    g_netmsgs     = GetNetMsgs ? GetNetMsgs() : NULL;

    const char* pname = GetName(friends);
    uint64_t sid = GetID(user);
    char name[64]; strncpy(name, pname?pname:"PLAYER", sizeof(name)-1); name[63]=0;
    { char m[128]; snprintf(m,sizeof m,"persona='%s' steamid=%llu", name, (unsigned long long)sid); logline(m); }

    char token[65];
    if(!read_token(token)){ logline("WARN: no token from tlou-ii-mp.json; using zeros"); memset(token,'0',64); token[64]=0; }

    // ---- PHASE A: report {token, steamid, name} to daemon (opcode 0xF0) ----
    // payload = [64B token][8B steamid LE][1B namelen][name]
    SOCKET d = daemon_connect();
    if(d!=INVALID_SOCKET){
        uint8_t pl[64+8+1+64]; int o=0;
        memcpy(pl+o, token, 64); o+=64;
        for(int i=0;i<8;i++) pl[o++] = (uint8_t)((sid>>(8*i))&0xff);
        uint8_t nl = (uint8_t)strlen(name); pl[o++]=nl;
        memcpy(pl+o, name, nl); o+=nl;
        if(send_frame(d, 0xF0, pl, (uint16_t)o)) logline("reported name+steamid to daemon (0xF0)");
        else logline("WARN: 0xF0 report send failed");
    } else logline("WARN: daemon not reachable; name report skipped");

    // ---- local UDP socket for the gameplay bridge ----
    SOCKET u = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    struct sockaddr_in la; memset(&la,0,sizeof la);
    la.sin_family=AF_INET; la.sin_port=htons(LOCAL_UDP);
    inet_pton(AF_INET, "127.0.0.1", &la.sin_addr);
    bind(u,(struct sockaddr*)&la,sizeof la);
    u_long nb=1; ioctlsocket(u, FIONBIO, &nb);   // nonblocking
    if(d!=INVALID_SOCKET){ u_long nb2=1; ioctlsocket(d, FIONBIO, &nb2); }
    struct sockaddr_in game_addr; int have_game=0; int gal=sizeof game_addr;

    uint8_t ident[IDENT_SZ];
    uint8_t rbuf[2048];
    void* rxmsgs[16];

    logline("bridge loop running (local UDP :7777 <-> Steam P2P)");
    for(;;){
        RunCallbacks();

        // (1) daemon control: peer assignment 0xF1 = [8B peer steamid LE]
        if(d!=INVALID_SOCKET){
            uint8_t cb[512]; int r = recv(d,(char*)cb,sizeof cb,0);
            if(r>=3){
                uint16_t ln = cb[0] | (cb[1]<<8); uint8_t op = cb[2];
                if(op==0xF1 && ln>=9 && r>=11){   // (r>=11: all 8 steamid bytes were received)
                    uint64_t peer=0; for(int i=0;i<8;i++) peer |= ((uint64_t)cb[3+i])<<(8*i);
                    g_peer = peer;
                    char m[64]; snprintf(m,sizeof m,"peer assigned steamid=%llu",(unsigned long long)peer); logline(m);
                    if(g_netmsgs && AcceptSession){ // pre-accept so first packet isn't dropped
                        memset(ident,0,IDENT_SZ); if(IdentClear) IdentClear(ident);
                        IdentSetID64(ident, g_peer); AcceptSession(g_netmsgs, ident);
                    }
                }
            }
        }

        // (2) game -> peer: read local UDP, send over Steam
        if(g_netmsgs && SendToUser && g_peer){
            for(;;){
                int rl = recvfrom(u,(char*)rbuf,sizeof rbuf,0,(struct sockaddr*)&game_addr,&gal);
                if(rl<=0) break;
                have_game=1;
                // keepalive [03][u32 seq] -> answer [04][seq] LOCALLY so the game's
                // game-server check passes (bridge poses as the relay endpoint).
                if(rl>=5 && rbuf[0]==0x03){
                    uint8_t pong[5]; pong[0]=0x04; memcpy(pong+1, rbuf+1, 4);
                    sendto(u,(char*)pong,5,0,(struct sockaddr*)&game_addr,sizeof game_addr);
                    continue;
                }
                // real gameplay packet -> tunnel to the matched Steam peer
                memset(ident,0,IDENT_SZ); if(IdentClear) IdentClear(ident);
                IdentSetID64(ident, g_peer);
                SendToUser(g_netmsgs, ident, rbuf, (uint32_t)rl, SEND_UNRELIABLE, P2P_CHANNEL);
            }
        }

        // (3) peer -> game: pull Steam messages, write back to game's UDP addr
        if(g_netmsgs && RecvOnChannel){
            int n = RecvOnChannel(g_netmsgs, P2P_CHANNEL, rxmsgs, 16);
            for(int i=0;i<n;i++){
                void* m = rxmsgs[i];
                void* data = *(void**)((uint8_t*)m + 0x00);
                int   sz   = *(int*)((uint8_t*)m + 0x08);
                if(have_game && data && sz>0)
                    sendto(u,(char*)data,sz,0,(struct sockaddr*)&game_addr,sizeof game_addr);
                if(MsgRelease) MsgRelease(m);
            }
        }

        Sleep(1);
    }
    // unreachable; kept for completeness
    Shutdown(); WSACleanup(); return 0;
}
