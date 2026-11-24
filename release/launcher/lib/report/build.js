/**
 * @file Assemble, scrub and ZIP a complete report.
 */
'use strict';

const fs = require('fs');
const zlib = require('zlib');
const { ZIP_CAP, TAIL, DUMP_ENTRY_MAX } = require('./constants');
const { zipBuild } = require('./zip');
const { scrub, scrubDump } = require('./scrub');
const { readTail } = require('./artifacts');

/**
 * Build the report entry model from the selected source files.
 * @param {object[]} list
 * @param {object} meta
 * @param {string} systemText
 * @param {object[]} shots
 * @returns {{entries: object[], files: object[], skipped: string[]}}
 */
function buildModel(list, meta, systemText, shots, extras) {
  // shots: optional [{name:'screenshot-1.png', data}] (lib/attach.js), stored as files/<name> and listed with their size
  const entries = [],
    sent = [],
    skipped = [];
  let budget = ZIP_CAP - 2 * 1024 * 1024;
  const push = (name, data, srcName, mtime) => {
    entries.push({ name: 'files/' + name, data, mtime });
    sent.push({ name: srcName || name, size: data.length });
  };
  push('system.txt', Buffer.from(scrub(systemText), 'utf8'));
  for (const s of shots || []) push(s.name, s.data, s.name, s.mtime);
  // extras: optional generated text files [{name:'network.txt', text}] (0.1.51 network check), scrubbed like system.txt
  for (const x of extras || []) push(x.name, Buffer.from(scrub(String(x.text || '')), 'utf8'));
  for (const f of list.filter((x) => x.kind !== 'dump' && x.kind !== 'missing')) {
    let t;
    try {
      t = readTail(f.src, TAIL);
    } catch {
      skipped.push(f.name);
      continue;
    } // a log that vanished or is locked since the list was made: the report still goes
    let text = t.buf.toString('latin1');
    if (t.cut)
      text = '[cut: the last 20 MB of ' + t.size + ' bytes]\n' + text.slice(text.indexOf('\n') + 1);
    const data = Buffer.from(scrub(text), 'latin1');
    push(f.name, data, f.name, f.mtime);
  }
  let scrubbed = 0;
  let used = entries.reduce((a, e) => a + zlib.deflateRawSync(e.data).length, 0);
  for (const f of list.filter((x) => x.kind === 'dump')) {
    let data, c;
    try {
      if (fs.statSync(f.src).size > DUMP_ENTRY_MAX) {
        skipped.push(f.name);
        continue;
      } // never read a multi-GB dump into memory (readFileSync fails above 2 GB)
      data = fs.readFileSync(f.src);
      scrubbed += scrubDump(data);
      c = zlib.deflateRawSync(data).length;
    } catch {
      skipped.push(f.name);
      continue;
    }
    if (used + c > budget) {
      skipped.push(f.name);
      continue;
    }
    used += c;
    push(f.name, data, f.name, f.mtime);
  }
  entries.unshift({
    name: 'meta.json',
    data: Buffer.from(
      JSON.stringify({
        ...meta,
        files: sent.map((x) => x.name),
        fileSizes: sent,
        screenshots: (shots || []).map((s) => ({
          name: s.name,
          size: s.data.length,
        })),
        skippedDumps: skipped,
        dumps: list.dumps || [],
        notAttachedDumps: list.skippedDumps || [],
        dumpTokensBlanked: scrubbed,
      }),
      'utf8',
    ),
  });
  return { entries, files: sent, skipped };
}

/**
 * Encode a report entry model as a ZIP archive.
 * @param {{entries: object[], files: object[], skipped: string[]}} model
 * @returns {{zip: Buffer, files: object[], skipped: string[]}}
 */
function encodeReport(model) {
  return { zip: zipBuild(model.entries), files: model.files, skipped: model.skipped };
}

// builds the zip; returns { zip: Buffer, files: [{name,size,sent}], skipped: [name] }
/**
 * Build, scrub and package a complete report archive.
 * @param {object[]} list
 * @param {object} meta
 * @param {string} systemText
 * @param {object[]} shots
 * @returns {Promise<Buffer>}
 */
function build(list, meta, systemText, shots, extras) {
  return encodeReport(buildModel(list, meta, systemText, shots, extras));
}

module.exports = { build, buildModel, encodeReport };
