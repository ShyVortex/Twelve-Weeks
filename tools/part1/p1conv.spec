# PyInstaller one-file build of p1conv:  python -m PyInstaller --distpath <dir> --workpath <dir> p1conv.spec   (run from tools/part1)
# Code only: no Part I or TLOU2 file is bundled. The converters (p1_levelset + p1_convert / p1_abi / havok_convert / p1_rsenv / p1_archive /
# p1_textures, and the stage helpers sp_maps_build imports) are collected from tools/part1, tools/features, tools/models by import analysis.
import os
here = os.path.abspath(SPECPATH)
tools = os.path.dirname(here)
a = Analysis(
    [os.path.join(here, "p1conv.py")],
    pathex=[here, tools, os.path.join(tools, "features"), os.path.join(tools, "models"), os.path.join(tools, "maps")],
    hiddenimports=["p1_levelset", "p1_fileset", "p1_convert", "p1_abi", "havok_convert", "p1_rsenv", "p1_archive", "p1_textures",
                   "p1_audio", "p1_actors", "p1_fires", "sp_maps_build", "psarc_extract", "ndpak", "havok_preview", "p1_audit", "p1mesh", "sp_maps",
                   "p1_pak", "p1_spawner_pak", "lz4", "lz4.block", "numpy", "scipy"],
    excludes=["tkinter", "matplotlib", "PIL.ImageTk", "IPython", "pytest"],
    datas=[(os.path.join(tools, "maps", "sp_maps.json"), os.path.join("tools", "maps")),
           (os.path.join(here, "data"), "data"),                       # p1_abi_ref.json, p1_rs_defaults.json: our recipe data
           (os.path.join(tools, "maps", "data", "p1-bookstore-spawn-arts.json"), os.path.join("tools", "maps", "data"))],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="p1conv", console=True, upx=False)
