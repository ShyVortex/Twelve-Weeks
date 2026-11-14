"""Minimal SquashFS 4.0 writer (gzip/zlib, no fragments, no xattrs, uid/gid 0), standard library only.

Used by build-linux-pkg.py to make the AppImage's filesystem on Windows (no mksquashfs there). Layout as mksquashfs
writes it: superblock, data blocks, inode table, directory table, (empty) fragment table, id table.

Tree format: a dict  name -> node, where node is
  {'type': 'dir', 'mode': 0o755, 'children': {...}}
  {'type': 'file', 'mode': 0o644, 'data': b'...'}
  {'type': 'symlink', 'target': 'x'}
"""
import struct
import zlib

MAGIC = 0x73717368
META = 8192
NO_FRAGMENTS = 0x0010
NO_XATTRS = 0x0200
INVALID = 0xFFFFFFFFFFFFFFFF
T_DIR, T_FILE, T_SYMLINK = 1, 2, 3


def _compress(data, level):
    c = zlib.compress(data, level)
    return (c, True) if len(c) < len(data) else (data, False)


class _Meta:
    """Metadata stream: 8 KiB blocks, each with a u16 header (bit 15 = stored). pos() = (block start, offset)."""

    def __init__(self, level):
        self.out = bytearray()
        self.buf = bytearray()
        self.level = level

    def pos(self):
        return len(self.out), len(self.buf)

    def write(self, data):
        self.buf += data
        while len(self.buf) >= META:
            self._flush(bytes(self.buf[:META]))
            del self.buf[:META]

    def _flush(self, block):
        c, comp = _compress(block, self.level)
        self.out += struct.pack('<H', len(c) | (0 if comp else 0x8000)) + c

    def finish(self):
        if self.buf:
            self._flush(bytes(self.buf))
            self.buf = bytearray()
        return bytes(self.out)


def build(tree, mtime, block_size=131072, level=9):
    block_log = block_size.bit_length() - 1
    assert 1 << block_log == block_size
    image = bytearray(96)  # superblock written last

    # inode numbers: children before their parent (post-order), root last
    numbers = {}
    counter = [0]

    def number(node):
        if node['type'] == 'dir':
            for name in sorted(node['children'], key=lambda s: s.encode()):
                number(node['children'][name])
        counter[0] += 1
        numbers[id(node)] = counter[0]

    root = {'type': 'dir', 'mode': 0o755, 'children': tree}
    number(root)
    inode_count = counter[0]

    # data blocks for every file (in the order the inodes will be written)
    blocks = {}

    def write_data(node):
        if node['type'] == 'dir':
            for name in sorted(node['children'], key=lambda s: s.encode()):
                write_data(node['children'][name])
        elif node['type'] == 'file':
            data = node['data']
            start = len(image)
            sizes = []
            for i in range(0, len(data), block_size):
                c, comp = _compress(data[i:i + block_size], level)
                image.extend(c)
                sizes.append(len(c) | (0 if comp else 1 << 24))
            if start > 0xFFFFFFFF:
                raise ValueError('image too large for basic file inodes')
            blocks[id(node)] = (start, sizes)

    write_data(root)

    inodes = _Meta(level)
    dirs = _Meta(level)

    def header(itype, mode, num):
        return struct.pack('<HHHHII', itype, mode & 0o7777, 0, 0, mtime, num)

    def emit(node, parent_num):
        """Writes the inode (and for a dir its children + listing); returns (inode ref, basic type)."""
        num = numbers[id(node)]
        t = node['type']
        if t == 'file':
            start, sizes = blocks[id(node)]
            ref = inodes.pos()
            inodes.write(header(T_FILE, node.get('mode', 0o644), num)
                         + struct.pack('<IIII', start, 0xFFFFFFFF, 0, len(node['data']))
                         + struct.pack('<%dI' % len(sizes), *sizes))
            return ref, T_FILE
        if t == 'symlink':
            target = node['target'].encode()
            ref = inodes.pos()
            inodes.write(header(T_SYMLINK, 0o777, num) + struct.pack('<II', 1, len(target)) + target)
            return ref, T_SYMLINK
        # directory: children first
        entries = []
        subdirs = 0
        for name in sorted(node['children'], key=lambda s: s.encode()):
            child = node['children'][name]
            (blk, off), ctype = emit(child, num)
            if ctype == T_DIR:
                subdirs += 1
            entries.append((name.encode(), blk, off, ctype, numbers[id(child)]))
        listing = bytearray()
        i = 0
        while i < len(entries):
            blk, base = entries[i][1], entries[i][4]
            group = []
            while (i < len(entries) and len(group) < 256 and entries[i][1] == blk
                   and -32768 <= entries[i][4] - base <= 32767):
                group.append(entries[i])
                i += 1
            listing += struct.pack('<III', len(group) - 1, blk, base)
            for name, _b, off, ctype, cnum in group:
                listing += struct.pack('<HhHH', off, cnum - base, ctype, len(name) - 1) + name
        dblk, doff = dirs.pos()
        dirs.write(bytes(listing))
        size = len(listing) + 3
        if size > 0xFFFF:
            raise ValueError('directory too large for a basic dir inode')
        ref = inodes.pos()
        inodes.write(header(T_DIR, node.get('mode', 0o755), num)
                     + struct.pack('<IIHHI', dblk, 2 + subdirs, size, doff, parent_num))
        return ref, T_DIR

    (rblk, roff), _ = emit(root, inode_count + 1)
    inode_table = inodes.finish()
    dir_table = dirs.finish()

    inode_start = len(image)
    image += inode_table
    dir_start = len(image)
    image += dir_table
    frag_start = len(image)  # no fragments: an empty table here, like mksquashfs -no-fragments
    idm = _Meta(level)
    idm.write(struct.pack('<I', 0))
    id_block_pos = len(image)
    image += idm.finish()
    id_start = len(image)
    image += struct.pack('<Q', id_block_pos)
    bytes_used = len(image)

    sb = struct.pack('<IIIIIHHHHHHQQQQQQQQ', MAGIC, inode_count, mtime, block_size, 0, 1, block_log,
                     NO_FRAGMENTS | NO_XATTRS, 1, 4, 0, (rblk << 16) | roff, bytes_used, id_start, INVALID,
                     inode_start, dir_start, frag_start, INVALID)
    assert len(sb) == 96
    image[0:96] = sb
    image += b'\0' * (-len(image) % 4096)
    return bytes(image)
