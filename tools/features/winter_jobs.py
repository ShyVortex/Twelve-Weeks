"""Job functions for tools/parjobs.py: the independent winter-part builders of build_dll.stage_crew_winter (each writes its own paks)."""
import os
import sys

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TOOLS, "models"))


def crew(out_dir, name):
    import crew_winter
    rep = {}
    crew_winter.build(out_dir, [name], rep)
    return rep


def mask(out_dir, group):
    import scar_mask
    rep = {}
    scar_mask.build(out_dir, report=rep, group=group)
    return rep


def gear(out_dir):
    import winter_gear
    rep = {}
    winter_gear.build(out_dir, report=rep)
    return rep


def snow_build(data, g, donor, donor_pak, mask):
    """mp_snow_pak.build in a child interpreter (CPU-bound python: the snow masks) -> ("ok", data, report) or (kind, text) for the exceptions the callers handle"""
    import mp_snow_pak
    rep = {}
    try:
        return ("ok", mp_snow_pak.build(data, g, donor=donor, report=rep, donor_pak=donor_pak, mask=mask), rep)
    except mp_snow_pak.CliFailed as e:
        return ("cli", str(e))
    except SystemExit as e:
        return ("exit", str(e.code) if e.code is not None else "")
    except StopIteration:
        return ("stop", "")
    except KeyError as e:
        return ("key", e.args[0] if e.args else "")
