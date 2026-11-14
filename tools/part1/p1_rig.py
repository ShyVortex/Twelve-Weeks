"""Quaternion / FK helpers shared by the Part I animation tools (no dependency on the UC4 proto skeleton).
Quaternions are xyzw (ND layout); a pose row is 12 floats: scale xyz,0 | quat xyzw | trans xyz,0."""
import numpy as np


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw,
                     aw * bw - ax * bx - ay * by - az * bz])


def qinv(q):
    return np.array([-q[0], -q[1], -q[2], q[3]])


def qnorm(q):
    return q / np.linalg.norm(q)


def qrot(q, v):
    x, y, z, w = q
    u = np.array([x, y, z])
    return 2 * np.dot(u, v) * u + (w * w - np.dot(u, u)) * v + 2 * w * np.cross(u, v)


def from_to(a, b):
    """shortest-arc quaternion rotating unit vector a onto unit vector b"""
    c = np.cross(a, b)
    d = float(np.dot(a, b))
    if d < -0.999999:
        ax = np.cross(a, [1.0, 0, 0])
        if np.linalg.norm(ax) < 1e-6:
            ax = np.cross(a, [0, 1.0, 0])
        ax /= np.linalg.norm(ax)
        return np.array([ax[0], ax[1], ax[2], 0.0])
    q = np.array([c[0], c[1], c[2], 1.0 + d])
    return q / np.linalg.norm(q)


def angle_deg(a, b):
    return float(np.degrees(2 * np.arccos(min(1.0, abs(float(np.dot(a, b)))))))


def slerp(a, b, t):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    d = float(np.dot(a, b))
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        return qnorm(a + t * (b - a))
    th = np.arccos(d)
    return (np.sin((1 - t) * th) * a + np.sin(t * th) * b) / np.sin(th)


def fill(rows, bind):
    """rows (n,12) with NaN where a clip did not write -> the bind values there"""
    out = np.array(rows, dtype=np.float64)
    m = np.isnan(out)
    out[m] = np.broadcast_to(bind, out.shape)[m]
    return out


def fk(local, parent):
    """local (n,12) rows (in joint index order, parents first) -> world quats (n,4), world positions (n,3);
    scale is ignored (ND joint scale is used to hide parts, not to size bones)"""
    n = len(local)
    wq = np.zeros((n, 4))
    wp = np.zeros((n, 3))
    for j in range(n):
        p = parent[j]
        q = local[j, 4:8]
        t = local[j, 8:11]
        if p < 0:
            wq[j], wp[j] = qnorm(q), t
        else:
            wq[j] = qnorm(qmul(wq[p], q))
            wp[j] = wp[p] + qrot(wq[p], t)
    return wq, wp


def resample(frames, fps, new_fps):
    """frames (F, ...) of a clip at fps -> (F', ...) at new_fps over the same duration (linear; quaternions are
    renormalised by the caller's encoder path, rows here are already sign-continuous)"""
    F = len(frames)
    if new_fps >= fps or F < 3:
        return frames, fps
    dur = (F - 1) / fps
    n = max(2, int(round(dur * new_fps)) + 1)
    t = np.linspace(0, F - 1, n)
    i0 = np.floor(t).astype(int).clip(0, F - 2)
    w = (t - i0).reshape((-1,) + (1,) * (frames.ndim - 1))
    out = frames[i0] * (1 - w) + frames[i0 + 1] * w
    return out, (n - 1) / dur
