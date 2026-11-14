/**
 * @file Language registry - single source of truth for supported languages.
 */
'use strict';

const LANGUAGES = [
  {
    code: 'en',
    name: 'English',
    flag: 'gb',
    pluralRule: 'en',
    daemonByte: 0,
    hasTickerPool: true,
    rtl: false,
  },
  {
    code: 'pl',
    name: 'Polski',
    flag: 'pl',
    pluralRule: 'pl',
    daemonByte: 1,
    hasTickerPool: true,
    rtl: false,
  },
  {
    code: 'es',
    name: 'Español',
    flag: 'es',
    pluralRule: 'es',
    daemonByte: 2,
    hasTickerPool: false,
    rtl: false,
  },
];

const LANG_MAP = Object.fromEntries(LANGUAGES.map((l) => [l.code, l]));
const SUPPORTED_LANGS = LANGUAGES.map((l) => l.code);
const DAEMON_LANG_BYTES = Object.fromEntries(LANGUAGES.filter((l) => l.daemonByte != null).map((l) => [l.code, l.daemonByte]));

function getLanguage(code) {
  return LANG_MAP[code] || LANG_MAP.en;
}

function isSupported(code) {
  return !!LANG_MAP[code];
}

function normalizeLanguage(code) {
  const base = String(code || '')
    .toLowerCase()
    .split(/[-_]/)[0];
  return isSupported(base) ? base : 'en';
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    LANGUAGES,
    LANG_MAP,
    SUPPORTED_LANGS,
    DAEMON_LANG_BYTES,
    getLanguage,
    isSupported,
    normalizeLanguage,
  };
} else if (typeof window !== 'undefined') {
  window.I18N_LANGS = {
    LANGUAGES,
    LANG_MAP,
    SUPPORTED_LANGS,
    DAEMON_LANG_BYTES,
    getLanguage,
    isSupported,
    normalizeLanguage,
  };
}
