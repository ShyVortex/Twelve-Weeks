'use strict';

const fs = require('fs');
const path = require('path');

const MAGIC = 'T2SLIM03';
const HEAD_SIZE = 128;
const BUILD_ID_AT = 0x18;

function readSlimHead(file) {
  let fd;
  try {
    fd = fs.openSync(file, 'r');
    const b = Buffer.alloc(HEAD_SIZE);
    if (fs.readSync(fd, b, 0, HEAD_SIZE, 0) !== HEAD_SIZE) return null;
    if (b.toString('latin1', 0, 8) !== MAGIC) return null;
    const outSize = b.readBigUInt64LE(32);
    if (outSize > BigInt(Number.MAX_SAFE_INTEGER) || outSize < 32n) return null;
    return { outSize: Number(outSize), buildId: Buffer.from(b.subarray(88, 104)) };
  } catch {
    return null;
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
  }
}

function slimTargets(clientDir, game) {
  const root = path.join(clientDir, 't2r-maps');
  const out = [];
  const walk = (d) => {
    let ents;
    try {
      ents = fs.readdirSync(d, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of ents) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.isFile() && e.name.endsWith('.slim')) {
        const rel = path.relative(root, p);
        const targetRel = rel.slice(0, -'.slim'.length) + '.bin';
        const shown = 't2r-maps/' + targetRel.split(path.sep).join('/');
        out.push({ slim: p, rel, target: path.join(game, 't2r-maps', targetRel), targetRel, shown });
      }
    }
  };
  walk(root);
  return out;
}

function isSlimManaged(file) {
  if (file.endsWith('.slim')) return true;
  return file.endsWith('.bin') && fs.existsSync(file.slice(0, -'.bin'.length) + '.slim');
}

function dataCurrent(slim, target) {
  const h = readSlimHead(slim);
  if (!h) return false;
  let fd;
  try {
    if (fs.statSync(target).size !== h.outSize) return false;
    fd = fs.openSync(target, 'r');
    const a = Buffer.alloc(16);
    const z = Buffer.alloc(16);
    fs.readSync(fd, a, 0, 16, BUILD_ID_AT);
    fs.readSync(fd, z, 0, 16, h.outSize - 16);
    return a.equals(h.buildId) && z.equals(h.buildId);
  } catch {
    return false;
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
  }
}

module.exports = { MAGIC, readSlimHead, slimTargets, isSlimManaged, dataCurrent };
