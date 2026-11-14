"""Voice pools of the clan selection (to1/clan-side): lines said (native `say`) when a faction is hovered / highlighted. (kind, n) = vox_lines.json entries
(the registered t2r-vox-* records, VX_LINES in tools/ext/vox_lines.h). The same tables sit in t2r-ext.c (SIDE_VOX_*); keep them in step."""
SER = [("introrsp", 1), ("introrsp", 2), ("introrsp", 6), ("introrsp", 8), ("introrsp", 9), ("introrsp", 12), ("introrsp", 13),
       ("xstmt", 3), ("xstmt", 8), ("xstmt", 10), ("introrsp", 3)]
WLF = [("introrsp", 1), ("introrsp", 2), ("introrsp", 3), ("introrsp", 4), ("introrsp", 5), ("introrsp", 8), ("introrsp", 11),
       ("xcomm", 6), ("xcomm", 7), ("intro", 4)]
# shipped by default (the rest are only exported for pruning): without 'Hesitation is death.' and the profane 'Let's lock this shit down.'
DEFAULT_SER = [("introrsp", 1), ("introrsp", 2), ("introrsp", 6), ("introrsp", 8), ("introrsp", 9), ("introrsp", 12), ("xstmt", 3), ("xstmt", 8), ("xstmt", 10), ("introrsp", 3)]
DEFAULT_WLF = [("introrsp", 1), ("introrsp", 2), ("introrsp", 4), ("introrsp", 5), ("introrsp", 8), ("introrsp", 11), ("xcomm", 6), ("xcomm", 7), ("intro", 4)]
