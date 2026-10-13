"""Camera identity, the data layer (redesign stage 3): the wizard died
so the curation could have ONE path - its functions survive here,
importable and testable without a display.

Identity is the PnP InstanceId (camera.camera_devices): indexes drift
on replugs, so labels, hides, shows, and BINDINGS ride the instance
path. A device's CURRENT index resolves in precedence order: the
owner's bind (camera.bindings - a human assertion that evicts
guesses), the unique name join (identity_map), then the relaxed
preview fallback (preview_map: one shared-name feed lights every
twin, confessed). Unclaimed open indexes still walk as synthetic
idx:N rows (all_rows) so every feed the picker shows has an identity
the owner can name - and every such row is itself a bind candidate
for the twin case.

The diagnostic verdict rides display_names' neighbors, not its ladder
(diag_suffix): a noimg index says so wherever its camera is captioned,
and the wizard-era pre-mark (all_rows) still steers the setup screen's
hide checkboxes through the stickiness law - labels, bindings, and
shown veto the sweep's hiding, forever.

SIZE LAW: measured 257 (Oct 13) - a lean pure-data module, the
survivors of the 953-line wizard (its widget shell died with the
redesign; the setup screen _assign.py carries the UI now, and this
file carries the truth the setup screen, the picker, and the duty
cards all read the same way from).
"""

import logging

from ... import camera

log = logging.getLogger("ui")

DUP = ("two identical models share this name: the app cannot tell them "
       "apart. Wave at one camera and bind the device to the feed that "
       "moves - the bind is stored on the device, replugs and all.")


def identity_map(devs, found, bindings=None):
    """{instance: index}. The human answer FIRST of all: camera.bindings
    (the wizard's "this device is that feed") is applied LAST over the
    name join and EVICTS a guess standing on the same index - a bind
    whose instance is not in the PnP rows maps nothing (unplugged: the
    claim waits in the toml, exactly like a hidden instance waits).
    With no bind, a device maps only when its friendly name appears
    EXACTLY once in the PnP list and one scanned entry carries that
    name - uniqueness is the fallback clue; identical models now have
    the bind as their way, replacing the unplug-and-rerun dance."""
    hits = {}
    present = set()
    for d in devs or []:
        present.add(str(d["instance"]))
        hits.setdefault(str(d["name"]).lower(), []).append(d["instance"])
    out = {}
    for entry in found or []:
        got = hits.get(str(entry[3] or "").lower(), [])
        if len(got) == 1:
            out[got[0]] = entry[0]
    for inst, idx in (bindings or {}).items():
        try:                            # hand-edited toml is input
            idx = int(idx)              # like every other value here
        except (TypeError, ValueError):
            continue
        if str(inst) in present:
            for guess, gidx in list(out.items()):
                if gidx == idx and guess != str(inst):
                    del out[guess]      # the human evicts the guess
            out[str(inst)] = idx
    return out


def display_names(devs, found, cfg_camera):
    """index -> the name the UI may show. The owner's law: a name
    chosen in the wizard must reach EVERY pane for THAT CAMERA - a
    label resolves through any identity that legitimately points at
    the index (BIND first, honest unique-name join second, then the
    "idx:N" key the synthetic rows are named by - the bind handler
    migrates those to the instance), the scan's positional guess
    fills the rest, and a label of an identity that claims nothing
    shows nowhere: NEVER a borrowed name. The panes that caption
    cameras call this instead of trusting entry[3]."""
    ids = identity_map(devs, found, (cfg_camera or {}).get("bindings") or {})
    labels = (cfg_camera or {}).get("labels") or {}
    out = {idx: str(labels.get(inst, "") or "") for inst, idx in ids.items()}
    # a label keyed on "idx:N" is the identity a synthetic row was
    # named by (pre-bind, or an unmappable filter): it belongs to that
    # index no matter what the name join says, and the bind handler
    # MIGRATES it to the instance when a real identity arrives
    for key, text in labels.items():
        k = str(key)
        if k.startswith("idx:") and k[4:].lstrip("-").isdigit():
            n = int(k[4:])
            if str(text or "").strip() and not out.get(n):
                out[n] = str(text).strip()
    for entry in found or []:
        got = out.setdefault(entry[0], "")
        if not got and len(entry) > 3 and entry[3]:
            out[entry[0]] = str(entry[3])        # positional fallback:
    return out                                   # better than nothing,
                                                 # never more than truth


def diag_suffix(cfg_camera, index):
    """The sweep's verdict as a picker/duty-card line suffix: ONE
    static for both panes (feature law 3). Membership only - the
    record is rewritten whole by the state loop at every sweep, so a
    present noimg list is by construction the current truth about
    THESE indexes; the call sites add the coverage gate (the record
    must have measured this exact scan) so a verdict of an older set
    never speaks for a camera it never probed."""
    d = (cfg_camera or {}).get("diag") or {}
    return " (no image during diagnostic)" \
        if index in (d.get("noimg") or []) else ""


def bind_candidates(devs, found, bindings=None):
    """Open scanned indexes no identity claims (bind or join): the
    feeds only a human eye can assign - the wizard offers exactly
    these to "bind this device to a feed"."""
    owned = set(identity_map(devs, found, bindings).values())
    return [entry[0] for entry in found or []
            if len(entry) > 1 and entry[1] and entry[0] not in owned]


