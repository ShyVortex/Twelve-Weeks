#!/usr/bin/env bash
# Build t2r-bridge.exe (Windows x64) with llvm-mingw. Static, no SDK headers.
set -e
cd "$(dirname "$0")"
CC=x86_64-w64-mingw32-gcc
"$CC" -O2 -o t2r-bridge.exe t2r-bridge.c -lws2_32 -static
echo "built: $(ls -la t2r-bridge.exe | awk '{print $5, $NF}')"
