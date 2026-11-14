/**
 * @file Remove secrets and personal paths from report text and dumps.
 */
'use strict';

/**
 * Remove secrets and personal paths from report text.
 * @param {string} text
 * @returns {string}
 */
function scrub(text) {
  return text
    .replace(/\b[0-9a-fA-F]{64}\b/g, '<token-removed>')
    .replace(/("token"\s*:\s*")[^"]*(")/gi, '$1<removed>$2')
    .replace(/(token[=:]\s*)[0-9a-zA-Z]{20,}/gi, '$1<removed>');
}
// A dump is process memory: the player's 64-hex name token may sit in it (ASCII or UTF-16). Every 64-char hex run is overwritten with '0' IN THE COPY that
// goes into the zip (same length, the dump stays valid; the file on disk is never touched). Returns the number of runs blanked.
/**
 * Scrub a binary dump buffer in place or as a copy.
 * @param {Buffer} buf
 * @returns {Buffer}
 */
function scrubDump(buf) {
  const hex = (c) => (c >= 48 && c <= 57) || (c >= 97 && c <= 102) || (c >= 65 && c <= 70);
  let n = 0;
  for (const step of [1, 2]) {
    // 1 = ASCII, 2 = UTF-16LE (hex char followed by a zero byte)
    for (let i = 0; i < buf.length;) {
      if (!hex(buf[i]) || (step === 2 && buf[i + 1] !== 0)) {
        i++;
        continue;
      }
      let j = i;
      while (j < buf.length && hex(buf[j]) && (step === 1 || buf[j + 1] === 0)) j += step;
      const cnt = (j - i) / step;
      if (cnt === 64) {
        for (let k = i; k < j; k += step) buf[k] = 48;
        n++;
      }
      i = Math.max(j, i + 1);
    }
  }
  return n;
}

module.exports = { scrub, scrubDump };