def preview_map(devs, found):
    """{instance: (index, shared)}: identity_map's pessimism RELAXED
    for the wizard's live view only. When a name is carried by several
    PnP rows but exactly ONE scanned index answers to it (the common
    shape: a twin-sensor module where only the color stream ever
    opens), that feed shows for every twin and the step line confesses
    the twins are indistinguishable. The picker and hidden filter keep
    the strict map - there a guess HIDES the wrong device, here it
    only lights the wrong preview, and the user sees which it is.
    Two+ indexes for one name: ordinal order is a coin flip, nothing
    maps (the UAT gap this closes: identical models made a streaming
    physical cam untestable in the wizard)."""
    rows = {}
    for d in devs:
        rows.setdefault(d["name"].lower(), []).append(d["instance"])
    idxs = {}
    for entry in found or []:
        idxs.setdefault(str(entry[3] or "").lower(), []).append(entry[0])
    out = {}
    for name, insts in rows.items():
        got = idxs.get(name, [])
        if len(got) == 1:
            for inst in insts:
                out[inst] = (got[0], len(insts) > 1)
    return out


def all_rows(devs, found, cfg_camera=None):
    """PnP rows + a synthetic row per OPEN scanned index that no PnP
    row claimed: the wizard walks what the picker shows (the owner's
    UAT law - identify gives the add pane its names and hides, so it
    must see EVERYTHING the add pane can open). A claimed index is one
    identity_map or preview_map resolved; the synthetic remainder keys
    policy on "idx:N" - drifts on replug renumbering, the honest
    documented twin of the unplug-and-rerun pattern for identical
    models. The DSHOW/MF ordinal->instance oracle that would name
    these properly lives in panelboss/dshow.py's ledger note: this
    box registers no SystemDeviceEnum class (cv2 carries its own), so
    until the enumeration route is cracked, synthetic rows are the
    truthful stand-in - preview works, labels persist, no positional
    name lie rides them.

    cfg_camera is the whole camera config dict (amendment 2: ONE
    argument, not a param per table - the pre-mark below reads diag,
    labels, bindings, and shown, and every caller already holds
    app.cfg["camera"]). The sweep's no-image verdict PRE-MARKS the
    synthetic rows it measured dark (feature law 3): a sometimes-
    plugged camera the owner named, bound, or showed (camera.shown)
    is human-touched by ANY of the three, and the stickiness law says
    the sweep can then only INFORM - its verdict never re-hides what
    a hand wrote, forever."""
    cfg_camera = cfg_camera or {}
    bindings = cfg_camera.get("bindings") or {}
    ids = identity_map(devs, found, bindings)
    mapped = set(ids.values())
    mapped |= {got[0] for got in preview_map(devs, found).values()}
    try:
        from ... import dshow              # the ordinal oracle: {} on a
        truth = dshow.index_instances()    # box without the registered
    except Exception:                      # SystemDeviceEnum class
        truth = {}                         # (the dev desk today)
    rows = [dict(d) for d in (devs or [])]   # copies: the idx attach
    for row in rows:                          # below must not leak
        idx = ids.get(row["instance"])        # back into _devs
        if idx is not None:
            row["idx"] = idx
    for entry in found or []:
        if len(entry) < 2 or not entry[1] or entry[0] in mapped:
            continue
        nm = str(entry[3]).strip() if len(entry) > 3 and entry[3] else ""
        inst = truth.get(entry[0])
        rows.append({"name": nm or ("camera %d" % entry[0]),
                     "instance": inst or ("idx:%d" % entry[0]),
                     "status": "OK",
                     # UNKNOWN is not SOFTWARE: only a resolved
                     # non-USB instance may hide a synthetic row by
                     # default; an unresolved one shows, previews and
                     # waits for the owner's verdict (that IS the
                     # wizard's job)
                     "virtual": bool(inst) and camera.is_virtual_camera(inst),
                     "idx": entry[0]})
    # the hello IR sensors: glass behind a driver flag, invisible to
    # the class-Camera query AND to cv2's scan space - without these
    # rows the owner could never NAME the IR cameras the picker lists
    # (they showed in the picker but "not in identify at all": true by
    # construction). Identity keys on "ir:<group name>" - stable as
    # the bridge reports it, no index to drift; the preview opens the
    # named group through the same Camera-compatible adapter the duty
    # engine uses.
    if camera.optional_present("whircam"):
        for g in camera.hello_ir_names():
            rows.append({"name": g, "instance": "ir:" + g,
                         "status": "OK", "virtual": False,
                         "idx": camera.HELLO_IR, "ir": g})
    # the diagnostic pre-mark (feature law 3), AFTER the synthetic rows
    # stand: a measured-dark index hides its SYNTHETIC row behind the
    # show-virtual checkbox (the sweep could not name the feed, only
    # time it - a bound/known instance keeps its namespace verdict,
    # and a human touch (label, bind, or a one-at-a-time show: the
    # stickiness law, amendment 2) outranks the sweep permanently -
    # the verdict rides the picker line's suffix either way, so dark
    # stays VISIBLE to the eye that decides
    noimg = (cfg_camera.get("diag") or {}).get("noimg") or []
    touched = (set(cfg_camera.get("labels") or {})
               | set(bindings)
               | set(cfg_camera.get("shown") or []))
    for row in rows:
        if (str(row["instance"]).startswith("idx:")
                and row.get("idx") in noimg
                and row["instance"] not in touched):
            row["virtual"] = True
    return rows


def hidden_indices(devs, found, hidden, bindings=None):
    """Scan indexes to suppress in the picker and menu lines. An
    unmappable hidden device suppresses nothing - it stays visible
    here, so the wizard remains its way out. The "idx:N" synthetic
    keys (all_rows) hide by index directly: that IS their whole
    identity claim."""
    hidden = list(hidden or [])
    out = {int(str(i)[4:]) for i in hidden
           if str(i).startswith("idx:") and str(i)[4:].isdigit()}
    out |= {idx for inst, idx in identity_map(devs, found, bindings).items()
            if inst in set(hidden)}
    return out


def step_warning(devs, dev):
    return DUP if sum(1 for d in devs if d["name"] == dev["name"]) > 1 \
        else ""

