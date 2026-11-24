/**
 * @file Main-process report orchestration: collection, upload and progress events.
 *
 * `buildBundle` collects files and metadata, `transmitBundle` handles delivery plus queueing on
 * retryable failures, `uploadClips` handles the optional clip follow-up, and `sendReport`
 * orchestrates them. Progress events are emitted by the transport helpers as they run.
 */
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { nativeImage, dialog } = require('electron');
const game = require('../lib/game');
const rpt = require('../lib/report');
const att = require('../lib/attach');
const sysinfo = require('../lib/sysinfo');
const dmn = require('../lib/daemon');
const { netProbe } = require('../lib/report/netprobe');

// PLAYER REPORT: the players of the last 3 matches come from the game server (op 0xD6), the report goes back to it (op 0xD4).
// Nothing but the picked match / slot, the reasons and the typed text is sent; the server checks that the player really was in one of the player's last matches.
const PLAYER_REPORT_ERRORS = {
  'too many reports today':
    'You already sent the most player reports allowed for today. Try again tomorrow.',
  'already reported': 'You already reported this player.',
  'not in that match': 'That player is no longer in your recent matches.',
  'match too old': 'That player is no longer in your recent matches.',
  'no such player': 'That player is no longer in your recent matches.',
};

/**
 * Create the main-process report service.
 * @param {{ app: object, runtime: object, config: object, paths: object, log: Function, send: Function, getWindow: Function, player: object, locale: object }} options
 * @returns {object} Report service for files, attachments, send and progress.
 */
