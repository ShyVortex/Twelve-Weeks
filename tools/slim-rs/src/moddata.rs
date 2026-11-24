use std::fs::File;
use std::path::Path;

use crate::archive::Source;
use crate::util::*;

#[derive(Clone, Copy, Debug)]
pub struct ChunkEnt {
    pub off: u64,
    pub usz: u32,
    pub csz: u32,
}

pub struct ModData {
    pub f: File,
    pub file_size: u64,
    pub off: u64,
    pub size: u64,
    pub fnv: u64,
    pub build_id: [u8; 16],
    pub ent: Vec<ChunkEnt>,
    pub ustart: Vec<u64>,
    cached: Option<(usize, Vec<u8>)>,
}

impl ModData {
    pub fn open(path: &Path) -> Res<ModData> {
        let name = path.display().to_string();
        let f = io_ctx(File::open(path), || format!("cannot open {}", name))?;
        let file_size = f.metadata()?.len();
        let mut h = [0u8; 0x38];
        io_ctx(read_at(&f, 0, &mut h), || format!("cannot read {}", name))?;
        if &h[..4] != b"T2RD" || le32(&h, 4) != 1 {
            return fail(EXIT_IO, format!("{} is not a t2r-data.bin (version 1)", name));
        }
        let size = le64(&h, 8);
        let fnv = le64(&h, 0x10);
        let build_id: [u8; 16] = h[0x18..0x28].try_into().unwrap();
        let off = le64(&h, 0x28).checked_add(le64(&h, 0x30)).unwrap_or(u64::MAX);
        if off.checked_add(size).map_or(true, |e| e > file_size) {
            return fail(EXIT_IO, format!("{}: the payload does not fit the file", name));
        }
        let mut m = ModData { f, file_size, off, size, fnv, build_id, ent: Vec::new(), ustart: Vec::new(), cached: None };
        let n = le32(&m.dec(8, 4)?, 0) as usize;
        if n > 1 << 26 || 0x28 + n as u64 * 0x20 > size {
            return fail(EXIT_IO, format!("{}: unexpected archive directory", name));
        }
        let dir = m.dec(0x28, n * 0x20)?;
        let mut u = 0u64;
        for i in 0..n {
            let e = ChunkEnt { off: le64(&dir, i * 0x20), usz: le32(&dir, i * 0x20 + 8), csz: le32(&dir, i * 0x20 + 12) };
            m.ustart.push(u);
            u += e.usz as u64;
            m.ent.push(e);
        }
        Ok(m)
    }

    pub fn ks_end(&self) -> u64 {
        self.size & !7
    }

    pub fn dec(&self, a: u64, n: usize) -> Res<Vec<u8>> {
        if a.checked_add(n as u64).map_or(true, |e| e > self.size) {
            return fail(EXIT_IO, "read past the end of the mod archive");
        }
        let mut buf = vec![0u8; n];
        read_at(&self.f, self.off + a, &mut buf)?;
        xor_keystream(&mut buf, a, self.ks_end());
        Ok(buf)
    }

    pub fn inside(&self, i: usize) -> bool {
        let e = self.ent[i];
        e.off.checked_add(e.csz as u64).map_or(false, |end| end <= self.size)
    }

    pub fn chunk(&self, i: usize) -> Res<Vec<u8>> {
        let e = self.ent[i];
        if !self.inside(i) {
            return fail(EXIT_INTERNAL, format!("chunk {} is not in this data file", i));
        }
        let raw = self.dec(e.off, e.csz as usize)?;
        if e.csz == e.usz {
            return Ok(raw);
        }
        match lz4_decompress(&raw, e.usz as usize) {
            Some(d) => Ok(d),
            None => fail(EXIT_IO, format!("chunk {} of the mod archive is damaged", i)),
        }
    }

    pub fn payload_fnv(&self) -> Res<u64> {
        let mut h = FNV_INIT;
        let mut buf = vec![0u8; 1 << 22];
        let mut pos = 0u64;
        while pos < self.size {
            let n = (self.size - pos).min(buf.len() as u64) as usize;
            read_at(&self.f, self.off + pos, &mut buf[..n])?;
            h = fnv(h, &buf[..n]);
            pos += n as u64;
        }
        Ok(h)
    }

    pub fn file_fnv(&self) -> Res<u64> {
        let mut h = FNV_INIT;
        let mut buf = vec![0u8; 1 << 22];
        let mut pos = 0u64;
        while pos < self.file_size {
            let n = (self.file_size - pos).min(buf.len() as u64) as usize;
            read_at(&self.f, pos, &mut buf[..n])?;
            h = fnv(h, &buf[..n]);
            pos += n as u64;
        }
        Ok(h)
    }
}

impl Source for ModData {
    fn read(&mut self, pos: u64, n: usize) -> Res<Vec<u8>> {
        let mut out = Vec::with_capacity(n);
        while out.len() < n {
            let p = pos + out.len() as u64;
            let i = match self.ustart.partition_point(|&s| s <= p) {
                0 => return fail(EXIT_IO, "read outside the mod archive"),
                k => k - 1,
            };
            if p >= self.ustart[i] + self.ent[i].usz as u64 {
                return fail(EXIT_IO, "read outside the mod archive");
            }
            if self.cached.as_ref().map(|c| c.0) != Some(i) {
                let c = self.chunk(i)?;
                self.cached = Some((i, c));
            }
            let c = &self.cached.as_ref().unwrap().1;
            let a = (p - self.ustart[i]) as usize;
            let take = (c.len() - a).min(n - out.len());
            out.extend_from_slice(&c[a..a + take]);
        }
        Ok(out)
    }
}
