# T2R update server

Serves the launcher: manifest, content-addressed files (HTTP Range, resumable), news, status. Python stdlib only.

## Publish a client build
```
python tools/update_server/publish.py dist/client --data <data> --channel stable --version 74
python tools/update_server/publish.py --data <data> --launcher T2R-Launcher-Setup.exe --launcher-version 1.0.0   # optional
python tools/update_server/publish.py --data <data> --channel stable --version 73 --promote-only                 # rollback
python tools/update_server/publish.py --data <data> --gc 3        # optional: free blobs not used by the newest 3 versions
```
Files are stored once by sha256 (`blobs/`), so a new version only adds the changed files. Manifests of old versions stay
Compressed transfer: `publish.py` also writes `blobs/<sha256>.gz` (gzip -9; `.br` brotli q9 if `pip install brotli` is present, else gzip) for every blob that shrinks by >= 5 % (empty `<sha256>.nz` = tried, not worth it) and adds `zsize`/`enc` to the manifest; the server adds `zurl` and serves `/files/<sha256>.gz|.br` with Range. On the real playtest76 client this turns 1.12 GB into about 255 MB (winmm.dll 847 MB -> 1.7 MB, t2r-ext.dll 50 -> 31 MB, t2r-slim.dat stays raw). Add it to already published versions without republishing: `python tools/update_server/publish.py --data <data> --recompress`. `--no-compress` / `--codec gzip|br` override.
(`manifests/<channel>/<version>.json`); `channels.json` says which one a channel serves. `t2r-play.log`, `t2r-client.json`,
`linux-config.json` are never published. `news.json` in the data dir is served as-is. Newest first, one entry per build / hotfix: `{"id":10,"date":"2026-10-20","build":"85","kind":"build|hotfix","stamp":"4080fec4","headline":"a few words","sections":{"changed":[],"why":[],"watch":[],"known":[],"fixed":[]}}` (only non-empty sections are shown; hotfix of 85 = `"build":"85.2"`). The old `{date,title,text|body}` shape still renders. Every entry also carries a `pl` object (Polish headline/sections/title/body, merged from `release/news-pl.json` by `release/news_merge_pl.py`); old launchers ignore it. Full field list: `release/launcher/API.md`; the current draft lives in `release/news.json`.

## Publish a client build to GitHub Releases
```
python tools/update_server/publish_github.py dist/client --repo <owner>/<repo> --version 198 --data <data>
```
Every client file goes up once as a release asset named by its sha256 (plus `<sha256>.gz` where gzip saves >= 5 %, plus `manifest.json`);
assets must be under 2 GiB. Order: draft release, upload, sizes checked, release made public, and only then the manifest (absolute
`https://github.com/<repo>/releases/download/build-<version>/<sha256>` urls) is written to `<data>` and promoted. The server keeps an
entry's `https://` url and `zurl` as they are and does not look for its blob locally, so launchers download from GitHub while
`/manifest.json`, news and status stay here. Needs the `gh` CLI, logged in with write access to the repository. `--dry-run` prints the
plan and uploads nothing.

