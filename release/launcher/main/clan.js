/**
 * @file Clan feed polling and summary data for the CLAN tab.
 */
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const game = require('../lib/game');
const upd = require('../lib/update');
const dmn = require('../lib/daemon');
const clanwire = require('../lib/clanwire');
const gameData = require('./gamedata');
const { isSupported } = require('../src/i18n/languages');

/**
 * Create the clan-feed service.
 * @param {{ config: object, paths: object, player: object, locale: object }} options
 * @returns {object} Clan API for summaries and feed data.
 */
function createClan({ config, paths, player, locale, userData }) {
  async function getClan() {
    let why = '';
    try {
      const name = await player.resolveName();
      const steam = await player.readSteamUser();
      const token = game.nameToken(name.name, config.values.token_id);
      const { host, port } = game.parseServer(paths.serverAddress());
      const texts = await dmn.clanTexts(host, port, token, steam && steam.id);
      const clan = clanwire.fromWire(texts.state, texts.meta, gameData());
      if (clan) return { clan };
      why = 'the game server did not answer';
    } catch (e) {
      why = e.message;
    }
    const host = paths.fileHost();
    if (host) {
      try {
        return {
          clan: await upd.getJson(`${host}/clan.json?player=${config.values.token_id}`, 4000),
        };
      } catch (e) {
        why += (why ? '; ' : '') + 'update server: ' + e.message;
      }
    }
    return { clan: null, error: why || 'no clan source' };
  }

  async function getClanFeed(since, lang) {
    lang = lang && isSupported(lang) ? lang : locale.langNow();
    try {
      const name = await player.resolveName();
      const token = game.nameToken(name.name, config.values.token_id);
      const { host, port } = game.parseServer(paths.serverAddress());
      const lines = await dmn.feedLines(host, port, token, lang);
      if (lines && lines.length) {
        const out = {
          ok: true,
          hasClan: true,
          source: 'daemon',
          feed: lines.map((line) => ({
            id: 'd' + line.id,
            text: line.text,
            mood: '',
            kind: 'feed',
          })),
        };
        const updateHost = paths.fileHost();
        if (updateHost) {
          try {
            const json = await upd.getJson(
              `${updateHost}/clanfeed.json?player=${config.values.token_id}&limit=1&lang=${lang}`,
              1500,
            );
            if (json && json.ok && json.alife) out.alife = json.alife;
          } catch {
            /* optional */
          }
        }
        return { feed: out };
      }
    } catch {
      /* fall through */
    }
    const host = paths.fileHost();
    if (!host) return { feed: null, error: 'no feed source' };
    try {
      const json = await upd.getJson(
        `${host}/clanfeed.json?player=${config.values.token_id}&limit=40&since=${Math.max(
          0,
          since | 0,
        )}&lang=${lang}`,
        4000,
      );
      if (json && json.ok && json.hasClan && Array.isArray(json.menu) && json.menu.length)
        return {
          feed: {
            ok: true,
            hasClan: true,
            source: 'server',
            alife: json.alife || null,
            feed: json.menu.map((line) => ({
              id: 'd' + line.id,
              text: line.text,
              mood: '',
              kind: 'feed',
            })),
          },
        };
      return { feed: json };
    } catch (e) {
      return { feed: null, error: e.message };
    }
  }

  async function getNews() {
    const host = paths.fileHost();
    if (!host) return { items: [], error: 'No update server configured' };
    try {
      const json = await upd.getJson(`${host}/news.json`, 8000, { force: true });
      return {
        items: Array.isArray(json) ? json : json.items || [],
      };
    } catch (e) {
      return { items: [], error: e.message };
    }
  }

  // News media (GIF / WebP / PNG / JPG / MP4 / WebM named in a news entry's blocks): fetched from <update server>/media/<name> on first use,
  // kept in <userData>/news-media, handed to the renderer as a data: URI (the page's CSP allows only 'self' and data:). Plain file names only.
  const MEDIA_TYPES = {
    gif: 'image/gif',
    webp: 'image/webp',
    png: 'image/png',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    mp4: 'video/mp4',
    webm: 'video/webm',
  };
  async function getNewsMedia(src) {
    const m = /^(?:media\/)?([A-Za-z0-9_-][A-Za-z0-9_.-]{0,80})\.([A-Za-z0-9]{3,4})$/.exec(
      String(src || ''),
    );
    const type = m && MEDIA_TYPES[m[2].toLowerCase()];
    if (!type) return { ok: false, error: 'bad media name' };
    const name = `${m[1]}.${m[2].toLowerCase()}`;
    const dir = path.join(userData || os.tmpdir(), 'news-media');
    const file = path.join(dir, name);
    const asUri = (buf) => ({
      ok: true,
      uri: `data:${type};base64,${buf.toString('base64')}`,
      video: type.startsWith('video/'),
    });
    try {
      return asUri(fs.readFileSync(file));
    } catch {}
    const host = paths.fileHost();
    if (!host) return { ok: false, error: 'No update server configured' };
    try {
      const buf = await upd.getBuffer(`${host}/media/${name}`, 12000);
      try {
        fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(file, buf);
      } catch {}
      return asUri(buf);
    } catch (e) {
      return { ok: false, error: e.message };
    }
  }

  return { getClan, getClanFeed, getNews, getNewsMedia };
}

module.exports = { createClan };
