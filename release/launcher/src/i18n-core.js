/**
 * @file Language tables and the shared translation lookup core.
 */
'use strict';
// Launcher translation core (browser script AND node module). The English source text IS the key: src/i18n/pl.json maps English -> Polish (plus
// src/i18n/game-pl.json, generated from the mod's tools/loc/pl for weapon / skill / class names and descriptions); src/i18n/en.json lists the English
// source strings (identity, kept in step by test/i18n-test.js).
//   T('PLAY')                         exact entry
//   T('Client updated to 74 (5 files).')   matched against pattern entries written with {name} placeholders: "Client updated to {v} ({n} files)."
//   Polish templates may use  {n|plik|pliki|plików}  (Polish plural by the number n),  {name!}  (translate the captured text too),  {1} {2}  (loc style).
// More languages (community contribution by OmegaMan): src/i18n/<code>.json + game-<code>.json, registered in src/i18n/languages.js. The tables are kept PER
// LANGUAGE (load(dict, code)), so a second language never overwrites the first one's entries; load(dict) without a code applies to every language (tests, legacy).
// src/i18n/es.json and game-es.json were translated with LLMs.
(function (root) {
  // core.tables: language code -> dictionary; '*' = entries without a language; core.dict = '*' + the table of the current language
  const core = { lang: 'en', dict: {}, pats: null, tables: {} };
  const esc = (s) => s.replace(/[.*+?^$()|[\]\\]/g, '\\$&');
  // plural form index per language (templates are {n|one|few|many}; en / es: one|other)
  const pluralRules = {
    en: (n) => (n === 1 ? 0 : 1),
    es: (n) => (n === 1 ? 0 : 1),
    pl: (n) => {
      if (n === 1) return 0;
      const a = n % 10,
        b = n % 100;
      return a >= 2 && a <= 4 && (b < 12 || b > 14) ? 1 : 2;
    },
  };
  const plural = (n, lang) => (pluralRules[lang] || pluralRules.en)(Math.abs(n));
  const rebuild = () => {
    core.dict = Object.assign({}, core.tables['*'], core.tables[core.lang]);
    core.pats = null;
  };

  function compile() {
    core.pats = [];
    for (const k of Object.keys(core.dict)) {
      if (!/\{[A-Za-z0-9_]+\}/.test(k)) continue;
      const names = [];
      const rx = new RegExp(
        '^' +
          esc(k).replace(/\\?\{([A-Za-z0-9_]+)\\?\}/g, (_, n) => {
            names.push(n);
            return '([\\s\\S]+?)';
          }) +
          '$',
      );
      core.pats.push({ rx, names, to: core.dict[k] });
    }
    core.pats.sort((a, b) => b.rx.source.length - a.rx.source.length);
  }
  function fill(tpl, vars) {
    return tpl.replace(/\{([A-Za-z0-9_]+)(!)?(?:\|([^}]*))?\}/g, (m, n, bang, forms) => {
      if (!(n in vars)) return m;
      const v = vars[n];
      if (forms) {
        const f = forms.split('|');
        return f[plural(parseInt(v, 10), core.lang)] || f[f.length - 1];
      }
      return bang ? core.T(String(v)) : String(v);
    });
  }
  core.load = (dict, lang) => {
    const k = lang || '*';
    core.tables[k] = Object.assign({}, core.tables[k], dict);
    rebuild();
  };
  // 'pl', 'pl-PL', 'es_ES' -> the base code; a language nobody loaded a table for simply stays English text
  core.setLang = (l) => {
    core.lang =
      String(l || '')
        .toLowerCase()
        .split(/[-_]/)[0] || 'en';
    rebuild();
  };
  core.T = (s, vars) => {
    if (s == null) return s;
    s = String(s);
    if (core.lang === 'en') return vars ? fill(s, vars) : s;
    let to = core.dict[s];
    if (to !== undefined && !vars) return fill(to, {});
    if (vars) return fill(core.dict[s] !== undefined ? core.dict[s] : s, vars);
    if (!core.pats) compile();
    for (const p of core.pats) {
      const m = p.rx.exec(s);
      if (m) {
        const v = {};
        p.names.forEach((n, i) => {
          v[n] = m[i + 1];
        });
        return fill(p.to, v);
      }
    }
    return s;
  };
  core.plural = plural;
  if (typeof module !== 'undefined' && module.exports) module.exports = core;
  else root.I18N = core;
})(typeof window !== 'undefined' ? window : globalThis);
