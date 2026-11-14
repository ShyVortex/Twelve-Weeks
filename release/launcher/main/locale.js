/**
 * @file Load translations and expose the main-process i18n helpers.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const I18N = require('../src/i18n-core');
const { SUPPORTED_LANGS, isSupported, normalizeLanguage } = require('../src/i18n/languages');

/**
 * Language codes whose tables are loaded: the registry (src/i18n/languages.js) plus every <code>.json / game-<code>.json found in src/i18n.
 * @param {string} rootDir
 * @returns {string[]}
 */
function discoverLanguages(rootDir) {
  const langs = new Set(SUPPORTED_LANGS);
  try {
    for (const f of fs.readdirSync(path.join(rootDir, 'src', 'i18n'))) {
      const m = /^(?:game-)?([a-z]{2,3})\.json$/.exec(f);
      if (m) langs.add(m[1]);
    }
  } catch {
    /* the registry alone */
  }
  return Array.from(langs);
}

/**
 * Load translations and expose main-process i18n helpers.
 * @param {{ app: object, config: object, rootDir: string }} options
 * @returns {object} Locale API used by IPC and window code.
 */
function createLocale({ app, config, rootDir }) {
  // the saved choice when it is a registered language, else the system language, else English
  function langNow() {
    const lang = config.values.lang;
    if (lang && isSupported(lang)) return lang;
    return normalizeLanguage(app.getLocale());
  }

  function load() {
    const read = (file) => {
      try {
        return JSON.parse(fs.readFileSync(path.join(rootDir, 'src', 'i18n', file), 'utf8'));
      } catch {
        return {};
      }
    };
    // per language: the launcher table (<code>.json) over the game-data table (game-<code>.json: weapon / skill / class names and texts)
    const strings = { langs: {}, available: discoverLanguages(rootDir) };
    for (const code of strings.available) {
      if (code === 'en') continue;
      strings.langs[code] = Object.assign({}, read('game-' + code + '.json'), read(code + '.json'));
      I18N.load(strings.langs[code], code);
    }
    I18N.setLang(langNow());
    return strings;
  }

  function setLang(lang) {
    I18N.setLang(lang);
  }

  return { I18N, langNow, load, setLang };
}

module.exports = { createLocale, discoverLanguages };
