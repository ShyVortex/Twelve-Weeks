import sys
import numpy as np
sys.path.insert(0, './re/uc4ps4/tools')
from t2skel import T2Skel


def quat_to_mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def worlds(path):
    s = T2Skel(path)
    n = s.nj
    W = [None] * n

    def local(i):
        L = np.eye(4)
        if i < s.xform_count:
            b = s.bind[i]
            L[:3, :3] = quat_to_mat(b[4:8]) * b[0:3][None, :]
            L[:3, 3] = b[8:11]
        return L

    def world(i):
        if W[i] is None:
            p = s.parent[i]
            W[i] = local(i) if p < 0 else world(p) @ local(i)
        return W[i]
    sys.setrecursionlimit(5000)
    for i in range(n):
        world(i)
    return s, W


def bind_worlds(path):
    """{joint name: 4x4 model-space bind frame} for EVERY joint, from the skeleton's inverse-bind table (JOINT_HIERARCHY xforms header word 4:
    nj 3x4 row-major float matrices). worlds() chains the local bind transforms, which only exist for the first xform_count joints: helper /
    twist / attach joints (r_twist_*, r_thigh_holster_attach, ...) come out of worlds() in a meaningless space, here they get the frame the
    skinning uses. Checked: equals worlds() to 1 mm on every body joint of the main chain (spine, arms, legs, pelvis, props) of base-male-skel /
    base-female-skel; fingers and face differ (their stored local pose is not the bind pose)."""
    import struct
    s = T2Skel(path)
    p, d = s.p, s.p.d
    io = [x for x in p.items if x[1] == 'JOINT_HIERARCHY'][0][3]
    a = io + 48 + 32
    xo = p.pages[p.fix[a]][0] + struct.unpack_from('<Q', d, a)[0]
    tab = xo + struct.unpack_from('<10I', d, xo + 24)[4]
    out = {}
    for i, n in enumerate(s.names):
        M = np.eye(4)
        M[:3, :] = np.frombuffer(d, np.float32, 12, tab + 48 * i).reshape(3, 4)
        out[n] = np.linalg.inv(M)
    return out


if __name__ == '__main__':
    for f in sys.argv[1:]:
        s, W = worlds(f)
        by = {n: i for i, n in enumerate(s.names)}
        print(f, s.nj, s.xform_count)
        for n in ['pelvis', 'r_thigh', 'r_knee', 'r_leg', 'r_thigh_holster_attach_space', 'r_thigh_holster_attach', 'r_thigh_holster_attach_aim',
                  'r_thigh_holster_attach_up', 'r_thigh_pistol_holster_attach', 'r_leg_holster', 'headb', 'r_hand_prop_attachment', 'r_hand_prop',
                  'one_hand_attach', 'r_backpack_holster_attach', 'lowerback_holster_attach', 'backpack_r_side_holster']:
            if n in by:
                i = by[n]
                print('  %-32s idx %4d parent %-30s pos %s' % (n, i, s.names[s.parent[i]], np.round(W[i][:3, 3], 4)))
                if 'holster' in n:
                    print(np.round(W[i][:3, :3], 3))
