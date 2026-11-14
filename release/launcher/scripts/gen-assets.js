'use strict';
// Generates the app icon (assets/icon.png / icon.ico). With --sounds it also writes synthetic placeholder UI sounds over
// assets/sounds/*.wav (the shipped sounds are TLOU2's own menu waves - do not run with --sounds unless you want to replace them).
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

const A = path.join(__dirname, '..', 'assets');
fs.mkdirSync(path.join(A, 'sounds'), { recursive: true });
const SR = 44100;

function wav(name, samples) {
  const n = samples.length, buf = Buffer.alloc(44 + n * 2);
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + n * 2, 4); buf.write('WAVEfmt ', 8); buf.writeUInt32LE(16, 16);
  buf.writeUInt16LE(1, 20); buf.writeUInt16LE(1, 22); buf.writeUInt32LE(SR, 24); buf.writeUInt32LE(SR * 2, 28);
  buf.writeUInt16LE(2, 32); buf.writeUInt16LE(16, 34); buf.write('data', 36); buf.writeUInt32LE(n * 2, 40);
  let peak = 0; for (const s of samples) peak = Math.max(peak, Math.abs(s));
  const g = peak > 0 ? 0.85 / peak : 1;
  samples.forEach((s, i) => buf.writeInt16LE(Math.max(-32767, Math.min(32767, Math.round(s * g * 32767))), 44 + i * 2));
  fs.writeFileSync(path.join(A, 'sounds', name + '.wav'), buf);
}

let seed = 12345;
const rnd = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296 * 2 - 1; };
const env = (t, a, d) => (t < a ? t / a : Math.exp(-(t - a) / d));
function synth(dur, fn) { const out = new Float64Array(Math.floor(dur * SR)); for (let i = 0; i < out.length; i++) out[i] = fn(i / SR, i); return out; }
function lp(x, k) { let y = 0; return x.map((v) => (y += (v - y) * k)); }
const sine = (f, t) => Math.sin(2 * Math.PI * f * t);

if (process.argv.includes('--sounds')) {
// soft tick
wav('hover', synth(0.07, (t) => (sine(2400, t) * 0.5 + rnd() * 0.15) * env(t, 0.002, 0.012)));
// dull key click
wav('click', Float64Array.from(lp(synth(0.14, (t) => (sine(140, t) * 0.9 + sine(900, t) * 0.3 + rnd() * 0.4) * env(t, 0.001, 0.03)), 0.6)));
// tab switch: short filtered whoosh
wav('tab', Float64Array.from(lp(synth(0.22, (t) => rnd() * Math.sin(Math.PI * Math.min(1, t / 0.22)) * 0.6 + sine(320 + t * 500, t) * 0.2 * env(t, 0.01, 0.08)), 0.18)));
// confirm: two rising tones
wav('confirm', synth(0.45, (t) => (t < 0.16 ? sine(520, t) : sine(780, t)) * 0.5 * (t < 0.16 ? env(t, 0.004, 0.07) : env(t - 0.16, 0.004, 0.12)) + sine(130, t) * 0.4 * env(t, 0.003, 0.06)));
// back: falling tone
wav('back', synth(0.3, (t) => sine(520 - t * 600, t) * 0.5 * env(t, 0.004, 0.07) + rnd() * 0.05 * env(t, 0.001, 0.02)));
// error: low buzz x2
wav('error', synth(0.38, (t) => { const u = t % 0.19; return (Math.sign(sine(110, t)) * 0.4 + sine(165, t) * 0.3) * env(u, 0.005, 0.06); }));
// play / launch: deep swell + hit
wav('launch', Float64Array.from(lp(synth(1.3, (t) => {
  const sw = Math.min(1, t / 0.9) ** 2;
  const hit = t > 0.9 ? env(t - 0.9, 0.002, 0.14) : 0;
  return rnd() * 0.5 * sw + sine(70 + 60 * sw, t) * 0.7 * sw + sine(55, t) * hit * 1.2 + rnd() * hit * 0.6;
}), 0.25)));
// boot: terminal blips over a drone
wav('boot', synth(1.9, (t) => {
  const drone = sine(48, t) * 0.5 * Math.min(1, t / 0.8) * Math.exp(-Math.max(0, t - 1.3) * 3);
  let b = 0; for (const [at, f] of [[0.15, 1500], [0.45, 1900], [0.75, 1200], [1.15, 2300]]) if (t > at) b += sine(f, t) * 0.25 * env(t - at, 0.002, 0.03);
  return drone + b + rnd() * 0.03;
}));

}
// ---------------------------------------------------------------- icon: a muted "II" mark in a hex frame
function png(w, h, px) {
  const crcT = []; for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; crcT[n] = c >>> 0; }
  const crc = (b) => { let c = 0xFFFFFFFF; for (const x of b) c = crcT[(c ^ x) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
  const chunk = (t, d) => { const l = Buffer.alloc(4); l.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(t), d]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([l, td, c]); };
  const raw = Buffer.alloc((w * 4 + 1) * h);
  for (let y = 0; y < h; y++) { raw[y * (w * 4 + 1)] = 0; px.copy(raw, y * (w * 4 + 1) + 1, y * w * 4, (y + 1) * w * 4); }
  const ih = Buffer.alloc(13); ih.writeUInt32BE(w, 0); ih.writeUInt32BE(h, 4); ih[8] = 8; ih[9] = 6;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ih), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}
const S = 256, px = Buffer.alloc(S * S * 4);
const hexDist = (x, y) => { x = Math.abs(x); y = Math.abs(y); return Math.max(x * 0.866 + y * 0.5, y); };
for (let y = 0; y < S; y++) for (let x = 0; x < S; x++) {
  const cx = (x - 127.5) / 127.5, cy = (y - 127.5) / 127.5, d = hexDist(cy, cx);   // pointy-top hex
  const i = (y * S + x) * 4;
  let c = null;
  if (d < 0.97) {
    const ring = d > 0.85 && d < 0.92;
    const bar = (Math.abs(cx - (-0.2)) < 0.085 || Math.abs(cx - 0.2) < 0.085) && Math.abs(cy) < 0.5;
    if (bar) c = [196, 189, 168]; else if (ring) c = [122, 138, 150]; else c = [14, 18, 20];
  }
  if (c) { px[i] = c[0]; px[i + 1] = c[1]; px[i + 2] = c[2]; px[i + 3] = 255; }
}
const p = png(S, S, px);
fs.writeFileSync(path.join(A, 'icon.png'), p);
const ico = Buffer.alloc(22); ico.writeUInt16LE(0, 0); ico.writeUInt16LE(1, 2); ico.writeUInt16LE(1, 4);
ico[6] = 0; ico[7] = 0; ico.writeUInt16LE(1, 10); ico.writeUInt16LE(32, 12); ico.writeUInt32LE(p.length, 14); ico.writeUInt32LE(22, 18);
fs.writeFileSync(path.join(A, 'icon.ico'), Buffer.concat([ico, p]));
console.log('assets generated');
