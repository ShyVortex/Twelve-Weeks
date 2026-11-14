/**
 * @file Server status polling and the state snapshot consumed by the renderer.
 */
'use strict';

const path = require('path');
const game = require('../lib/game');
const upd = require('../lib/update');
const dmn = require('../lib/daemon');
const { makeSticky } = require('../lib/sticky');

/**
 * Create the server-status polling service.
 * @param {{ runtime: object, config: object, paths: object, player: object, report: object, jobs: object, mode: object, locale: object, log: Function }} options
 * @returns {object} Status API consumed by IPC and the renderer.
 */
function createStatus({ runtime, config, paths, player, report, jobs, mode, locale, log }) {
  // the last good update check (a single timed-out check flipped the launcher to OFFLINE for 10 s)
  const stateSticky = makeSticky();
  async function checkState() {
    const state = await checkStateRaw();
    if (!state.offline) {
      stateSticky.ok(state);
      return state;
    }
    // a real answer (HTTP error, bad manifest, no server set) is shown as it is
    if (
      !state.error ||
      !/timeout|ECONN|ENOTFOUND|EHOSTUNREACH|ENETUNREACH|EAI_AGAIN|unreachable/i.test(state.error)
    )
      return state;
    const keep = stateSticky.fail();
    if (!keep) return state;
    return {
      ...keep,
      gameDir: state.gameDir,
      gameOk: state.gameOk,
      clientDir: state.clientDir,
      localVersion: state.localVersion,
      installed: state.installed,
      server: state.server,
    };
  }

  async function checkStateRaw() {
    const dir = paths.clientDir();
    const host = paths.fileHost();
    if (!jobs.isBusy) {
      try {
        await upd.recoverStaged(dir);
      } catch {
        /* the file check below shows what is missing */
      }
    }
    const local = game.readTrim(path.join(dir, 'version.txt'));
    const state = {
      gameDir: config.values.game_dir,
      gameOk: game.isGameDir(config.values.game_dir),
      clientDir: dir,
      localVersion: local,
      fileHost: host,
      server: paths.serverAddress(),
      manifest: null,
      toDownload: { files: 0, bytes: 0 },
      launcherUpdate: null,
      offline: false,
      error: null,
      installed: game.exists(path.join(dir, 'winmm.dll')),
    };
    if (!host) {
      state.offline = true;
      state.error = 'No update server configured';
      return state;
    }
    try {
      const manifest = await paths.getManifest(host);
      state.manifest = {
        version: manifest.version,
        channel: manifest.channel || paths.channel(),
        files: manifest.files.length,
        bytes: manifest.files.reduce((a, file) => a + file.size, 0),
        notes: manifest.notes || '',
      };
      const bad = await upd.diffFiles(manifest, dir, path.join(runtime.userData, 'hashcache.json'));
      state.toDownload = {
        files: bad.length,
        bytes: bad.reduce((a, file) => a + (file.zurl ? file.zsize : file.size), 0),
      };
      report.flushQueue(host);
      const launcherVersion = runtime.isLinux ? manifest.launcher_linux : manifest.launcher;
      if (
        launcherVersion &&
        launcherVersion.version &&
        upd.cmpVersion(runtime.launcherVersion, launcherVersion.version) < 0
      )
        state.launcherUpdate = launcherVersion;
    } catch (e) {
      state.offline = true;
      state.error = e.message;
      log(`Update check failed: ${e.message}`);
    }
    return state;
  }

  // the last good server status: the online count flipped between '-' and a number
  let playersAt = 0;
  const statusSticky = makeSticky({ maxFails: 3, maxAgeMs: 120000 });
  async function serverStatus() {
    const out = await serverStatusRaw();
    if (out.sp) return out;
    if (out.online) {
      if (out.players !== null) playersAt = Date.now();
      else {
        // reachable, only the count query was lost (kept for 2 minutes at most)
        const good = statusSticky.last();
        if (good && good.players != null && Date.now() - playersAt < 120000)
          out.players = good.players;
      }
      statusSticky.ok(out);
      return out;
    }
    const keep = statusSticky.fail();
    return keep || out;
  }

  async function serverStatusRaw() {
    const out = {
      players: null,
      serverVersion: null,
      reachable: null,
      online: false,
      source: null,
      notices: null,
      targetVersion: null,
    };
    if (mode.current()) return { ...out, sp: true };
    let daemonOnline = null;
    const server = paths.serverAddress();
    if (server) {
      try {
        const { host, port } = game.parseServer(server);
        const { ip } = await game.resolveServer(server);
        const [probe, online] = await Promise.all([
          game.probeServer(
            ip,
            port,
            null,
            game.readTrim(path.join(paths.clientDir(), 'version.txt')) || null,
            2500,
          ),
          dmn.onlineCount(host, port),
        ]);
        out.reachable = probe.reachable;
        out.online = probe.reachable;
        out.serverVersion = probe.serverVersion;
        out.versionOk = probe.versionOk;
        out.source = 'daemon';
        // The daemon's 0x16 count is max(1, n) (the in-game MP menu counts you); the launcher shows only players in the
        // game, so the count comes from /status.json players_online below (same source as the PLAYERS ONLINE panel); 0x16 is the fallback
        if (online !== null) daemonOnline = online;
        try {
          const name = await player.resolveName();
          const notices = await dmn.notices(
            host,
            port,
            game.nameToken(name.name, config.values.token_id),
            locale.langNow(),
          );
          const now = Date.now() / 1000;
          if (notices)
            out.notices = notices.map((notice) => ({
              ...notice,
              endsAt: notice.kind === 'r' ? now + notice.param : null,
            }));
        } catch {
          /* none */
        }
      } catch {
        out.reachable = false;
      }
    }
    if (paths.fileHost()) {
      try {
        const json = await upd.getJson(`${paths.fileHost()}/status.json`, 3000);
        if (out.players === null) out.players = json.players_online ?? json.players ?? null;
        if (json.online) {
          out.online = true;
          out.reachable = true;
        }
        if (!out.serverVersion) out.serverVersion = json.server_version ?? null;
        if (out.notices === null && Array.isArray(json.notices)) out.notices = json.notices;
        out.targetVersion = json.target_version || null;
      } catch {
        /* unreachable */
      }
    }
    if (out.players === null && daemonOnline !== null) out.players = daemonOnline;
    return out;
  }

  // Players panel (test feature, src/players.js): names + states from the update server's /status.json "roster". Never throws.
  const ROSTER_STATES = new Set(['menu', 'searching', 'match', 'party']);
  async function roster() {
    if (mode.current() || !paths.fileHost()) return { ok: false, players: [] };
    try {
      const json = await upd.getJson(`${paths.fileHost()}/status.json`, 3000);
      const list = Array.isArray(json.roster) ? json.roster : [];
      return {
        ok: true,
        players: list.slice(0, 200).map((p) => ({
          name: String((p && p.name) || 'PLAYER').slice(0, 24),
          state: ROSTER_STATES.has(p && p.state) ? p.state : 'menu',
          map: p && typeof p.map === 'string' ? p.map.slice(0, 40) : null,
          party: !!(p && p.party),
        })),
      };
    } catch {
      return { ok: false, players: [] };
    }
  }

  return { checkState, serverStatus, roster };
}

module.exports = { createStatus };