Switching players over: launchers up to 0.1.44 cannot rebuild `t2r-data.bin` from a slim client, so until every player runs a launcher
with the slim rebuild, publish each build twice. `build_release.py` writes both clients: `<out>/client` (slim) and `<out>/client-full`
(the same files with `t2r-data.bin`, hardlinked).
```
python tools/update_server/publish.py <out>/client-full --data <data> --channel stable --version 198                         # older launchers, served from here
python tools/update_server/publish_github.py <out>/client --repo <owner>/<repo> --channel stable-slim --version 198 --data <data>
```
New launchers ask for `<channel>-slim` first and fall back to `<channel>`. Both manifests carry the same `launcher` entry, so an older
launcher downloads the full build as before and then updates itself at PLAY. One whose self-update fails (it tries once per version)
keeps playing the full build. The launcher change for the shipping 0.1.44 source is `release/launcher/patches/0.1.44-slim-data.patch`
(the repo's launcher tree is older than 0.1.44). Give the new launcher a higher version (0.1.45), or 0.1.44 is not offered it.

The launcher's own updates go the same way:
```
python tools/update_server/publish_github.py --repo <owner>/<repo> --launcher TwelveWeeks-Launcher-0.1.45.exe \
       --launcher-linux TwelveWeeks-Launcher-0.1.45.AppImage --launcher-version 0.1.45 --data <data>
```
makes the release `launcher-<version>` (the installers under their own names, so the release page doubles as the download page) and
writes `launcher.json` / `launcher-linux.json` with their GitHub urls; `/manifest.json` hands those to the launcher's self-update
(`launcher`, `launcher_linux`). A `launcher.json` without a url (`publish.py --launcher`) is still served from `/files/` here.

## Run
```
python tools/update_server/server.py --data <data> --port 7002 --public-url http://example.tun.ply.gg:PORT \
       --status-file <data>/status.json
```
- `--public-url` is put in front of `/files/<sha>` in manifests (default: the request's Host header, fine for LAN/tests).
- Status: start the daemon with `T2R_STATUS_FILE=<data>/status.json` (read-only snapshot every 10 s, default off); `/status.json`
  then gives `{online, server_version, matches, players_online, queue}`. Without it use `--daemon 127.0.0.1:7001`: online/server_version
  come from the same version question the launcher asks, `matches` is null.
- Endpoints: `/manifest.json?channel=stable[&version=X]`, `/files/<sha256>`, `/news.json`, `/status.json`, `/versions.json?channel=stable`.

## Behind the playit tunnel
The game tunnel (`example.tun.ply.gg:15389` -> 7001) is a UDP+TCP game tunnel. The update server needs its own
TCP tunnel in playit.gg: Tunnels -> Add -> TCP (a custom/"Minecraft Java"-free plain TCP tunnel), local address `127.0.0.1`,
local port `7002`. playit shows a new address like `xxx.tun.ply.gg:NNNNN`; pass `http://xxx.tun.ply.gg:NNNNN` as `--public-url`
and put the same URL into the launcher's config. (A free playit account may have a tunnel limit; if so the same update URL can
come from a static host/CDN: copy `blobs/`, `manifests/`, `channels.json` is not enough there since the manifest is generated -
use this server.) Use a separate port from the daemon; do not point the update tunnel at 7001.

## Tests
`python tools/update_server/test_update_server.py`

## Clan view (launcher CLAN tab)
`--db <path to the daemon's t2r.db>` enables `GET /clan.json?player=<24-hex install id>` (the last 24 hex chars of the name token also work).
The database is opened read-only (`mode=ro`); nothing is written or migrated. Fields: see `release/launcher/API.md`.
The id is the player's identity key: serve this only over a connection you trust, or leave `--db` off.

## Bug reports (launcher: REPORT A BUG)
`POST /report` takes ONE zip body (`Content-Type: application/zip`, max 80 MB): `meta.json` + `files/...`. At most 5 reports per IP per hour; the zip is
validated (entries, sizes, zip-bomb guard) and its files are written under `<data>/reports/<UTC date-time>_<code>_<player>/files/` with flat safe
names (zip-slip safe, nothing executed); `meta.json` there holds the player's text, when, map, build, steam id, name, received time, IP, file list.
Nothing is served back over HTTP. `--reports <dir>` moves the folder; `--reports ""` disables the endpoint. Read them:
```
python tools/update_server/reports.py --data <data> list [--all]      # new reports, newest first
python tools/update_server/reports.py --data <data> show R-7F3K      # text + paths of the log files
python tools/update_server/reports.py --data <data> handled R-7F3K
```
Attachments: `files/screenshot-N.<png|jpg|webp|gif|bmp>` inside the zip (max 5, 8 MB each, magic bytes checked, otherwise the report is refused) and video
clips via `PUT /report-clip?code&key` after the zip (max 2, 200 MB each, 250 MB together, streamed to disk, mp4/mov/webm/mkv by magic bytes; 3 reports with
clips per IP per hour; refused when the reports folder is over `T2R_REPORTS_MAX_GB` (20) or free disk under `T2R_REPORTS_MIN_FREE_GB` (10)). Format: release/launcher/API.md.
Tests: `python tools/update_server/test_reports.py`.

## Part I map pack (launcher MAPS tab, "Download from server (temporary)")
Separate from the release: `GET /part1-maps.json` -> `{pack, ver, hash, maps, total, files:[{name, sha256, size, url}]}` (404 `{"error"}` while nothing is published), `GET /part1-files/<sha256>` (Range). Data: `<data>/part1/manifest.json` + `<data>/part1/blobs/`; `/manifest.json`, `publish.py` and `--gc` never touch it.
```
python tools/update_server/publish_part1.py <folder with part1-a.psarc + part1-a.txt> --data <data>   # --remove = offline, --gc = free old blobs
python tools/update_server/patch_part1_server.py <path to an existing server.py>   # patch a deployed server (Pi) in place, idempotent; part1_maps.py must sit next to it
```
Tests: `python tools/update_server/test_part1_maps.py`. Design: `re/launcher/part1-dlc.md` section 7.
