// netdiag.c - the TWELVE WEEKS connect check, logged (a report: a Steam Deck in China pressed TWELVE WEEKS, the bar ran 11 s, the game fell back to
// the title with match state 0, three times; the daemon had answered the ext's own TCP ops at boot, so the failing step was winmm's, and nothing logged it).
// winmm talks to the daemon with plain ws2_32 calls through its import table (winmm IAT, image base 0x180000000): connect 0x180129988, send 0x1801299d8,
// recv 0x1801299c0, sendto 0x1801299e0, recvfrom 0x1801299c8. Per daemon.py: TCP login 0x0f -> 0x10 + 0x08 (auth), UDP 03+seq -> 04+seq (presence
// keepalive and the game-server check, sent to the 0x08 list's UDP endpoint). The wrappers only count and remember (no change to any call):
//   - TCP: connect calls (address, result, WSA error), bytes sent / received on winmm's sockets, last receive time;
//   - UDP: datagrams sent (first byte 0x03 counted apart) with their target, datagrams received (0x04 counted apart, sender), last reply time.
// lds (loadseq.c) calls netdiag_mark() when the entry page goes up and netdiag_report() when it leaves; the report line "connect check:" says what moved
// in between: no 04 back for the 03s sent = UDP to the server does not get through (firewall / ISP / VPN), no TCP bytes = the login path is down.
// t2r-no-netdiag.txt next to the exe = not installed.
typedef int (WINAPI *ncc_connect_t)(uintptr_t, const void *, int);
typedef int (WINAPI *ncc_send_t)(uintptr_t, const char *, int, int);
typedef int (WINAPI *ncc_recv_t)(uintptr_t, char *, int, int);
typedef int (WINAPI *ncc_sendto_t)(uintptr_t, const char *, int, int, const void *, int);
typedef int (WINAPI *ncc_recvfrom_t)(uintptr_t, char *, int, int, void *, int *);
typedef int (WINAPI *ncc_wsaerr_t)(void);
typedef void (WINAPI *ncc_wsaset_t)(int);
static ncc_connect_t g_ncc_connect; static ncc_send_t g_ncc_send; static ncc_recv_t g_ncc_recv;
static ncc_sendto_t g_ncc_sendto; static ncc_recvfrom_t g_ncc_recvfrom; static ncc_wsaerr_t g_ncc_wsaerr; static ncc_wsaset_t g_ncc_wsaset;
typedef struct {
    volatile LONG conn_n, conn_ok, conn_err;            // connect calls: returned 0 / returned an error other than WOULDBLOCK
    volatile LONG tcp_tx, tcp_rx, tcp_rx_err;           // send / recv calls that moved bytes; recv errors other than WOULDBLOCK (0 = peer closed counts too)
    volatile LONG udp_tx, udp_tx03, udp_rx, udp_rx04, udp_tx_err;
    volatile uint64_t tcp_rx_ms, udp_rx04_ms, udp_tx03_ms;
} ncc_cnt_t;
static ncc_cnt_t g_ncc;
static ncc_cnt_t g_ncc_mark;
static uint64_t g_ncc_mark_ms;
static volatile uint32_t g_ncc_conn_ip, g_ncc_udp_ip, g_ncc_rx_ip; static volatile uint16_t g_ncc_conn_port, g_ncc_udp_port, g_ncc_rx_port;
static volatile LONG g_ncc_conn_lasterr;
static int g_ncc_on;
static void ncc_addr(const void *sa, int len, volatile uint32_t *ip, volatile uint16_t *port) {
    const uint8_t *a = (const uint8_t *)sa;
    if (!a || len < 8 || IsBadReadPtr(a, 8) || *(const uint16_t *)a != 2) return;   // AF_INET only
    *port = (uint16_t)(a[2] << 8 | a[3]);
    memcpy((void *)ip, a + 4, 4);
}
static const char *ncc_ip(uint32_t ip, uint16_t port, char *b, size_t n) {
    const uint8_t *q = (const uint8_t *)&ip;
    if (!ip) snprintf(b, n, "none"); else snprintf(b, n, "%u.%u.%u.%u:%u", q[0], q[1], q[2], q[3], port);
    return b;
}
static int WINAPI ncc_connect_w(uintptr_t s, const void *sa, int len) {
    int r = g_ncc_connect(s, sa, len);
    int e = r ? (g_ncc_wsaerr ? g_ncc_wsaerr() : -1) : 0;
    ncc_addr(sa, len, &g_ncc_conn_ip, &g_ncc_conn_port);
    InterlockedIncrement(&g_ncc.conn_n);
    if (!r) InterlockedIncrement(&g_ncc.conn_ok);
    else if (e != 10035) { InterlockedIncrement(&g_ncc.conn_err); g_ncc_conn_lasterr = e; }   // (10035 WSAEWOULDBLOCK = non-blocking connect in progress)
    if (r && g_ncc_wsaset) g_ncc_wsaset(e);                       // (the caller reads WSAGetLastError after us)
    return r;
}
static int WINAPI ncc_send_w(uintptr_t s, const char *b, int n, int f) {
    int r = g_ncc_send(s, b, n, f);
    if (r > 0) InterlockedIncrement(&g_ncc.tcp_tx);
    return r;
}
static int WINAPI ncc_recv_w(uintptr_t s, char *b, int n, int f) {
    int r = g_ncc_recv(s, b, n, f);
    if (r > 0) { InterlockedIncrement(&g_ncc.tcp_rx); g_ncc.tcp_rx_ms = GetTickCount64(); }
    else {
        int e = r ? (g_ncc_wsaerr ? g_ncc_wsaerr() : -1) : 0;
        if (e != 10035) InterlockedIncrement(&g_ncc.tcp_rx_err);
        if (r && g_ncc_wsaset) g_ncc_wsaset(e);
    }
    return r;
}
static int WINAPI ncc_sendto_w(uintptr_t s, const char *b, int n, int f, const void *to, int tl) {
    int r = g_ncc_sendto(s, b, n, f, to, tl);
    if (r > 0) {
        InterlockedIncrement(&g_ncc.udp_tx);
        if (n > 0 && !IsBadReadPtr(b, 1) && (uint8_t)b[0] == 0x03) { InterlockedIncrement(&g_ncc.udp_tx03); g_ncc.udp_tx03_ms = GetTickCount64(); ncc_addr(to, tl, &g_ncc_udp_ip, &g_ncc_udp_port); }
    } else InterlockedIncrement(&g_ncc.udp_tx_err);
    return r;
}
static int WINAPI ncc_recvfrom_w(uintptr_t s, char *b, int n, int f, void *from, int *fl) {
    int r = g_ncc_recvfrom(s, b, n, f, from, fl);
    if (r > 0) {
        InterlockedIncrement(&g_ncc.udp_rx);
        if ((uint8_t)b[0] == 0x04) { InterlockedIncrement(&g_ncc.udp_rx04); g_ncc.udp_rx04_ms = GetTickCount64(); if (fl && !IsBadReadPtr(fl, 4)) ncc_addr(from, *fl, &g_ncc_rx_ip, &g_ncc_rx_port); }
    }
    return r;
}
static int ncc_iat(uint64_t slot, void *wrap, void **orig, const char *name) {
    void **p = (void **)VMA(slot);
    HMODULE ws = GetModuleHandleA("ws2_32.dll");
    void *real = ws ? (void *)GetProcAddress(ws, name) : NULL;
    if (IsBadReadPtr(p, 8) || !real || *p != real) { xlog("netdiag: winmm import %s at %llx is not ws2_32's (%p vs %p) - not wrapped", name, (unsigned long long)slot, IsBadReadPtr(p, 8) ? NULL : *p, real); return 0; }
    DWORD old;
    if (!VirtualProtect(p, 8, PAGE_READWRITE, &old)) return 0;
    *orig = real;
    InterlockedExchangePointer(p, wrap);
    VirtualProtect(p, 8, old, &old);
    return 1;
}
static void netdiag_install(void) {
    static int done;
    if (done) return;
    done = 1;
    FILE *f = exe_side_open("t2r-no-netdiag.txt", "r");
    if (f) { fclose(f); xlog("netdiag: off (t2r-no-netdiag.txt)"); return; }
    HMODULE ws = GetModuleHandleA("ws2_32.dll");
    if (!ws) { xlog("netdiag: ws2_32 not loaded - not installed"); return; }
    g_ncc_wsaerr = (ncc_wsaerr_t)GetProcAddress(ws, "WSAGetLastError");
    g_ncc_wsaset = (ncc_wsaset_t)GetProcAddress(ws, "WSASetLastError");
    int n = ncc_iat(0x180129988, (void *)ncc_connect_w, (void **)&g_ncc_connect, "connect")
          + ncc_iat(0x1801299d8, (void *)ncc_send_w, (void **)&g_ncc_send, "send")
          + ncc_iat(0x1801299c0, (void *)ncc_recv_w, (void **)&g_ncc_recv, "recv")
          + ncc_iat(0x1801299e0, (void *)ncc_sendto_w, (void **)&g_ncc_sendto, "sendto")
          + ncc_iat(0x1801299c8, (void *)ncc_recvfrom_w, (void **)&g_ncc_recvfrom, "recvfrom");
    g_ncc_on = n == 5;
    xlog("netdiag: %d of 5 winmm socket imports wrapped (connect / send / recv / sendto / recvfrom: counts only) - 'connect check:' at each TWELVE WEEKS entry", n);
}
// entry page up (TWELVE WEEKS pressed): remember the counters
static void netdiag_mark(void) {
    if (!g_ncc_on) return;
    g_ncc_mark = g_ncc; g_ncc_mark_ms = GetTickCount64();
}
// entry page left: what winmm's sockets did since the mark. ok = the engine went on into the menu world load (match state 1).
static void netdiag_report(int ok) {
    if (!g_ncc_on || !g_ncc_mark_ms) return;
    uint64_t now = GetTickCount64();
    ncc_cnt_t c = g_ncc, m = g_ncc_mark;
    long tx03 = c.udp_tx03 - m.udp_tx03, rx04 = c.udp_rx04 - m.udp_rx04, tcptx = c.tcp_tx - m.tcp_tx, tcprx = c.tcp_rx - m.tcp_rx;
    long conn = c.conn_n - m.conn_n, connerr = c.conn_err - m.conn_err, rxerr = c.tcp_rx_err - m.tcp_rx_err;
    char a[32], u[32], r[32], l[32];
    const char *why = ok ? "OK"
        : (tx03 > 0 && rx04 == 0) ? "FAILED - UDP pings to the server got NO reply (UDP blocked on the way: firewall / router / ISP / VPN)"
        : (conn > 0 && connerr > 0) ? "FAILED - the TCP connect to the server failed"
        : (tcptx > 0 && tcprx == 0) ? "FAILED - TCP sent, nothing came back from the server"
        : (tx03 == 0 && tcptx == 0) ? "FAILED - winmm sent nothing in the window"
        : "FAILED - server answered (cause not in the socket counts)";
    xlog("connect check: %s | %.1f s window | UDP 03 sent %ld (to %s, last %.1f s ago), 04 back %ld (from %s, last %s), other UDP in %ld, send errors %ld"
         " | TCP connects %ld (errors %ld, last error %ld, to %s), sends %ld, receives %ld (last %.1f s ago), receive errors / closes %ld",
         why, (now - g_ncc_mark_ms) / 1000.0, tx03, ncc_ip(g_ncc_udp_ip, g_ncc_udp_port, u, sizeof u),
         c.udp_tx03_ms ? (now - c.udp_tx03_ms) / 1000.0 : -1.0, rx04, ncc_ip(g_ncc_rx_ip, g_ncc_rx_port, r, sizeof r),
         c.udp_rx04_ms ? (snprintf(l, sizeof l, "%.1f s ago", (now - c.udp_rx04_ms) / 1000.0), l) : "never",
         (c.udp_rx - m.udp_rx) - rx04, (long)(c.udp_tx_err - m.udp_tx_err),
         conn, connerr, (long)g_ncc_conn_lasterr, ncc_ip(g_ncc_conn_ip, g_ncc_conn_port, a, sizeof a), tcptx, tcprx,
         c.tcp_rx_ms ? (now - c.tcp_rx_ms) / 1000.0 : -1.0, rxerr);
    g_ncc_mark_ms = 0;
}
