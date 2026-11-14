/**
 * @file The same three hardware hashes the game reports to the server (tools/ext/hwid.c), so the update server can recognise a banned PC
 * from the launcher too (new Steam account or not).
 *
 * Each component hash = first 12 bytes of SHA-256("T2R-HWID1" + tag byte + data), kept as 24 hex chars:
 *   tag 1  MachineGuid (HKLM\SOFTWARE\Microsoft\Cryptography, 64-bit view) as the registry string
 *   tag 2  SMBIOS system UUID, the 16 raw bytes of the type 1 table (GetSystemFirmwareTable 'RSMB'); all-zero / all-FF are not a UUID
 *   tag 3  smallest-sorting serial of the fixed physical drives (IOCTL_STORAGE_QUERY_PROPERTY; USB / virtual buses skipped), trimmed
 * The raw data is read by one PowerShell script that calls the same Windows APIs as the game; node does the hashing. Windows only;
 * on other systems (or when nothing is readable) the result is empty and the ban check falls back to the Steam id.
 */
'use strict';

const crypto = require('crypto');
const { execFile } = require('child_process');

const TAG = Buffer.from('T2R-HWID1', 'latin1');

/**
 * Hash one component the way hwid.c's hw_comp does.
 * @param {number} tag
 * @param {Buffer} data
 * @returns {string} 24 hex chars
 */
function componentHash(tag, data) {
  return crypto
    .createHash('sha256')
    .update(TAG)
    .update(Buffer.from([tag]))
    .update(data)
    .digest()
    .subarray(0, 12)
    .toString('hex');
}

/**
 * Turn the raw component dump ("<tag>:<hex data>" per line) into hashes, in the game's order (tag 1, 2, 3).
 * @param {string} text
 * @returns {string[]}
 */
function hashesFromDump(text) {
  const byTag = new Map();
  for (const line of String(text || '').split(/\r?\n/)) {
    const m = /^([123]):([0-9a-fA-F]+)\s*$/.exec(line.trim());
    if (m && m[2].length % 2 === 0 && m[2].length > 0) byTag.set(+m[1], Buffer.from(m[2], 'hex'));
  }
  return [1, 2, 3].filter((t) => byTag.has(t)).map((t) => componentHash(t, byTag.get(t)));
}

const PS = String.raw`
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices; using System.Text; using System.IO;
public static class T2rHw {
  [DllImport("kernel32.dll")] static extern uint GetSystemFirmwareTable(uint sig, uint id, byte[] buf, uint size);
  [DllImport("kernel32.dll", CharSet=CharSet.Ansi, SetLastError=true)] static extern IntPtr CreateFileA(string n, uint acc, uint share, IntPtr sa, uint disp, uint fl, IntPtr t);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool DeviceIoControl(IntPtr h, uint code, byte[] inb, uint inSz, byte[] outb, uint outSz, out uint ret, IntPtr ov);
  public static string Smbios() {
    uint sz = GetSystemFirmwareTable(0x52534D42, 0, null, 0);
    if (sz < 8 || sz > (1u << 20)) return "";
    byte[] b = new byte[sz];
    if (GetSystemFirmwareTable(0x52534D42, 0, b, sz) != sz) return "";
    uint tl = BitConverter.ToUInt32(b, 4);
    long end = Math.Min(8L + tl, (long)sz), off = 8;
    while (off + 4 <= end) {
      int type = b[off], len = b[off + 1];
      if (len < 4) break;
      if (type == 1 && len >= 0x19 && off + 8 + 16 <= end) {
        bool z = true, f = true; var sb = new StringBuilder();
        for (int i = 0; i < 16; i++) { byte v = b[off + 8 + i]; z &= v == 0; f &= v == 0xFF; sb.Append(v.ToString("x2")); }
        return (!z && !f) ? sb.ToString() : "";
      }
      long nx = off + len;
      while (nx + 1 < end && (b[nx] != 0 || b[nx + 1] != 0)) nx++;
      off = nx + 2;
    }
    return "";
  }
  public static string Disk() {
    string best = "";
    for (int i = 0; i < 16; i++) {
      IntPtr h = CreateFileA(new string((char)92, 2) + "." + (char)92 + "PhysicalDrive" + i, 0, 3, IntPtr.Zero, 3, 0, IntPtr.Zero);
      if (h == (IntPtr)(-1)) continue;
      byte[] q = new byte[12]; byte[] buf = new byte[1024]; uint ret;
      bool ok = DeviceIoControl(h, 0x2D1400, q, (uint)q.Length, buf, (uint)buf.Length, out ret, IntPtr.Zero);
      CloseHandle(h);
      if (!ok || ret < 36) continue;
      uint so = BitConverter.ToUInt32(buf, 24), bus = BitConverter.ToUInt32(buf, 28);
      if (bus == 7 || bus == 14 || bus == 15 || so == 0 || so >= buf.Length - 1) continue;
      int e = (int)so; while (e < buf.Length && e < (int)so + 100 && buf[e] != 0) e++;
      string s = Encoding.GetEncoding(28591).GetString(buf, (int)so, e - (int)so).Trim(' ', '\t', '\r', '\n');
      if (s.Length > 0 && (best == "" || string.CompareOrdinal(s, best) < 0)) best = s;
    }
    return best;
  }
}
'@
function Hex([byte[]]$b) { ($b | ForEach-Object { $_.ToString('x2') }) -join '' }
$g = [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine', 'Registry64').OpenSubKey('SOFTWARE\Microsoft\Cryptography').GetValue('MachineGuid')
if ($g) { '1:' + (Hex ([Text.Encoding]::ASCII.GetBytes([string]$g))) }
$u = [T2rHw]::Smbios(); if ($u) { '2:' + $u }
$d = [T2rHw]::Disk(); if ($d) { '3:' + (Hex ([Text.Encoding]::GetEncoding(28591).GetBytes($d))) }
`;

/**
 * Read this PC's hardware hashes. Never throws; resolves to [] when unsupported or unreadable.
 * @param {{ timeoutMs?: number, platform?: string, exec?: Function }} [opts]
 * @returns {Promise<string[]>}
 */
function hardwareHashes(opts = {}) {
  const platform = opts.platform || process.platform;
  if (platform !== 'win32') return Promise.resolve([]);
  const run = opts.exec || execFile;
  return new Promise((resolve) => {
    try {
      const enc = Buffer.from(PS, 'utf16le').toString('base64');
      run(
        'powershell.exe',
        ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', enc],
        { timeout: opts.timeoutMs || 20000, windowsHide: true, maxBuffer: 1 << 20 },
        (err, stdout) => resolve(err && !stdout ? [] : hashesFromDump(stdout)),
      );
    } catch {
      resolve([]);
    }
  });
}

module.exports = { componentHash, hashesFromDump, hardwareHashes };
