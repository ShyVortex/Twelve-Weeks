/**
 * @file System information and local WER dump discovery.
 */
'use strict';

const os = require('os');

// READ-ONLY look at whether Windows writes a WER crash dump for the game (the only dump that carries the ext's g_cdiag block). WER reads
// LocalDumps from HKLM only (admin to set; HKCU is not honoured), so the launcher never writes it - it just reports the state so a missing .dmp is explained.
// run(keyPath) -> reg.exe query output ('' if absent); injectable so tests never touch the registry.
const LD_KEY = 'HKLM\\SOFTWARE\\Microsoft\\Windows\\Windows Error Reporting\\LocalDumps';
/**
 * Discover local Windows Error Reporting dumps.
 * @param {Function} run
 * @returns {object[]}
 */
function werLocalDumps(run) {
  if (!run) {
    if (process.platform !== 'win32') return 'n/a';
    run = (k) => {
      try {
        return require('child_process').execFileSync('reg.exe', ['query', k, '/s'], {
          encoding: 'utf8',
          windowsHide: true,
          timeout: 5000,
          stdio: ['ignore', 'pipe', 'ignore'],
        });
      } catch {
        return '';
      }
    };
  }
  const txt = run(LD_KEY);
  if (!txt) return 'not configured (no WER dump is written by Windows on a crash)';
  const blocks = txt.split(/\r?\n(?=HKEY_)/i),
    sec = blocks.find((b) => /\\LocalDumps\\tlou-ii\.exe\s*(\r?\n|$)/i.test(b));
  const val = (b, n) => {
    const m = new RegExp('^\\s+' + n + '\\s+REG_\\w+\\s+(.*)$', 'im').exec(b || '');
    return m ? m[1].trim() : '';
  };
  const t = val(sec, 'DumpType') || val(blocks[0], 'DumpType') || '1 (default)',
    f = val(sec, 'DumpFolder') || val(blocks[0], 'DumpFolder') || '%LOCALAPPDATA%\\CrashDumps';
  return `configured (DumpType ${t}, folder ${f}${sec ? ', per-exe key' : ', global key'})`;
}
/**
 * Build the system.txt contents for a report.
 * @param {object} [extra]
 * @returns {string}
 */
function systemInfo(extra) {
  const c = os.cpus();
  return (
    [
      `launcher ${extra.launcherVersion}`,
      `game build ${extra.version || '?'}`,
      `player ${extra.name} (${extra.nameSource}) steam ${extra.steamId || '-'}`,
      `os ${os.type()} ${os.release()} ${os.arch()}`,
      `cpu ${c.length ? c[0].model.trim() : '?'} x${c.length}`,
      `ram ${Math.round(os.totalmem() / 2 ** 30)} GB`,
      `gpu ${extra.gpu || '?'}`,
      `wer-localdumps ${extra.wer || '?'}`,
      `time ${new Date().toISOString()}`,
    ].join('\n') + '\n'
  );
}

module.exports = { werLocalDumps, systemInfo };
