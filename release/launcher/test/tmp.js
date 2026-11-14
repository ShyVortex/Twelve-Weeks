'use strict';
// Temp dirs of the launcher tests: named 't2r-tmp-<prefix>*' (identifiable), removed when the process ends (also after a failure or
// process.exit()), stale ones of a killed run (older than T2R_TMP_SWEEP_HOURS, default 6) swept at start.
// T2R_TMP=<dir> puts them elsewhere than the system temp dir (e.g. when C: is short on space).
const fs = require('fs'), os = require('os'), path = require('path');
const PREFIX = 't2r-tmp-';
const base = process.env.T2R_TMP || os.tmpdir();
const owned = [];
try { fs.mkdirSync(base, { recursive: true }); } catch {}
try {
  const cut = Date.now() - (parseFloat(process.env.T2R_TMP_SWEEP_HOURS) || 6) * 3600e3;
  for (const n of fs.readdirSync(base)) {
    if (!n.startsWith(PREFIX)) continue;
    const p = path.join(base, n);
    try { if (fs.statSync(p).mtimeMs < cut) fs.rmSync(p, { recursive: true, force: true }); } catch {}
  }
} catch {}
process.on('exit', () => {
  if (process.env.T2R_KEEP_TMP === '1') return;
  for (const d of owned) { try { fs.rmSync(d, { recursive: true, force: true }); } catch {} }
});
module.exports = function mkTmp(prefix) {
  const d = fs.mkdtempSync(path.join(base, PREFIX + (prefix || '')));
  owned.push(d);
  return d;
};
