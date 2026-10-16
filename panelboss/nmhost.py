"""nmhost: the app's reader of the companion's native host (the CLIENTS
side of native messaging).

The extension measures the video; the LOCAL host (a stdlib-only exe that
install_host.ps1 builds and registers) writes the app's doorway file. But
the host is ALSO the extension's self-describing API: feed it
{"op":"capabilities"} and it answers with what it can send (the veil op,
its fields, the protocol). This module is how PANELBOSS reads that
answer - the owner's mandate ("we'll make PanelBoss read what the API is
capable of sending") closes HERE, not in a commit line that claims the
card already does capability discovery.

The app does not know where the host exe lives (it is outside the app's
tree); install_host.ps1 writes the chosen path as a one-line json file
%APPDATA%\\PanelBoss\\host.json - a neighbor of the doorway - and this
module reads that. No host.json = no helper installed: the answer is the
honest "not installed" words, never a guess.

The frame codec here is the SAME law as the host's (extension/host/
panelboss_host.py): 4-byte NATIVE-order unsigned length prefix, then
that many UTF-8 json bytes. A wedged or vanished host must never stall
the beat: read-once, kill-on-timeout, and the reply is cached with a TTL
(installation rarely changes, and spawning an exe every beat is the tax
this design was built to avoid).

SIZE LAW (~150): ONE seam - codec, spawn-and-ask, cache. The card's
words live in companion.py; the fold lives in videoeye.py.
"""

import json
import os
import struct
import time

from . import _spawn

# where install_host.ps1 records the host exe path - the doorway's
# neighbor, so it dies and lives with the same app-owned folder.
HOST_JSON = os.path.join(os.environ.get("APPDATA", ""), "PanelBoss",
                         "host.json")

CAP_TIMEOUT = 2.0          # s: a wedged host answers nothing; kill it
                           # and report not-installed rather than stall
CAP_TTL = 300.0            # s: the capabilities answer is cached - the
                           # API surface changes when the host is
                           # reinstalled, not between dimmer beats
NOT_INSTALLED = ("the buddy's helper is not installed - run "
                 "extension\\host\\install_host.ps1")

_cache = {"until": 0.0, "caps": None}


def host_path():
    """The host exe path install_host.ps1 recorded, or None when the
    helper was never installed. A missing file, a junk json, a non-exe
    path all answer None - never an exception, never a camera into the
    app's own folder."""
    try:
        with open(HOST_JSON, encoding="utf-8") as f:
            p = json.load(f).get("path")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(p, str) or not os.path.exists(p):
        return None
    return p


def _ask(exe, *extra):
    """Spawn the host once, ask capabilities, read ONE framed reply.
    Any trouble (a wedged host, a crash, a bad reply) reads as None.
    The browser is not involved here: this is PanelBoss speaking the
    host's wire protocol directly. `extra` lets a suite substitute
    sys.executable + a script twin for the frozen exe. The timeout is
    load-bearing: a wedged host must kill inside CAP_TIMEOUT, never
    stall the dimmer's beat."""
    data = json.dumps({"op": "capabilities"}).encode("utf-8")
    framed = struct.pack("@I", len(data)) + data
    try:
        done = _spawn.run([exe, *extra], input=framed,
                          capture_output=True, timeout=CAP_TIMEOUT)
    except (OSError, _spawn.subprocess.TimeoutExpired):
        return None
    out = done.stdout
    if len(out) < 4:
        return None
    body = out[4:4 + struct.unpack("@I", out[:4])[0]]
    try:
        rep = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return rep if isinstance(rep, dict) else None


def capabilities(now=None, force=False):
    """What the host CAN send, discovered (not assumed): the
    self-description dict, or None when the helper is absent or wedged.
    Cached CAP_TTL seconds; force (the card's explicit re-check, or a
    config save) re-asks. Every failure is None and callers say so -
    this is a probe, not a promise."""
    now = time.monotonic() if now is None else now
    if not force and now < _cache["until"]:
        return _cache["caps"]
    exe = host_path()
    if exe is None:
        _cache.update(until=now + CAP_TTL, caps=None)
        return None
    caps = _ask(exe)
    _cache.update(until=now + CAP_TTL, caps=caps)
    return caps


def veil_fields(caps):
    """The veil op's field list from a capabilities dict, or () - the
    honest empty answer, never a guessed schema."""
    if not isinstance(caps, dict):
        return ()
    veil = caps.get("veil")
    if not isinstance(veil, dict):
        return ()
    f = veil.get("fields")
    return tuple(f) if isinstance(f, (list, tuple)) else ()


def ops(caps):
    """The op list from a capabilities dict, or () - never a guess."""
    if not isinstance(caps, dict):
        return ()
    o = caps.get("ops")
    return tuple(o) if isinstance(o, (list, tuple)) else ()