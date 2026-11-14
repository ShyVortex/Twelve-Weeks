"""Widget guids for the generated widget layouts (gui2-widgets.pak): 32 hex chars like uuid4().hex, but deterministic - the n-th guid
requested in a process is always the same, so two builds of the same inputs give byte-identical paks (they used to differ by
random guids only; that also made a cached build unprovable against an uncached one)."""
import hashlib
import itertools

_counter = itertools.count()


def guid():
    return hashlib.md5(b"t2r-widget-guid-%d" % next(_counter)).hexdigest()
