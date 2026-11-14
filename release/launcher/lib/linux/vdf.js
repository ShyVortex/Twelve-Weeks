'use strict';

/**
 * Parse Steam VDF text into a nested object.
 * @param {string} text
 * @returns {object}
 */
function parseVdf(text) {
  let i = 0;
  const n = text.length;
  const ws = () => {
    while (i < n) {
      const c = text[i];
      if (c === ' ' || c === '\t' || c === '\r' || c === '\n') i++;
      else if (c === '/' && text[i + 1] === '/') {
        while (i < n && text[i] !== '\n') i++;
      } else break;
    }
  };
  const str = () => {
    i++;
    let s = '';
    while (i < n && text[i] !== '"') {
      if (text[i] === '\\' && i + 1 < n) {
        const d = text[i + 1];
        s += d === 'n' ? '\n' : d === 't' ? '\t' : d;
        i += 2;
      } else s += text[i++];
    }
    i++;
    return s;
  };
  const obj = () => {
    const o = {};
    for (;;) {
      ws();
      if (i >= n) return o;
      if (text[i] === '}') {
        i++;
        return o;
      }
      if (text[i] !== '"') {
        i++;
        continue;
      }
      const k = str();
      ws();
      if (text[i] === '{') {
        i++;
        o[k] = obj();
      } else if (text[i] === '"') o[k] = str();
    }
  };
  return obj();
}

/**
 * Safely read a nested VDF value, matching keys case-insensitively.
 * @param {object} o
 * @param {...string} keys
 * @returns {unknown}
 */
function vget(o, ...keys) {
  let cur = o;
  for (const k of keys) {
    if (!cur || typeof cur !== 'object') return undefined;
    const hit = Object.keys(cur).find((x) => x.toLowerCase() === String(k).toLowerCase());
    if (hit === undefined) return undefined;
    cur = cur[hit];
  }
  return cur;
}

module.exports = { parseVdf, vget };
