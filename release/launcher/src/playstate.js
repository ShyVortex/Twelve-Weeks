/**
 * @file Pure game/launcher state transitions shared by renderer and main.
 */
'use strict';
// Pure helpers of the PLAY flow, shared by the main process (lib/game.js) and the window (src/app.js), unit-tested in test/selftest.js.
(function (root) {
  const P = {};

  // t2r-slim.exe prints "t2r-slim: progress <done> <total>" (weighted bytes of the whole job, one line per percent)
  P.parseSlimLine = (line) => {
    const m = /^t2r-slim: progress (\d+) (\d+)\s*$/.exec(String(line || ''));
    if (!m) return null;
    const done = +m[1],
      total = +m[2];
    return total > 0 && done <= total ? { done, total } : null;
  };

  // seconds left, or null while too little is known (first 2 s / first 3 %)
  P.eta = (done, total, elapsedMs) => {
    if (!(total > 0) || !(done > 0) || elapsedMs < 2000 || done / total < 0.03) return null;
    return Math.max(0, Math.round(((elapsedMs / 1000) * (total - done)) / done));
  };

  // an older t2r-slim.exe prints no progress: an honest-looking estimate (fraction 0..0.95) from the elapsed time, about a minute expected
  P.estimate = (elapsedMs, expectedMs = 60000) =>
    Math.min(0.95, 1 - Math.exp(-elapsedMs / (expectedMs * 0.7)));

  // Which leftover tlou-ii processes may be ended. `before` = pids that existed when PLAY was pressed, `ours` = pids this launcher started,
  // `now` = [{id, window}]. A process this launcher started is never touched; a pre-existing windowless one is waited for (it may be a slow
  // cold boot of the player's own start) and only after graceMs the user is asked.
  P.leftover = ({ before, ours, now, waitedMs, graceMs = 90000 }) => {
    const b = new Set(before || []),
      o = new Set(ours || []);
    const cand = (now || []).filter((p) => !o.has(p.id) && b.has(p.id));
    if (cand.some((p) => p.window))
      return { action: 'running', pids: cand.filter((p) => p.window).map((p) => p.id) };
    const stuck = cand.filter((p) => !p.window).map((p) => p.id);
    if (!stuck.length) return { action: 'none', pids: [] };
    return { action: waitedMs < graceMs ? 'wait' : 'ask', pids: stuck };
  };

  // The launcher's idea of the game: idle | preparing (Play flow running) | starting (process, no window yet) | running (window up).
  // Periodic polls never reset a state the Play flow owns, and 'idle' needs two empty polls in a row (a brief gap must not flip the button).
  P.gameState = (st, ev) => {
    st = st || { s: 'idle', misses: 0 };
    switch (ev.type) {
      case 'play-begin':
        return { s: 'preparing', misses: 0 };
      case 'play-window':
        return { s: 'running', misses: 0 };
      case 'play-end':
        return ev.ok
          ? { s: ev.windowUp ? 'running' : 'starting', misses: 0 }
          : { s: 'idle', misses: 0 };
      case 'poll': {
        if (st.s === 'preparing') return st;
        if (ev.running) return { s: 'running', misses: 0 };
        if (ev.starting) return { s: st.s === 'running' ? 'running' : 'starting', misses: 0 };
        const misses = st.misses + 1;
        return misses >= 2 ? { s: 'idle', misses } : { s: st.s, misses };
      }
    }
    return st;
  };

  // What to do about a newly published client build (a hotfix left players on the old build, their searches were refused).
  // 'auto' = download it now (idle launcher), 'quit-game' = tell the player to close the game first (never touches files under a running game), null = nothing.
  P.clientUpdateAction = (state, gs, busy, singlePlayer) => {
    const need = !!(state && state.toDownload && state.toDownload.files > 0 && !state.offline);
    if (!need || singlePlayer || busy) return null;
    return gs && (gs.s === 'running' || gs.s === 'starting' || gs.s === 'preparing')
      ? 'quit-game'
      : 'auto';
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = P;
  else root.PlayState = P;
})(typeof window !== 'undefined' ? window : globalThis);
