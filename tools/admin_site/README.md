# Twelve Weeks admin site

A local, launcher-styled web page for the server owner (Python stdlib only, binds **127.0.0.1** only).

```
python tools/admin_site/admin.py --db "%LOCALAPPDATA%\T2R-Factions2\t2r.db" --daemon-log <host folder>\daemon.log ^
       --reports <update data>\reports [--port 7010] [--daemon 127.0.0.1:7001] [--admin-url http://127.0.0.1:7011] [--update-data <update data>]
```
Open http://127.0.0.1:7010/ . Keys: `1-6` tabs, `/` search, `Esc` back, `P` pause the 3 s refresh, `R` refresh now.

Tabs: OVERVIEW (server up/down, uptime, build vs latest published, online / in match / searching, matches, recent errors), PLAYERS (online now with state,
clan, ping, build, platform, session length and a FORCE KICK button; all-time list with search; per-player page with clan state, morale, clan feed, match
history, bug reports), MATCHES (live matches with teams, map, host, ping, time left, reinforcements; recent results), CLANS (all clans, at-risk ones, feed),
REPORTS (bug reports, files, text preview, mark handled, attached screenshots as click-to-open thumbnails via `/api/report-image`, attached clips in an inline player via `/api/report-video` with HTTP Range seeking; both only for files the server recorded as screenshot/video, type from the bytes), LOGS (daemon log tail, filter, error highlighting, rotated logs, tokens masked).

PATCH NOTES tab (key `8`, needs `--update-data`): the launcher's own NEWS page made editable in place (`static/news.html` + `newsframe.js` in an iframe; it loads the launcher's real `release/launcher/src/app/news.js`, `news.css`, `style.css`, `neat.css`, `i18n/pl.json` through the same `/launcher/src/...` route the CLAN page uses, so it always looks exactly like the launcher; `release/launcher/src` must exist next to the admin on the host). Click an entry to open it, click any text to edit it (Enter = new line, Backspace on an empty line removes it, hover `+` adds a line, paste is plain text), EN / PL switch (a missing PL text shows the English one dimmed; typing there creates the PL text), date / build / kind / stamp strip inside the opened entry, new entry = next id + today, delete entry with confirm, unsaved-changes flag. SAVE TO LIVE validates, backs the old file up to `<update data>/news-backups/` (last 20) and replaces `news.json` atomically; the update server re-reads the file on every request, so launchers see it at once. The only other file this site writes besides the report `handled` flag.

## Where the data comes from
| Source | When | Gives |
|---|---|---|
| `live` | daemon build with the admin listener (needs a daemon restart) and `admin-secret.txt` next to the DB | real-time players / queue / matches, ping, kick |
| `snapshot` | `t2r-status.json` next to the DB, written by the same daemon build every 10 s | same, up to 10 s old, no kick |
| `log` | always available from `--daemon-log` (EVT / STATUS / ANNOUNCE lines) | online count (last STATUS line), running matches (players, map, host), history; approximate: no scores, no ping, names of menu players only if they opened the MP menu in the last minute |
The database (`t2r.db`) is opened `mode=ro` per query (1.5 s timeout, never written, no long locks). Player stats, clans, names, feed, client builds
(`client_versions.json`) and platform (`linux_clients.json`) come from it and the files beside it. Kills / deaths / executions are not recorded by the
server, so they are not shown (the page says so). Match history is reconstructed from the retained daemon logs (`daemon.log` + rotated files).

## Safety
* Only the report store (`handled` flag in meta.json) and, after an in-page confirm, `POST /kick` to the daemon's loopback listener are written.
* Requests need `Host: 127.0.0.1|localhost:<port>` (DNS rebinding); POSTs need the `X-Admin-Request` header and a same-origin `Origin` (CSRF).
* Tokens are never shown: players are addressed by a hash id; log lines have long hex runs and byte dumps masked.
* The game port is only probed with a connect + close (nothing is sent; the daemon logs nothing for it).

Tests: `python tools/admin_site/test_admin.py` and `python tools/tests/test_admin_kick.py` (daemon side: live snapshot, kick, listener).

## Clan page (launcher CLAN tab, read-only)

The player page embeds `/clan.html?id=<player id>` (iframe): the launcher's own `clan.js`, `clan-fx.js`, `clan-status.js`, styles and portrait / icon assets, served read-only from `release/launcher/` (whitelisted paths under `/launcher/src/` and `/launcher/assets/`), fed by `/api/clanview?id=<player id>[&lang=pl]`, which returns the same payloads as the update server's `/clan.json` and `/clanfeed.json` (`tools/update_server/clan_view.py`, `clanfeed_view.py`, called with `key=` = the player's clan row). Tabs OVERVIEW / SURVIVORS / RAIDS / JOURNAL are the launcher's sections grouped; EN / PL button inside. `&still=1` skips the entrance motion (screenshots).
