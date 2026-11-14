/**
 * @file winmm DLL target selection and verification.
 */
'use strict';

const fs = require('fs');

const XOR_KEY = 0x5a3c9e17;
const IP_OFFSETS = [0x56402, 0x58725];
const PORT_OFFSETS = [0x563f1, 0x58742];

/**
 * Read the server target embedded in the mod DLL.
 * @param {Buffer} buf
 * @returns {{ip: string, port: number}|null}
 */
function getDllTarget(buf) {
  const ips = new Set(),
    ports = new Set();
  for (const o of IP_OFFSETS) {
    const v = (buf.readUInt32LE(o) ^ XOR_KEY) >>> 0;
    const b = Buffer.alloc(4);
    b.writeUInt32LE(v);
    ips.add([...b].join('.'));
  }
  for (const o of PORT_OFFSETS) ports.add(buf.readUInt16LE(o));
  if (ips.size !== 1 || ports.size !== 1) throw new Error('winmm.dll is not a T2R client build.');
  return [[...ips][0], [...ports][0]];
}

/**
 * Patch the server target embedded in the mod DLL.
 * @param {Buffer} dll
 * @param {string} ip
 * @param {number} port
 * @returns {Buffer}
 */
function setDllTarget(dll, ip, port) {
  // The DLL is ~850 MB: read and write only the four patch sites (reading it whole on every Play cost ~1 s and ~850 MB of memory, and a
  // whole-file rewrite that is cut short leaves a broken DLL in the game folder).
  const fd = fs.openSync(dll, 'r+');
  try {
    const rd = (o, len) => {
      const b = Buffer.alloc(len);
      if (fs.readSync(fd, b, 0, len, o) !== len)
        throw new Error('winmm.dll is not a T2R client build.');
      return b;
    };
    const ips = new Set(),
      ports = new Set();
    for (const o of IP_OFFSETS) {
      const b = Buffer.alloc(4);
      b.writeUInt32LE((rd(o, 4).readUInt32LE(0) ^ XOR_KEY) >>> 0);
      ips.add([...b].join('.'));
    }
    for (const o of PORT_OFFSETS) ports.add(rd(o, 2).readUInt16LE(0));
    if (ips.size !== 1 || ports.size !== 1) throw new Error('winmm.dll is not a T2R client build.');
    if ([...ips][0] === ip && [...ports][0] === port) return false;
    const v = (Buffer.from(ip.split('.').map(Number)).readUInt32LE(0) ^ XOR_KEY) >>> 0;
    const w32 = Buffer.alloc(4);
    w32.writeUInt32LE(v);
    const w16 = Buffer.alloc(2);
    w16.writeUInt16LE(port);
    for (const o of IP_OFFSETS) fs.writeSync(fd, w32, 0, 4, o);
    for (const o of PORT_OFFSETS) fs.writeSync(fd, w16, 0, 2, o);
    return true;
  } finally {
    fs.closeSync(fd);
  }
}

// A T2R winmm.dll has the server address at four known sites; a cut-off or foreign file does not. { ok, why }.
/**
 * Verify that a winmm.dll is the expected mod build.
 * @param {string} file
 * @param {number} [shippedSize]
 * @returns {{ok: boolean, reason?: string}}
 */
function verifyWinmm(file, shippedSize) {
  try {
    const st = fs.statSync(file);
    if (shippedSize && st.size !== shippedSize)
      return { ok: false, why: `size ${st.size}, expected ${shippedSize}` };
    const fd = fs.openSync(file, 'r');
    try {
      const rd = (o, len) => {
        const b = Buffer.alloc(len);
        if (fs.readSync(fd, b, 0, len, o) !== len) throw new Error('too short');
        return b;
      };
      const ips = new Set(),
        ports = new Set();
      for (const o of IP_OFFSETS) ips.add(rd(o, 4).readUInt32LE(0));
      for (const o of PORT_OFFSETS) ports.add(rd(o, 2).readUInt16LE(0));
      if (ips.size !== 1 || ports.size !== 1) return { ok: false, why: 'not a T2R client build' };
    } finally {
      fs.closeSync(fd);
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, why: String(e.message) };
  }
}

module.exports = {
  XOR_KEY,
  IP_OFFSETS,
  PORT_OFFSETS,
  getDllTarget,
  setDllTarget,
  verifyWinmm,
};
