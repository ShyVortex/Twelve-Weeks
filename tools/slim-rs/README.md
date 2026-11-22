# t2r-slim (slim mod data)

The client no longer ships `t2r-maps/main/t2r-data.bin` (about 2.2 GB, most of it the game's own files with a few changes). It ships
`t2r-maps/main/t2r-data.slim` instead, and the launcher rebuilds the exact `t2r-data.bin` in the game folder from the player's own game files.

`t2r-data.slim` (format `T2SLIM03`) holds:

- a zstd patch against the game's original for every packed file that exists at the same path in the game (identical files: no patch at all),
- one xz stream with the packed files the game does not have,
- the few bytes of `t2r-data.bin` that are not file data (header, archive directory, table of contents, `_t2r*` files),
- the chunk table: how every rebuilt file is cut, lz4-HC compressed and encrypted, exactly as the build did.

The rebuild checks every file's hash, the payload FNV and the FNV of the whole file before the result replaces anything.
Files whose data lives in the Part I side file (`part1.dat`) are not touched.

Build 197, measured: 681.8 MB instead of 2173.2 MB (patches 261.9 MB for 220 game files, xz 416.0 MB for 5395 files, 1.6 MB kept bytes);
`make` 2 minutes, rebuild 43 seconds, byte-identical.

## Commands

```
t2r-slim make  <t2r-data.bin> <stage folder> <game folder> <out t2r-data.slim> [--cache <dir>] [--jobs N] [--xz-threads N]
t2r-slim check <t2r-data.bin> <t2r-data.slim> <game folder>
t2r-slim       <t2r-data.slim> <game folder> <out t2r-data.bin>
```

`release/build_release.py` runs `make` and `check` and puts `slim/t2r-slim.exe` into the client (`T2R_SLIM_DATA=0` ships the full file).
The launcher runs the third form (Proton on Linux). Exit codes: 0 ok, 1 file / usage error, 2 the game files differ from the pinned version, 3 internal.

## Build

```
cargo build --release
```

lz4 is pinned to 1.9.4 (`lz4-sys = "=1.9.4"`): the rebuilt chunks must be byte-identical to the ones the build's Python lz4 (liblz4 1.9.4) wrote.
The Windows build links the C runtime statically (`.cargo/config.toml`). `cargo test` runs the unit tests; the tool also builds and passes them on Linux.
