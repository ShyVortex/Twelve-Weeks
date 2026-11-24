use std::collections::HashMap;
use std::fs::File;
use std::io::Read;
use std::path::Path;

use md5::{Digest, Md5};

use crate::util::*;

pub trait Source {
    fn read(&mut self, pos: u64, n: usize) -> Res<Vec<u8>>;
}

pub struct Dsar {
    f: File,
    off: Vec<u64>,
    usz: Vec<u32>,
    csz: Vec<u32>,
    ustart: Vec<u64>,
    cached: Option<(usize, Vec<u8>)>,
    name: String,
}

impl Dsar {
    pub fn open(path: &Path) -> Res<Dsar> {
        let name = path.display().to_string();
        let f = io_ctx(File::open(path), || format!("cannot open {}", name))?;
        let mut h = [0u8; 0x28];
        io_ctx(read_at(&f, 0, &mut h), || format!("cannot read {}", name))?;
        if &h[..4] != b"DSAR" {
            return fail(EXIT_GAME, format!("{} is not a DSAR archive", name));
        }
        let n = le32(&h, 8) as usize;
        if n > 1 << 24 {
            return fail(EXIT_GAME, format!("{}: unexpected DSAR layout", name));
        }
        let mut dir = vec![0u8; n * 0x20];
        io_ctx(read_at(&f, 0x28, &mut dir), || format!("cannot read {}", name))?;
        let (mut off, mut usz, mut csz, mut ustart) = (Vec::with_capacity(n), Vec::with_capacity(n), Vec::with_capacity(n), Vec::with_capacity(n));
        let mut u = 0u64;
        for i in 0..n {
            off.push(le64(&dir, i * 0x20));
            let us = le32(&dir, i * 0x20 + 8);
            usz.push(us);
            csz.push(le32(&dir, i * 0x20 + 12));
            ustart.push(u);
            u += us as u64;
        }
        Ok(Dsar { f, off, usz, csz, ustart, cached: None, name })
    }

    fn chunk(&mut self, i: usize) -> Res<&[u8]> {
        if self.cached.as_ref().map(|c| c.0) != Some(i) {
            let (usz, csz) = (self.usz[i] as usize, self.csz[i] as usize);
            let data = if csz == 0 {
                vec![0u8; usz]
            } else {
                let mut raw = vec![0u8; csz];
                io_ctx(read_at(&self.f, self.off[i], &mut raw), || format!("cannot read {}", self.name))?;
                if csz == usz {
                    raw
                } else {
                    match lz4_decompress(&raw, usz) {
                        Some(d) => d,
                        None => return fail(EXIT_GAME, format!("{}: damaged chunk {}", self.name, i)),
                    }
                }
            };
            self.cached = Some((i, data));
        }
        Ok(&self.cached.as_ref().unwrap().1)
    }
}

impl Source for Dsar {
    fn read(&mut self, pos: u64, n: usize) -> Res<Vec<u8>> {
        let mut out = Vec::with_capacity(n);
        while out.len() < n {
            let p = pos + out.len() as u64;
            let i = match self.ustart.partition_point(|&s| s <= p) {
                0 => return fail(EXIT_GAME, format!("{}: read outside the archive", self.name)),
                k => k - 1,
            };
            if p >= self.ustart[i] + self.usz[i] as u64 {
                return fail(EXIT_GAME, format!("{}: read outside the archive", self.name));
            }
            let start = self.ustart[i];
            let c = self.chunk(i)?;
            let a = (p - start) as usize;
            let take = (c.len() - a).min(n - out.len());
            out.extend_from_slice(&c[a..a + take]);
        }
        Ok(out)
    }
}

#[derive(Clone, Copy, Debug)]
pub struct TocEntry {
    pub block: u32,
    pub size: u64,
    pub off: u64,
}

pub struct Psarc<S: Source> {
    pub src: S,
    pub toc: HashMap<[u8; 16], TocEntry>,
    first: TocEntry,
    bsizes: Vec<u32>,
    bsize: u32,
}

pub fn path_md5(p: &str) -> [u8; 16] {
    Md5::digest(p.as_bytes()).into()
}

