use std::fmt;
use std::fs::File;
use std::io;

pub const FNV_INIT: u64 = 0xCBF29CE484222325;
const FNV_PRIME: u64 = 0x100000001B3;
pub const DSAR_CHUNK: usize = 0x40000;
pub const LZ4_LEVEL: i32 = 12;

pub const EXIT_IO: i32 = 1;
pub const EXIT_GAME: i32 = 2;
pub const EXIT_INTERNAL: i32 = 3;

#[derive(Debug)]
pub struct Fail {
    pub code: i32,
    pub msg: String,
}

impl fmt::Display for Fail {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.msg)
    }
}

impl From<io::Error> for Fail {
    fn from(e: io::Error) -> Fail {
        Fail { code: EXIT_IO, msg: e.to_string() }
    }
}

pub type Res<T> = Result<T, Fail>;

pub fn fail<T>(code: i32, msg: impl Into<String>) -> Res<T> {
    Err(Fail { code, msg: msg.into() })
}

pub fn io_ctx<T>(r: io::Result<T>, what: impl FnOnce() -> String) -> Res<T> {
    r.map_err(|e| Fail { code: EXIT_IO, msg: format!("{}: {}", what(), e) })
}

pub fn fnv(mut h: u64, p: &[u8]) -> u64 {
    let mut it = p.chunks_exact(8);
    for q in &mut it {
        h = (h ^ u64::from_le_bytes(q.try_into().unwrap())).wrapping_mul(FNV_PRIME);
    }
    for &b in it.remainder() {
        h = (h ^ b as u64).wrapping_mul(FNV_PRIME);
    }
    h
}

pub fn ks_word(i: u64) -> u64 {
    let mut x = i.wrapping_mul(0x9E3779B97F4A7C15).wrapping_add(0xED9AE8F47523C0FB);
    x ^= 0xECBDD9B9C0033EFF;
    x = (x ^ (x >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
    x = (x ^ (x >> 27)).wrapping_mul(0x94D049BB133111EB);
    x ^ (x >> 31)
}

pub fn xor_keystream(buf: &mut [u8], payload_off: u64, ks_end: u64) {
    let mut k = 0usize;
    while k < buf.len() {
        let o = payload_off + k as u64;
        if o >= ks_end {
            break;
        }
        if o % 8 == 0 && k + 8 <= buf.len() && o + 8 <= ks_end {
            let w = ks_word(o >> 3).to_le_bytes();
            for j in 0..8 {
                buf[k + j] ^= w[j];
            }
            k += 8;
        } else {
            buf[k] ^= (ks_word(o >> 3) >> ((o & 7) * 8)) as u8;
            k += 1;
        }
    }
}

#[cfg(windows)]
pub fn read_at(f: &File, mut off: u64, mut buf: &mut [u8]) -> io::Result<()> {
    use std::os::windows::fs::FileExt;
    while !buf.is_empty() {
        let n = f.seek_read(buf, off)?;
        if n == 0 {
            return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "file ends early"));
        }
        off += n as u64;
        buf = &mut buf[n..];
    }
    Ok(())
}

#[cfg(unix)]
pub fn read_at(f: &File, off: u64, buf: &mut [u8]) -> io::Result<()> {
    use std::os::unix::fs::FileExt;
    f.read_exact_at(buf, off)
}

#[cfg(windows)]
pub fn write_at(f: &File, mut off: u64, mut buf: &[u8]) -> io::Result<()> {
    use std::os::windows::fs::FileExt;
    while !buf.is_empty() {
        let n = f.seek_write(buf, off)?;
        if n == 0 {
            return Err(io::Error::new(io::ErrorKind::WriteZero, "write failed"));
        }
        off += n as u64;
        buf = &buf[n..];
    }
    Ok(())
}

#[cfg(unix)]
pub fn write_at(f: &File, off: u64, buf: &[u8]) -> io::Result<()> {
    use std::os::unix::fs::FileExt;
    f.write_all_at(buf, off)
}

pub fn le64(b: &[u8], at: usize) -> u64 {
    u64::from_le_bytes(b[at..at + 8].try_into().unwrap())
}

