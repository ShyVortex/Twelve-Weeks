# servers: matchmaker and relay (C++)

C++ source of a matchmaker and a relay server for the client in `../winmm`:

- `matchmaker/`: accounts (SQLite), matchmaking, match setup.
- `relay/`: the UDP relay that forwards game traffic between players.

The live Twelve Weeks servers do not use this code. The game server is `tools/daemon.py` and the update server
is `tools/update_server/`. This folder is a reference for the client protocol.

## Building

Requirements: Windows and Visual Studio (MSVC). The matchmaker also needs SQLite and OpenSSL. `build.bat`
installs them with vcpkg into `%LOCALAPPDATA%\vcpkg` when they are missing.

```bat
build.bat            :: both servers
build.bat relay      :: relay only (no dependencies)
build.bat matchmaker
```

The output goes to `build\`. `run-local.bat` starts both servers on this machine.