function createReport({ app, runtime, config, paths, log, send, getWindow, player, locale }) {
  const I18N = locale.I18N;
  const attachments = [];
  let lastFlush = 0;

  const queueDir = () => path.join(runtime.userData, 'report-queue');

  function options(older, when) {
    return {
      gameDir: config.values.game_dir,
      clientDir: paths.clientDir(),
      launcherLog: path.join(runtime.logDir, 'launcher.log'),
      docsDir: app.getPath('documents'),
      olderDumps: !!older,
      matchLogs: /earlier|another/i.test(String(when || '')) ? 8 : 3,
    };
  }

  function view() {
    return attachments.map((item) => {
      let thumb = '';
      if (item.kind === 'image') {
        try {
          const image = nativeImage.createFromPath(item.path);
          if (!image.isEmpty()) thumb = image.resize({ height: 120 }).toDataURL();
          else if (item.size <= 2 * 1024 * 1024)
            thumb = `data:${att.MIME[item.ext]};base64,${fs
              .readFileSync(item.path)
              .toString('base64')}`;
        } catch {
          /* no thumbnail */
        }
      }
      return {
        id: item.id,
        name: item.name,
        size: item.size,
        kind: item.kind,
        ext: item.ext,
        thumb,
      };
    });
  }

  function result(rejected) {
    return {
      items: view(),
      rejected: rejected.map((item) => ({
        name: item.name,
        reason: I18N.T(item.reason),
      })),
    };
  }

  async function flushQueue(host) {
    if (!host || Date.now() - lastFlush < 300000 || !rpt.queueList(queueDir()).length) return;
    lastFlush = Date.now();
    try {
      const flushed = await rpt.flushQueue(queueDir(), host);
      if (flushed.sent.length || flushed.dropped)
        log(
          `Saved bug reports: sent ${flushed.sent.join(', ') || 'none'}, dropped ${
            flushed.dropped
          }, kept ${flushed.kept}.`,
        );
    } catch (e) {
      log(`Saved bug reports: ${e.message}`);
    }
  }

  async function files(older) {
    const list = rpt.collect(options(older));
    return {
      files: list.map((file) => ({
        name: file.name,
        size: file.size,
        mtime: file.mtime || 0,
        kind: file.kind,
        note: file.note,
      })),
      skippedDumps: (list.skippedDumps || []).map((dump) => ({
        name: dump.name,
        reason: dump.reason,
      })),
    };
  }

  async function add(pathsToAdd) {
    return result(
      att.addAll(
        attachments,
        (Array.isArray(pathsToAdd) ? pathsToAdd : [])
          .filter((p) => typeof p === 'string')
          .slice(0, 20),
      ),
    );
  }

  async function pick() {
    const picked = await dialog.showOpenDialog(getWindow(), {
      title: I18N.T('Attach screenshots or clips'),
      properties: ['openFile', 'multiSelections'],
      filters: [
        {
          name: I18N.T('Screenshots and clips'),
          extensions: ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'mp4', 'mov', 'webm', 'mkv'],
        },
      ],
    });
    return result(picked.canceled ? [] : att.addAll(attachments, picked.filePaths));
  }

  async function paste(bytes) {
    const buffer = Buffer.from(bytes || []);
    if (!buffer.length || buffer.length > att.IMG_MAX_EACH)
      return result([
        {
          name: 'pasted image',
          reason: 'Screenshot too big - it must be under 8 MB.',
        },
      ]);
    const dir = path.join(runtime.userData, 'report-stage');
    fs.mkdirSync(dir, { recursive: true });
    const ext = att.sniff(buffer.subarray(0, 64)) || 'png';
    const file = path.join(dir, `pasted-${Date.now()}.${ext}`);
    fs.writeFileSync(file, buffer);
    const rejected = att.addAll(attachments, [file]);
    if (rejected.length) {
      try {
        fs.unlinkSync(file);
      } catch {
        /* ignore */
      }
    }
    return result(rejected);
  }

  async function remove(id) {
    const index = attachments.findIndex((item) => item.id === id);
    if (index >= 0) {
      const [item] = attachments.splice(index, 1);
      if (item.path.startsWith(path.join(runtime.userData, 'report-stage')))
        try {
          fs.unlinkSync(item.path);
        } catch {
          /* ignore */
        }
    }
    return result([]);
  }

  async function buildBundle(form, text) {
    send('report-progress', { phase: 'collect', pct: 0 });
    const name = await player.resolveName();
    const steam = await player.readSteamUser();
    const gpu = await sysinfo.gpuName({ isLinux: runtime.isLinux, run: game.run });
    const version = game.readTrim(
      path.join(
        game.isGameDir(config.values.game_dir) ? config.values.game_dir : paths.clientDir(),
        game.isGameDir(config.values.game_dir) ? 't2r-version.txt' : 'version.txt',
      ),
    );
    const list = rpt.collect(options(form.includeDumps, form.when));
    const meta = {
      text: text.slice(0, 4000),
      when: String(form.when || '').slice(0, 200),
      whenText: String(form.whenText || '').slice(0, 400),
      mapMode: String(form.mapMode || '').slice(0, 100),
      version,
      name: name.name,
      nameSource: name.source,
      steamId: steam ? steam.id : '',
      launcherVersion: runtime.launcherVersion,
      os: `${os.type()} ${os.release()}`,
      gpu,
      includeDumps: !!form.includeDumps,
      clips: attachments.filter((item) => item.kind === 'video').length,
    };
    // 0.1.51: what each update address and the game server answer from this PC (files/network.txt), at most ~10 s
    send('report-progress', { phase: 'collect', pct: 50 });
    const network = await netProbe({
      gameServer: paths.serverAddress(),
      fileHost: paths.fileHost(),
    }).catch((e) => `network check failed: ${e.message}\n`);
    return rpt.build(
      list,
      meta,
      rpt.systemInfo({ ...meta, wer: rpt.werLocalDumps() }),
      att.screenshotEntries(attachments),
      [{ name: 'network.txt', text: network }],
    );
  }

  async function transmitBundle(host, bundle) {
    let response;
    try {
      response = await rpt.post(`${host}/report`, bundle.zip, (sent, total) =>
        send('report-progress', {
          phase: 'send',
          pct: Math.round((sent / total) * 100),
          size: total,
        }),
      );
    } catch (e) {
      if (!rpt.retryable(e)) throw e;
      try {
        rpt.enqueue(queueDir(), bundle.zip);
        log(`Bug report could not be sent (${e.message}); saved for later.`);
      } catch (saveError) {
        throw new Error(
          `The update server cannot be reached and the report could not be saved either (${saveError.message}). Try again later.`,
          { cause: saveError },
        );
      }
      throw new Error(
        'The update server cannot be reached right now, so the report was saved on this PC. It is sent automatically the next time the launcher can reach the server (you do not need to do anything).',
        { cause: e },
      );
    }
    if (rpt.retryableStatus(response.status)) {
      try {
        rpt.enqueue(queueDir(), bundle.zip);
        log(`Bug report not accepted (HTTP ${response.status}); saved for later.`);
      } catch {
        /* the error below still says so */
      }
      throw new Error(
        `The server is busy or restarting (HTTP ${response.status}), so the report was saved on this PC and is sent automatically later.`,
      );
    }
    if (response.status !== 200 || !response.json || !response.json.ok)
      throw new Error(
        response.json && response.json.error
          ? `The server refused the report: ${response.json.error}`
          : `The server answered HTTP ${response.status}.`,
      );
    return response;
  }

  async function uploadClips(host, response, clips) {
    const clipNotes = [];
    if (clips.length && response.json.clipRefused)
      clipNotes.push(`Clips were not attached: ${response.json.clipRefused}.`);
    else if (clips.length && response.json.clipKey) {
      for (let i = 0; i < clips.length; i++) {
        const clip = clips[i];
        let done = false;
        let lastError = '';
        for (let attempt = 0; attempt < 2 && !done; attempt++) {
          send('report-progress', {
            phase: 'clip',
            pct: 0,
            size: clip.size,
            n: i + 1,
            of: clips.length,
          });
          try {
            const upload = await att.uploadClip(
              host,
              response.json.code,
              response.json.clipKey,
              clip.path,
              (sent, total) =>
                send('report-progress', {
                  phase: 'clip',
                  pct: Math.round((sent / total) * 100),
                  size: total,
                  n: i + 1,
                  of: clips.length,
                }),
            );
            if (upload.status === 200 && upload.json && upload.json.ok) {
              done = true;
              log(`Bug report ${response.json.code}: clip ${i + 1} sent (${clip.size} bytes)`);
            } else {
              lastError =
                upload.json && upload.json.error ? upload.json.error : `HTTP ${upload.status}`;
              if (upload.status >= 400 && upload.status < 500) break;
            }
          } catch (e) {
            lastError = e.message;
          }
        }
        if (!done) {
          clipNotes.push(`Clip ${i + 1} (${clip.name}) could not be sent: ${lastError}`);
          log(`Bug report ${response.json.code}: clip ${i + 1} failed: ${lastError}`);
        }
      }
    } else if (clips.length)
      clipNotes.push('Clips were not attached (this update server is too old for video clips).');
    return clipNotes;
  }

  async function sendReport(form) {
    const text = String(form.text || '').trim();
    if (text.length < 10) throw new Error('Please describe what happened (at least a sentence).');
    const host = paths.fileHost();
    if (!host)
      throw new Error('No file host set (Settings > Files): reports go to the update server.');
    const bundle = await buildBundle(form, text);
    send('report-progress', { phase: 'send', pct: 0, size: bundle.zip.length });
    const response = await transmitBundle(host, bundle);
    log(
      `Bug report sent: ${response.json.code} (${bundle.zip.length} bytes, ${bundle.files.length} files)`,
    );
    const clipNotes = await uploadClips(
      host,
      response,
      attachments.filter((item) => item.kind === 'video'),
    );
    attachments.length = 0;
    return {
      code: response.json.code,
      size: bundle.zip.length,
      files: bundle.files,
      skipped: bundle.skipped,
      uniqueCode: bundle.uniqueCode,
      clipNotes,
    };
  }

  async function players() {
    const name = await player.resolveName();
    const token = game.nameToken(name.name, config.values.token_id);
    const { host, port } = game.parseServer(paths.serverAddress());
    const matches = await dmn.recentPlayers(host, port, token);
    if (!matches) throw new Error('The game server did not answer. Try again in a moment.');
    return { matches };
  }

  async function reportPlayer(form) {
    const f = form || {};
    const name = await player.resolveName();
    const token = game.nameToken(name.name, config.values.token_id);
    const { host, port } = game.parseServer(paths.serverAddress());
    const r = await dmn.reportPlayer(host, port, token, {
      mid: String(f.mid || ''),
      slot: f.slot | 0,
      reasons: f.reasons | 0,
      text: String(f.text || ''),
    });
    if (!r) throw new Error('The game server did not answer. Try again in a moment.');
    if (!r.ok) throw new Error(PLAYER_REPORT_ERRORS[r.err] || 'The server refused the report.');
    log(`Player report sent: ${r.code}`);
    return { code: r.code };
  }

  return {
    files,
    players,
    reportPlayer,
    add,
    pick,
    paste,
    remove,
    list: () => result([]),
    sendReport,
    flushQueue,
  };
}

module.exports = { createReport };