pub fn le32(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}

pub fn be32(b: &[u8], at: usize) -> u32 {
    u32::from_be_bytes(b[at..at + 4].try_into().unwrap())
}

pub fn be40(b: &[u8], at: usize) -> u64 {
    (b[at] as u64) << 32 | be32(b, at + 1) as u64
}

pub fn lz4_decompress(src: &[u8], usz: usize) -> Option<Vec<u8>> {
    let mut out = vec![0u8; usz];
    let n = unsafe {
        lz4_sys::LZ4_decompress_safe(src.as_ptr() as *const _, out.as_mut_ptr() as *mut _, src.len() as i32, usz as i32)
    };
    if n == usz as i32 {
        Some(out)
    } else {
        None
    }
}

pub fn lz4_compress_chunk(src: &[u8]) -> Option<Vec<u8>> {
    let cap = unsafe { lz4_sys::LZ4_compressBound(src.len() as i32) } as usize + 64;
    let mut dst = vec![0u8; cap];
    let n = unsafe {
        lz4_sys::LZ4_compress_HC(src.as_ptr() as *const _, dst.as_mut_ptr() as *mut _, src.len() as i32, cap as i32, LZ4_LEVEL)
    };
    if n <= 0 {
        return None;
    }
    let n = n as usize;
    if n == src.len() {
        let mut q = Vec::with_capacity(src.len() + 8);
        if src.len() < 15 {
            q.push((src.len() << 4) as u8);
        } else {
            q.push(0xF0);
            let mut rr = src.len() - 15;
            while rr >= 255 {
                q.push(255);
                rr -= 255;
            }
            q.push(rr as u8);
        }
        q.extend_from_slice(src);
        return Some(q);
    }
    dst.truncate(n);
    Some(dst)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fnv_matches_reference_words_and_tail() {
        let t: Vec<u8> = (0..=255u8).cycle().take(256 * 3).chain(b"xyz".iter().copied()).collect();
        let mut h = FNV_INIT;
        for q in t[..t.len() / 8 * 8].chunks(8) {
            h = (h ^ u64::from_le_bytes(q.try_into().unwrap())).wrapping_mul(FNV_PRIME);
        }
        for &b in &t[t.len() / 8 * 8..] {
            h = (h ^ b as u64).wrapping_mul(FNV_PRIME);
        }
        assert_eq!(fnv(FNV_INIT, &t), h);
        let (a, b) = t.split_at(256);
        assert_eq!(fnv(fnv(FNV_INIT, a), b), h);
    }

    #[test]
    fn keystream_is_symmetric_and_offset_aware() {
        let plain: Vec<u8> = (0..100u8).collect();
        for off in [0u64, 3, 8, 13] {
            let mut a = plain.clone();
            xor_keystream(&mut a, off, 1 << 40);
            let mut slow = plain.clone();
            for (k, b) in slow.iter_mut().enumerate() {
                let o = off + k as u64;
                *b ^= (ks_word(o >> 3) >> ((o & 7) * 8)) as u8;
            }
            assert_eq!(a, slow);
            xor_keystream(&mut a, off, 1 << 40);
            assert_eq!(a, plain);
        }
        let mut c = plain.clone();
        xor_keystream(&mut c, 0, 16);
        assert_eq!(&c[16..], &plain[16..]);
    }

    #[test]
    fn lz4_round_trip_and_literal_fallback() {
        let text = b"the quick brown fox jumps over the lazy dog ".repeat(7000);
        let c = lz4_compress_chunk(&text[..DSAR_CHUNK]).unwrap();
        assert!(c.len() < DSAR_CHUNK);
        assert_eq!(lz4_decompress(&c, DSAR_CHUNK).unwrap(), &text[..DSAR_CHUNK]);
        let mut x: u64 = 7;
        let rnd: Vec<u8> = (0..1000).map(|_| { x = ks_word(x); x as u8 }).collect();
        let c = lz4_compress_chunk(&rnd).unwrap();
        assert_ne!(c.len(), rnd.len());
        assert_eq!(lz4_decompress(&c, rnd.len()).unwrap(), rnd);
    }
}