impl<S: Source> Psarc<S> {
    pub fn open(mut src: S, what: &str) -> Res<Psarc<S>> {
        let hd = src.read(0, 32)?;
        if &hd[..4] != b"PSAR" {
            return fail(EXIT_GAME, format!("{}: not a PSARC", what));
        }
        if &hd[8..12] != b"zlib" {
            return fail(EXIT_GAME, format!("{}: PSARC compression is not zlib", what));
        }
        let (toc_len, esz, n, bsize) = (be32(&hd, 12) as usize, be32(&hd, 16) as usize, be32(&hd, 20) as usize, be32(&hd, 24));
        if esz != 30 || toc_len > 64 << 20 || 32 + n * 30 > toc_len || n == 0 || bsize == 0 {
            return fail(EXIT_GAME, format!("{}: unexpected PSARC layout", what));
        }
        let toc_raw = src.read(0, toc_len)?;
        let ent = |i: usize| {
            let e = &toc_raw[32 + i * 30..32 + (i + 1) * 30];
            (<[u8; 16]>::try_from(&e[..16]).unwrap(), TocEntry { block: be32(e, 16), size: be40(e, 20), off: be40(e, 25) })
        };
        let mut toc = HashMap::with_capacity(n);
        for i in 1..n {
            let (m, e) = ent(i);
            toc.insert(m, e);
        }
        let width = if bsize <= 0x10000 { 2 } else if bsize <= 0x1000000 { 3 } else { 4 };
        let bt = 32 + n * 30;
        let bsizes = toc_raw[bt..].chunks_exact(width).map(|b| b.iter().fold(0u32, |a, &x| a << 8 | x as u32)).collect();
        Ok(Psarc { src, toc, first: ent(0).1, bsizes, bsize })
    }

    fn file_at(&mut self, e: TocEntry, what: &str) -> Res<Vec<u8>> {
        let mut out = Vec::with_capacity(e.size as usize);
        let (mut bi, mut off) = (e.block as usize, e.off);
        while (out.len() as u64) < e.size {
            let cs = match self.bsizes.get(bi) {
                Some(0) => self.bsize,
                Some(&c) => c,
                None => return fail(EXIT_GAME, format!("{}: block table too short", what)),
            } as usize;
            let want = (self.bsize as u64).min(e.size - out.len() as u64) as usize;
            if cs > self.bsize as usize + 16 {
                return fail(EXIT_GAME, format!("{}: damaged block table", what));
            }
            let blk = self.src.read(off, cs)?;
            if cs == want {
                out.extend_from_slice(&blk);
            } else {
                let mut d = flate2::read::ZlibDecoder::new(&blk[..]);
                let mut buf = Vec::with_capacity(want);
                if d.read_to_end(&mut buf).is_err() || buf.len() != want {
                    return fail(EXIT_GAME, format!("{}: a zlib block is damaged", what));
                }
                out.extend_from_slice(&buf);
            }
            off += cs as u64;
            bi += 1;
        }
        Ok(out)
    }

    pub fn file(&mut self, md5: &[u8; 16], what: &str) -> Res<Option<Vec<u8>>> {
        match self.toc.get(md5).copied() {
            Some(e) => self.file_at(e, what).map(Some),
            None => Ok(None),
        }
    }

    pub fn paths(&mut self, what: &str) -> Res<Vec<String>> {
        let m = self.file_at(self.first, what)?;
        Ok(String::from_utf8_lossy(&m).split(['\0', '\n']).filter(|p| !p.is_empty()).map(|p| p.to_string()).collect())
    }
}

pub fn valid_archive_name(a: &str) -> bool {
    !a.is_empty() && a.len() < 48 && a.ends_with(".psarc") && a.bytes().all(|c| c.is_ascii_alphanumeric() || b"-_.".contains(&c)) && !a.contains("..")
}

pub fn game_archive(game: &Path, arch: &str) -> std::path::PathBuf {
    game.join("build").join("pc").join("main").join(arch)
}

pub struct GameIndex {
    pub by_path: HashMap<String, Vec<(String, u64)>>,
}

impl GameIndex {
    pub fn build(game: &Path) -> Res<GameIndex> {
        let main = game.join("build").join("pc").join("main");
        let mut names: Vec<String> = io_ctx(std::fs::read_dir(&main), || format!("game folder not found: {}", main.display()))?
            .filter_map(|e| e.ok())
            .map(|e| e.file_name().to_string_lossy().into_owned())
            .filter(|n| n.ends_with(".psarc"))
            .collect();
        names.sort();
        let mut by_path: HashMap<String, Vec<(String, u64)>> = HashMap::new();
        for a in names {
            if !valid_archive_name(&a) {
                continue;
            }
            let mut p = Psarc::open(Dsar::open(&main.join(&a))?, &a)?;
            for path in p.paths(&a)? {
                if let Some(e) = p.toc.get(&path_md5(&path)) {
                    by_path.entry(path).or_default().push((a.clone(), e.size));
                }
            }
        }
        Ok(GameIndex { by_path })
    }

    pub fn pick(&self, path: &str, size: u64) -> Option<(String, u64)> {
        let c = self.by_path.get(path)?;
        c.iter().find(|(_, s)| *s == size).or_else(|| c.first()).cloned()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn archive_names() {
        assert!(valid_archive_name("world-farm.psarc"));
        assert!(valid_archive_name("common.psarc"));
        assert!(!valid_archive_name("../common.psarc"));
        assert!(!valid_archive_name("a\\b.psarc"));
        assert!(!valid_archive_name("common.exe"));
        assert!(!valid_archive_name(""));
    }
}
