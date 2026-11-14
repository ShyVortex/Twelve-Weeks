"""Link local-only files (game-derived data, toolchains, private tools) from a data root into a checkout.

  python tools/overlay.py link <data-root> [--dry-run]

Every file or directory under <data-root> that this checkout does not track is linked in at the same path:
directories as junctions (shared with the data root), files as copies (a build may rewrite them). Tracked paths are
never touched.
The linked paths go into .git/info/exclude so `git status` stays clean. Safe to re-run.
"""
import os
import subprocess
import sys

SKIP_TOP = {".git", ".claude", "node_modules", "dist", "__pycache__"}
SKIP_EXT = {".mp4", ".mov", ".mkv", ".llc", ".log"}


def tracked(repo):
    out = subprocess.run(["git", "-C", repo, "ls-files", "-z"], capture_output=True, check=True).stdout
    files = set(out.decode("utf-8").split("\0")) - {""}
    dirs = set()
    for f in files:
        p = f
        while "/" in p:
            p = p.rsplit("/", 1)[0]
            dirs.add(p)
    return files, dirs


def junction(src, dst):
    r = subprocess.run(["cmd", "/c", "mklink", "/J", dst.replace("/", "\\"), src.replace("/", "\\")], capture_output=True)
    if r.returncode:
        raise OSError(r.stderr.decode(errors="replace") or r.stdout.decode(errors="replace"))


def link_file(src, dst):
    import shutil
    shutil.copy2(src, dst)


def main():
    if len(sys.argv) < 3 or sys.argv[1] != "link":
        sys.exit(__doc__)
    data = os.path.abspath(sys.argv[2]).replace("\\", "/")
    dry = "--dry-run" in sys.argv
    repo = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip()
    files, dirs = tracked(repo)
    linked, n_dir, n_file = [], 0, 0

    def walk(rel):
        nonlocal n_dir, n_file
        base = os.path.join(data, rel) if rel else data
        for name in sorted(os.listdir(base)):
            r = f"{rel}/{name}" if rel else name
            if not rel and name in SKIP_TOP:
                continue
            if name in ("__pycache__", "node_modules") or os.path.splitext(name)[1].lower() in SKIP_EXT:
                continue
            src = os.path.join(base, name)
            dst = os.path.join(repo, r)
            if r in files:
                continue
            if r in dirs:
                if os.path.isdir(src):
                    walk(r)
                continue
            if os.path.lexists(dst):
                linked.append(r)
                continue
            if os.path.isdir(src):
                n_dir += 1
                if not dry:
                    junction(src, dst)
            else:
                n_file += 1
                if not dry:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    link_file(src, dst)
            linked.append(r)

    walk("")
    if not dry:
        ex = os.path.join(repo, ".git", "info", "exclude") if os.path.isdir(os.path.join(repo, ".git")) else None
        if ex is None:
            gd = subprocess.run(["git", "rev-parse", "--git-common-dir"], capture_output=True, text=True, cwd=repo).stdout.strip()
            ex = os.path.join(repo, gd, "info", "exclude") if not os.path.isabs(gd) else os.path.join(gd, "info", "exclude")
        os.makedirs(os.path.dirname(ex), exist_ok=True)
        old = open(ex, encoding="utf-8").read().splitlines() if os.path.exists(ex) else []
        keep = [l for l in old if not l.startswith("/") or l == "/"]
        with open(ex, "w", encoding="utf-8") as f:
            f.write("\n".join(keep + ["/" + p for p in sorted(set(linked))]) + "\n")
    print(f"{'would link' if dry else 'linked'} {n_dir} directories, {n_file} files ({len(linked)} paths excluded)")


if __name__ == "__main__":
    main()
