/**
 * @file ZIP writer for report archives (adm-zip; OmegaMan's "more robust ZIP handling").
 */
'use strict';

const AdmZip = require('adm-zip');

/**
 * Convert a timestamp to the DOS date/time fields used by ZIP headers.
 * @param {number|Date} [value]
 * @returns {{time: number, date: number}}
 */
function dosDateTime(value) {
  const d = value instanceof Date ? value : new Date(Number.isFinite(value) ? value : Date.now());
  const year = Math.min(2107, Math.max(1980, d.getFullYear()));
  return {
    time: (d.getHours() << 11) | (d.getMinutes() << 5) | Math.floor(d.getSeconds() / 2),
    date: ((year - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate(),
  };
}

/**
 * Build a ZIP archive from named buffers (deflated, UTF-8 names, each entry keeps its file time).
 * @param {{name: string, data: Buffer, mtime?: number|Date}[]} entries
 * @returns {Buffer}
 */
function zipBuild(entries) {
  const zip = new AdmZip();
  for (const e of entries) {
    zip.addFile(e.name, e.data);
    const entry = zip.getEntry(e.name);
    if (entry) {
      const t =
        e.mtime instanceof Date
          ? e.mtime
          : new Date(Number.isFinite(e.mtime) ? e.mtime : Date.now());
      entry.header.time = t;
    }
  }
  return zip.toBuffer();
}

module.exports = { zipBuild, dosDateTime };
