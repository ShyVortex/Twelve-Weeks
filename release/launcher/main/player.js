/**
 * @file Player identity resolution from config, the game and Steam.
 */
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const game = require('../lib/game');

/**
 * Create player-identity resolution.
 * @param {{ config: object, runtime: object, mode: object, log: Function }} options
 * @returns {object} Player API for name and token resolution.
 */
function createPlayer({ config, runtime, mode, log }) {
  async function readSteamUser() {
    try {
      const steamPath = await game.steamPathPublic();
      if (!steamPath) return null;
      const text = fs.readFileSync(path.join(steamPath, 'config', 'loginusers.vdf'), 'utf8');
      const re = /"(\d{17})"\s*\{([^}]*)\}/g;
      let match;
      let pick = null;
      while ((match = re.exec(text))) {
        const name = /"PersonaName"\s+"([^"]*)"/.exec(match[2]);
        const mostRecent = /"MostRecent"\s+"1"/.test(match[2]);
        if (name && (mostRecent || !pick)) {
          pick = { id: match[1], name: game.cleanName(name[1]) };
          if (mostRecent) break;
        }
      }
      return pick;
    } catch {
      return null;
    }
  }

  // every Steam account known on this PC, the most recent login first (the ban check sends them all: an alt account does not escape)
  async function readSteamIds() {
    try {
      const steamPath = await game.steamPathPublic();
      if (!steamPath) return [];
      const text = fs.readFileSync(path.join(steamPath, 'config', 'loginusers.vdf'), 'utf8');
      const re = /"(\d{17})"\s*\{([^}]*)\}/g;
      const recent = [];
      const rest = [];
      let match;
      while ((match = re.exec(text)))
        (/"MostRecent"\s+"1"/.test(match[2]) ? recent : rest).push(match[1]);
      return [...recent, ...rest].slice(0, 4);
    } catch {
      return [];
    }
  }

  async function resolveName() {
    const clean = game.cleanName;
    if (game.isGameDir(config.values.game_dir)) {
      const nameFile = path.join(config.values.game_dir, 't2r-name.txt');
      if (game.exists(nameFile)) {
        const name = clean(String(fs.readFileSync(nameFile, 'utf8').split(/\r?\n/)[0] || ''));
        if (name) return { name, source: 'In-game name' };
      }
    }
    if (config.values.custom_name) {
      const custom = clean(config.values.custom_name);
      if (custom) return { name: custom, source: 'Custom name (Settings)' };
    }
    const steam = await readSteamUser();
    if (steam && steam.name) return { name: steam.name, source: 'Steam name' };
    return {
      name: clean(os.userInfo().username) || 'Player',
      source: runtime.isLinux ? 'System user' : 'Windows user',
    };
  }

  // The name typed in the launcher is written to t2r-name.txt (line 1; line 2 = the tag stays) so the game and the launcher always agree.
  // The game (daemon names.py) only takes letters, digits, space . _ - and starts with a letter or digit; anything else would be refused
  // there and the player would see the old name. The file carries the name the game can really show.
  function gameFileName(name) {
    let clean = game
      .cleanName(name)
      .replace(/[^A-Za-z0-9 _.-]/g, '')
      .replace(/ +/g, ' ')
      .trim();
    clean = clean.replace(/^[^A-Za-z0-9]+/, '');
    return clean.slice(0, 15).trim();
  }

  function writeNameFile(name) {
    const clean = gameFileName(name);
    if (!clean || !game.isGameDir(config.values.game_dir)) return;
    if (config.writesBlocked()) return;
    if (mode.current()) return;
    const file = path.join(config.values.game_dir, 't2r-name.txt');
    let rest = '';
    let old = null;
    try {
      const lines = fs.readFileSync(file, 'utf8').split(/\r?\n/);
      old = lines[0];
      if (lines.length > 1) rest = lines.slice(1).join('\r\n');
    } catch {
      /* new file */
    }
    if (old === clean) return;
    fs.writeFileSync(file, clean + (rest ? '\r\n' + rest : ''));
    log(`t2r-name.txt written: ${clean} (a running game picks it up within ~3 s)`);
  }

  return { readSteamUser, readSteamIds, resolveName, writeNameFile };
}

module.exports = { createPlayer };
