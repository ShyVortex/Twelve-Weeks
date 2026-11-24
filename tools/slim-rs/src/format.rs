use crate::util::*;

pub const MAGIC: &[u8; 8] = b"T2SLIM03";
pub const HEAD_SIZE: usize = 128;
pub const REC_SIZE: usize = 256;
pub const CHUNK_SIZE: usize = 16;
pub const LIT_SIZE: usize = 24;
pub const ARCH_MAX: usize = 48;
pub const PATH_MAX: usize = 128;

pub const KIND_GAME: u32 = 0;
pub const KIND_PACK: u32 = 1;

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Head {
    pub blob_off: u64,
    pub blob_size: u64,
    pub blob_fnv: u64,
    pub out_size: u64,
    pub out_fnv: u64,
    pub nrec: u32,
    pub nchunks: u32,
    pub nlit: u32,
    pub pack_off: u64,
    pub pack_len: u64,
    pub pack_usz: u64,
    pub build_id: [u8; 16],
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Rec {
    pub kind: u32,
    pub base_size: u64,
    pub usz: u64,
    pub delta_off: u64,
    pub delta_len: u64,
    pub raw_fnv: u64,
    pub chunk0: u32,
    pub nchunks: u32,
    pub pack_pos: u64,
    pub md5: [u8; 16],
    pub arch: String,
    pub path: String,
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Chunk {
    pub payload_off: u64,
    pub usz: u32,
    pub csz: u32,
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Lit {
    pub out_off: u64,
    pub len: u64,
    pub dat_off: u64,
}

fn put_str(b: &mut Vec<u8>, s: &str, n: usize) {
    let mut f = s.as_bytes().to_vec();
    f.resize(n, 0);
    b.extend_from_slice(&f);
}

fn get_str(b: &[u8]) -> String {
    let end = b.iter().position(|&c| c == 0).unwrap_or(b.len());
    String::from_utf8_lossy(&b[..end]).into_owned()
}

impl Head {
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut b = Vec::with_capacity(HEAD_SIZE);
        b.extend_from_slice(MAGIC);
        for v in [self.blob_off, self.blob_size, self.blob_fnv, self.out_size, self.out_fnv] {
            b.extend_from_slice(&v.to_le_bytes());
        }
        for v in [self.nrec, self.nchunks, self.nlit, 0] {
            b.extend_from_slice(&v.to_le_bytes());
        }
        for v in [self.pack_off, self.pack_len, self.pack_usz] {
            b.extend_from_slice(&v.to_le_bytes());
        }
        b.extend_from_slice(&self.build_id);
        b.resize(HEAD_SIZE, 0);
        b
    }

    pub fn from_bytes(b: &[u8]) -> Res<Head> {
        if b.len() < HEAD_SIZE || &b[..8] != MAGIC {
            return fail(EXIT_IO, "not a slim data file of this version (T2SLIM03)");
        }
        Ok(Head {
            blob_off: le64(b, 8),
            blob_size: le64(b, 16),
            blob_fnv: le64(b, 24),
            out_size: le64(b, 32),
            out_fnv: le64(b, 40),
            nrec: le32(b, 48),
            nchunks: le32(b, 52),
            nlit: le32(b, 56),
            pack_off: le64(b, 64),
            pack_len: le64(b, 72),
            pack_usz: le64(b, 80),
            build_id: b[88..104].try_into().unwrap(),
        })
    }
}

impl Rec {
    pub fn to_bytes(&self) -> Res<Vec<u8>> {
        if self.arch.len() >= ARCH_MAX || self.path.len() >= PATH_MAX {
            return fail(EXIT_INTERNAL, format!("name too long for the slim format: {} / {}", self.arch, self.path));
        }
        let mut b = Vec::with_capacity(REC_SIZE);
        b.extend_from_slice(&self.kind.to_le_bytes());
        b.extend_from_slice(&0u32.to_le_bytes());
        for v in [self.base_size, self.usz, self.delta_off, self.delta_len, self.raw_fnv] {
            b.extend_from_slice(&v.to_le_bytes());
        }
        b.extend_from_slice(&self.chunk0.to_le_bytes());
        b.extend_from_slice(&self.nchunks.to_le_bytes());
        b.extend_from_slice(&self.pack_pos.to_le_bytes());
        b.extend_from_slice(&self.md5);
        put_str(&mut b, &self.arch, ARCH_MAX);
        put_str(&mut b, &self.path, PATH_MAX);
        debug_assert_eq!(b.len(), REC_SIZE);
        Ok(b)
    }

    pub fn from_bytes(b: &[u8]) -> Rec {
        Rec {
            kind: le32(b, 0),
            base_size: le64(b, 8),
            usz: le64(b, 16),
            delta_off: le64(b, 24),
            delta_len: le64(b, 32),
            raw_fnv: le64(b, 40),
            chunk0: le32(b, 48),
            nchunks: le32(b, 52),
            pack_pos: le64(b, 56),
            md5: b[64..80].try_into().unwrap(),
            arch: get_str(&b[80..80 + ARCH_MAX]),
            path: get_str(&b[80 + ARCH_MAX..80 + ARCH_MAX + PATH_MAX]),
        }
    }
}

impl Chunk {
    pub fn to_bytes(&self) -> [u8; CHUNK_SIZE] {
        let mut b = [0u8; CHUNK_SIZE];
        b[..8].copy_from_slice(&self.payload_off.to_le_bytes());
        b[8..12].copy_from_slice(&self.usz.to_le_bytes());
        b[12..16].copy_from_slice(&self.csz.to_le_bytes());
        b
    }

    pub fn from_bytes(b: &[u8]) -> Chunk {
        Chunk { payload_off: le64(b, 0), usz: le32(b, 8), csz: le32(b, 12) }
    }
}

impl Lit {
    pub fn to_bytes(&self) -> [u8; LIT_SIZE] {
        let mut b = [0u8; LIT_SIZE];
        b[..8].copy_from_slice(&self.out_off.to_le_bytes());
        b[8..16].copy_from_slice(&self.len.to_le_bytes());
        b[16..24].copy_from_slice(&self.dat_off.to_le_bytes());
        b
    }

    pub fn from_bytes(b: &[u8]) -> Lit {
        Lit { out_off: le64(b, 0), len: le64(b, 8), dat_off: le64(b, 16) }
    }
}

pub fn literal_ranges(zeroed: &[(u64, u64)], size: u64) -> Vec<(u64, u64)> {
    let mut z = zeroed.to_vec();
    z.sort_unstable();
    let mut out = Vec::new();
    let mut pos = 0u64;
    for (a, n) in z {
        if a > pos {
            out.push((pos, a - pos));
        }
        pos = pos.max(a + n);
    }
    if pos < size {
        out.push((pos, size - pos));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn head_and_records_round_trip() {
        let h = Head { blob_off: 0x10000, blob_size: 5, blob_fnv: 6, out_size: 7, out_fnv: 8, nrec: 1, nchunks: 2, nlit: 3, pack_off: 9, pack_len: 10, pack_usz: 11, build_id: [7; 16] };
        let b = h.to_bytes();
        assert_eq!(b.len(), HEAD_SIZE);
        assert_eq!(Head::from_bytes(&b).unwrap(), h);
        let r = Rec { kind: 1, base_size: 2, usz: 3, delta_off: 4, delta_len: 5, raw_fnv: 6, chunk0: 7, nchunks: 8, pack_pos: 9, md5: [3; 16], arch: "common.psarc".into(), path: "actor97/x.pak".into() };
        let rb = r.to_bytes().unwrap();
        assert_eq!(rb.len(), REC_SIZE);
        assert_eq!(Rec::from_bytes(&rb), r);
        let long = Rec { path: "p".repeat(PATH_MAX), ..r };
        assert!(long.to_bytes().is_err());
        let c = Chunk { payload_off: 1 << 40, usz: 3, csz: 2 };
        assert_eq!(Chunk::from_bytes(&c.to_bytes()), c);
        let l = Lit { out_off: 1, len: 2, dat_off: 3 };
        assert_eq!(Lit::from_bytes(&l.to_bytes()), l);
        assert!(Head::from_bytes(b"T2SLIM02xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx").is_err());
    }

    #[test]
    fn literals_fill_the_gaps() {
        assert_eq!(literal_ranges(&[(10, 5), (0, 2), (20, 30)], 60), vec![(2, 8), (15, 5), (50, 10)]);
        assert_eq!(literal_ranges(&[(0, 60)], 60), vec![]);
        assert_eq!(literal_ranges(&[], 4), vec![(0, 4)]);
        assert_eq!(literal_ranges(&[(5, 10), (5, 10), (8, 3)], 20), vec![(0, 5), (15, 5)]);
    }
}
