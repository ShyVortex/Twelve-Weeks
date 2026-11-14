'use strict';
// Source groups for the tests that read launcher source text. The code was split into modules (main/*, lib/game/*, lib/update/*, lib/report/*,
// src/app/*, src/loadout-*.js); a group is the old file plus the modules that now hold its code. Paths are relative to release/launcher.
const fs = require('fs');
const path = require('path');
const root = path.join(__dirname, '..');
const walk = (d) => fs.readdirSync(path.join(root, d), { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : /\.js$/.test(e.name) ? [path.join(d, e.name)] : [])).sort();
const GROUPS = {
  main: () => ['main.js', ...walk('main')],
  game: () => ['lib/game.js', ...walk('lib/game')],
  update: () => ['lib/update.js', ...walk('lib/update')],
  report: () => ['lib/report.js', ...walk('lib/report')],
  app: () => ['src/app.js', ...walk('src/app')],
  loadout: () => ['src/loadout.js', 'src/loadout-model.js', 'src/loadout-view.js'],
};
const files = (g) => GROUPS[g]();
const text = (g) => files(g).map((f) => fs.readFileSync(path.join(root, f), 'utf8')).join('\n');
module.exports = { root, files, text, read: (f) => fs.readFileSync(path.join(root, f), 'utf8') };
