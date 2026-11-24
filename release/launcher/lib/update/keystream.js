/**
 * @file The pack files' keystream (tools/t2r_pack.py _keystream_chunk): stream qword i is XOR'd with splitmix(i). Used by the patch apply
 * (lib/update/patch.js) to decrypt a chunk at its old stream position and encrypt it again at the new one.
 */
'use strict';

// A tiny WebAssembly module, assembled here byte by byte (no toolchain in the build): 64-bit multiplies in JS numbers or BigInt
// are far too slow for 2 GB. Exports: memory "m" (65 pages = 4 MiB + 64 KiB) and x(ptr, len, pos): XOR len bytes at ptr with the
// keystream bytes of stream positions pos, pos + 1, ... (byte b of qword q = bits 8b..8b+7 of splitmix(q)).
const C = {
  mul1: 0x9e3779b97f4a7c15n,
  add1: 0xed9ae8f47523c0fbn,
  xor1: 0xecbdd9b9c0033effn,
  mul2: 0xbf58476d1ce4e5b9n,
  mul3: 0x94d049bb133111ebn,
};
const MEM_PAGES = 65;
const CHUNK = 4 << 20;

function sleb(v) {
  // signed LEB128 of a 64-bit two's complement value
  v = BigInt.asIntN(64, v);
  const out = [];
  for (;;) {
    const b = Number(v & 0x7fn);
    v >>= 7n;
    if ((v === 0n && !(b & 0x40)) || (v === -1n && b & 0x40)) {
      out.push(b);
      return out;
    }
    out.push(b | 0x80);
  }
}
const uleb = (n) => {
  const out = [];
  do {
    let b = n & 0x7f;
    n >>>= 7;
    if (n) b |= 0x80;
    out.push(b);
  } while (n);
  return out;
};
const vec = (items) => [...uleb(items.length), ...items.flat()];
const section = (id, body) => [id, ...uleb(body.length), ...body];
const str = (s) => [...uleb(s.length), ...Buffer.from(s, 'latin1')];

// opcodes
const I64 = 0x7e,
  I32 = 0x7f;
const LGET = 0x20,
  LSET = 0x21,
  CALL = 0x10;
const K = (v) => [0x42, ...sleb(v)]; // i64.const
const I = (v) => [0x41, ...sleb(BigInt(v))]; // i32.const
const BLOCK = [0x02, 0x40],
  LOOP = [0x03, 0x40],
  END = 0x0b,
  BR = 0x0c,
  BRIF = 0x0d;
const MEM = [0, 0]; // memarg align 0, offset 0

// func 1: ks(q) -> splitmix(q)
const ksBody = [
  0, // no locals
  LGET,
  0,
  ...K(C.mul1),
  0x7e,
  ...K(C.add1),
  0x7c,
  ...K(C.xor1),
  0x85,
  LSET,
  0,
  LGET,
  0,
  LGET,
  0,
  ...K(30n),
  0x88,
  0x85,
  ...K(C.mul2),
  0x7e,
  LSET,
  0,
  LGET,
  0,
  LGET,
  0,
  ...K(27n),
  0x88,
  0x85,
  ...K(C.mul3),
  0x7e,
  LSET,
  0,
  LGET,
  0,
  LGET,
  0,
  ...K(31n),
  0x88,
  0x85,
  END,
];
// one keystream byte into mem[ptr + i]: mem ^= wrap(ks(pos >> 3) >> ((pos & 7) << 3)); then i++, pos++
const byteStep = [
  LGET,
  0,
  LGET,
  3,
  0x6a, // addr = ptr + i
  LGET,
  0,
  LGET,
  3,
  0x6a,
  0x2d,
  ...MEM, // load8_u
  LGET,
  2,
  ...K(3n),
  0x88,
  CALL,
  1, // ks(pos >> 3)
  LGET,
  2,
  ...K(7n),
  0x83,
  ...K(3n),
  0x86,
  0x88,
  0xa7, // >> ((pos & 7) << 3), wrap
  0x73,
  0x3a,
  ...MEM, // xor, store8
  LGET,
  3,
  ...I(1),
  0x6a,
  LSET,
  3,
  LGET,
  2,
  ...K(1n),
  0x7c,
  LSET,
  2,
];
// func 0: x(ptr i32, len i32, pos i64); locals: 3 = i (i32)
const xBody = [
  1,
  1,
  I32, // one local i32
  ...BLOCK,
  // 1. bytes until pos is qword aligned
  ...BLOCK,
  ...LOOP,
  LGET,
  2,
  ...K(7n),
  0x83,
  0x50,
  BRIF,
  1, // (pos & 7) == 0 -> aligned
  LGET,
  3,
  LGET,
  1,
  0x4f,
  BRIF,
  2, // i >= len -> done
  ...byteStep,
  BR,
  0,
  END,
  END,
  // 2. whole qwords
  ...BLOCK,
  ...LOOP,
  LGET,
  1,
  LGET,
  3,
  0x6b,
  ...I(8),
  0x49,
  BRIF,
  1, // len - i < 8 -> tail
  LGET,
  0,
  LGET,
  3,
  0x6a, // addr
  LGET,
  0,
  LGET,
  3,
  0x6a,
  0x29,
  ...MEM, // i64.load
  LGET,
  2,
  ...K(3n),
  0x88,
  CALL,
  1,
  0x85, // ^ ks(pos >> 3)
  0x37,
  ...MEM, // i64.store
  LGET,
  3,
  ...I(8),
  0x6a,
  LSET,
  3,
  LGET,
  2,
  ...K(8n),
  0x7c,
  LSET,
  2,
  BR,
  0,
  END,
  END,
  // 3. tail bytes
  ...BLOCK,
  ...LOOP,
  LGET,
  3,
  LGET,
  1,
  0x4f,
  BRIF,
  1,
  ...byteStep,
  BR,
  0,
  END,
  END,
  END, // outer block
  END,
];

function buildModule() {
  const types = vec([
    [0x60, ...vec([[I32], [I32], [I64]]), 0], // x
    [0x60, ...vec([[I64]]), ...vec([[I64]])], // ks
  ]);
  const bytes = [
    0x00,
    0x61,
    0x73,
    0x6d,
    0x01,
    0x00,
    0x00,
    0x00,
    ...section(1, types),
    ...section(3, vec([[0], [1]])),
    ...section(5, vec([[0x00, ...uleb(MEM_PAGES)]])),
    ...section(
      7,
      vec([
        [...str('x'), 0x00, 0],
        [...str('m'), 0x02, 0],
      ]),
    ),
    ...section(
      10,
      vec([
        [...uleb(xBody.length), ...xBody],
        [...uleb(ksBody.length), ...ksBody],
      ]),
    ),
  ];
  return new Uint8Array(bytes);
}

let inst = null;
/**
 * The keystream engine: buf = a Buffer over its own memory (CHUNK bytes), xor(len, pos) XORs buf[0, len) with the keystream at pos.
 * @returns {{buf: Buffer, chunk: number, xor: (len: number, pos: number) => void}}
 */
function engine() {
  if (!inst) {
    const m = new WebAssembly.Instance(new WebAssembly.Module(buildModule()), {});
    inst = {
      buf: Buffer.from(m.exports.m.buffer, 0, CHUNK),
      chunk: CHUNK,
      xor: (len, pos) => m.exports.x(0, len, BigInt(pos)),
    };
  }
  return inst;
}

/**
 * Reference implementation (BigInt, slow): keystream byte of stream position p. Tests only.
 * @param {number} p
 * @returns {number}
 */
function ksByteRef(p) {
  const M = (1n << 64n) - 1n;
  let x = (BigInt(Math.floor(p / 8)) * C.mul1 + C.add1) & M;
  x ^= C.xor1;
  x = ((x ^ (x >> 30n)) * C.mul2) & M;
  x = ((x ^ (x >> 27n)) * C.mul3) & M;
  x ^= x >> 31n;
  return Number((x >> BigInt((p % 8) * 8)) & 0xffn);
}

module.exports = { engine, ksByteRef, CHUNK };
