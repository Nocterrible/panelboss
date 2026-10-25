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

SIZE LAW (~230): ONE seam - codec, spawn-and-ask, cache, and install.
The install seam (install, Oct 16) is the app-side one-click on top of
the SAME script the README documents - extension\\host\\install_host.
ps1: the id law is derived here (derive_unpacked_id, the browser's
unpacked-extension derivation), PATH is prepended with the venv's dir
so the installer's `python` is the venv's (PyInstaller 6.22.3 lives
there), the installer's stdout lands in a scratch file (the owner's
shell law: bulk noise never rides the UI line), and the result is
re-probed with capabilities(force=True) - the success word IS the
fresh host's own reply, the probe being the proof-of-install. The
card's words live in companion.py; the fold lives in videoeye.py.
"""

import base64
import hashlib
import json
import os
import re
import struct
import sys
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
NOT_INSTALLED = ("the companion's helper is not installed - press install "
                 "the helper above")

# the installer the card's one-click runs - a module constant so a
# suite can stand a .ps1 twin in its own temp dir (the seam is the
# SPAWN: the fake twin runs through the real subprocess call).
# FROZEN AWARE (MSI gate, Oct 25, blocker 3): a frozen PyInstaller
# build rewrites __file__ into _internal, so __file__-relative
# resolution would look INSIDE the bundle's private half - while the
# build ships the host folder BESIDE the exe (dist\PanelBoss\
# extension\host\, the same user-visible convention as the models
# drop, inference.py). Exe-adjacent first when frozen and the folder
# is there; the repo layout otherwise - so the "install the helper"
# button finds its installer on BOTH install kinds.
def _app_root():
    if getattr(sys, "frozen", False):
        cand = os.path.dirname(sys.executable)
        if os.path.isdir(os.path.join(cand, "extension")):
            return cand
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_APP_ROOT = _app_root()

_INSTALL_PS1 = os.path.join(_APP_ROOT, "extension", "host",
                            "install_host.ps1")

_cache = {"until": 0.0, "caps": None}

# the browser's unpacked-extension id is a derivation over the LOAD
# PATH, not an invention: the path as the browser normalizes it (drive
# letter UPPERCASE, backslashes, UTF-8), SHA-256, the first 16 bytes
# mapped nibble-by-nibble into the a-p alphabet. Stable per location -
# which is what the manifest's allowed_origins needs; move the load
# path and the browser re-derives, and so do we.
EXT_ID_RE = re.compile(r"^[a-p]{32}$")


def derive_unpacked_id(ext_dir):
    """The browser's extension id for the folder `ext_dir`, or None when
    the dir cannot be normalized. THE FULL CHROMIUM LAW HAS TWO BRANCHES
    (learned Oct 16, when the keypair was generated for the store
    submission): if manifest.json carries "key" (base64 DER of the
    SubjectPublicKeyInfo), the id derives from THOSE BYTES - sha256 of
    the decoded DER, first 16 bytes, nibble-mapped a-p - which is what
    makes the id survive folder moves, machines, and the store itself.
    Only WITHOUT a key does the browser fall back to the PATH law: the
    absolute path string as loaded, UTF-8 bytes (abspath - which
    absolutizes and collapses but never case-folds: the on-disk spelling
    IS the load spelling; move the load path and the browser re-derives,
    and so do we - until a key pins it). The pinned manifest now carries
    the key, so this folder's id is the key-branch value:

        ->  feolhiokchmpphlhllagimnilceldegk   (permanent, companion_key.txt)

    Path-branch vectors, kept as the documented fallback behavior:

        sha256(os.path.abspath("F:\\Projects\\panelboss-reskin\\extension")
               .encode("utf-8"))[:16]  ->  jagfnepkfnioappmbloibkcjofhgaaai
        sha256(os.path.abspath("F:\\workspace").encode("utf-8"))[:16]
                                     ->  jeafefjdigahcngkajpclimdpjjamadc
    """
    key_id = derive_key_id(ext_dir)
    if key_id is not None:
        return key_id
    p = os.path.abspath((ext_dir or "").strip())
    if not p or p == os.path.abspath(os.curdir):
        return None
    p = p[0].upper() + p[1:]          # the law's drive letter: UPPERCASE
                                       # (the on-disk spelling is already
                                       # the load spelling; the letter is
                                       # the one byte the browser fixes)
    digest = hashlib.sha256(p.encode("utf-8")).digest()[:16]
    return "".join(chr(ord("a") + (b >> 4)) + chr(ord("a") + (b & 0xF))
                   for b in digest)


def derive_key_id(ext_dir):
    """The KEY BRANCH of the id law (see derive_unpacked_id): read
    manifest.json's "key", base64-decode to the SPKI DER, derive the id
    from THOSE BYTES. Any failure (no manifest, no key, bad base64, bad
    json) answers None = the path branch applies, exactly the browser's
    own fallthrough. Never raises."""
    try:
        if not (ext_dir or "").strip():
            return None      # never probe the cwd for a stray manifest
        with open(os.path.join(os.path.abspath(ext_dir),
                               "manifest.json"), encoding="utf-8") as f:
            key = json.load(f).get("key")
        if not isinstance(key, str):
            return None
        der = base64.b64decode(key, validate=True)
    except Exception:
        return None
    digest = hashlib.sha256(der).digest()[:16]
    return "".join(chr(ord("a") + (b >> 4)) + chr(ord("a") + (b & 0xF))
                   for b in digest)


def host_path():
    """The host exe path install_host.ps1 recorded, or None when the
    helper was never installed. A missing file, a junk json, a non-exe
    path all answer None - never an exception, never a camera into the
    app's own folder."""
    try:
        # utf-8-sig, not utf-8: install_host.ps1 writes this file with
        # Windows PowerShell's Set-Content -Encoding UTF8, which EMITS
        # A BOM (measured: EF BB BF), and json.load rejects the BOM -
        # the freshly-installed user would read "not installed"
        # forever, the silent-death class this design exists to kill
        # (2nd-pass gate, finding 1, HIGH: producer/consumer gap the
        # suite could not see - its fake host.json is Python-written,
        # no BOM; the pin that proves the fix writes one).
        with open(HOST_JSON, encoding="utf-8-sig") as f:
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


def install(ext_id=None):
    """One-click helper install: run extension\\host\\install_host.ps1
    (the SAME script the README documents - this call adds the app's
    convenience, not a second installer), then re-probe so the
    caller can answer with the fresh host's own reply.

    Id resolution: `ext_id` when given - and anything that is not the
    browser's 32-char a-p id refuses BEFORE a single process starts -
    else derived from the on-disk extension dir (derive_unpacked_id;
    the load path here is the extension's own home). A dir that cannot
    be normalized answers a word, never a spawn.

    The venv's python must be the installer's `python` (PyInstaller
    6.22.3 lives in the venv): PATH is PREPENDED with
    os.path.dirname(sys.executable). The installer's stdout (and
    stderr) is captured into a scratch file, never the UI string; the
    failure words quote the installer's OWN line (at most one) and
    name the step it names - id/build/register/write - so a user can
    tell WHICH of build, register, or write refused without opening
    the scratch file.

    Answers (bool, words). True + the fresh host's capabilities line -
    the PROBE IS THE PROOF-OF-INSTALL (the cache is reset and the
    fresh host is re-asked; a host that answers nothing reads as a
    failure, not a victory). False + the refusing step + the manual
    route (the ps1 path stays the documented one-line-down manual)."""
    if ext_id is not None:
        ext_id = str(ext_id).strip()
    if ext_id:
        if not EXT_ID_RE.match(ext_id):
            return False, ("bad extension id - it must be 32 lowercase "
                           "a-p chars (the browser's extensions page)")
    else:
        ext_dir = os.path.join(_APP_ROOT, "extension")
        ext_id = derive_unpacked_id(ext_dir)
        if not ext_id:
            return False, ("could not derive the extension id from the "
                           "on-disk extension dir")
    ps1 = _INSTALL_PS1
    if not os.path.exists(ps1):
        return False, "the installer is not here: %s" % ps1
    scratch = os.path.join(
        os.environ.get("TEMP") or os.environ.get("TMP") or ".",
        "panelboss-helper-install.log")
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + \
        env.get("PATH", "")
    try:
        done = _spawn.run(["powershell", "-NoProfile", "-ExecutionPolicy",
                           "Bypass", "-File", ps1, "-ExtensionId",
                           ext_id, "-Rebuild"],
                          env=env, capture_output=True, text=True,
                          timeout=300)
    except _spawn.subprocess.TimeoutExpired:
        return False, ("the install timed out (PyInstaller takes ~40 s; "
                       "the cap is 5 min) - or run extension\\host\\"
                       "install_host.ps1 -ExtensionId %s yourself"
                       % ext_id)
    # the installer's bulk never rides the UI string - it lands in the
    # scratch file for the owner to read (the shell law); the words
    # quote at most ONE line of it.
    try:
        with open(scratch, "w", encoding="utf-8") as f:
            f.write((done.stdout or "") + (done.stderr or ""))
    except OSError:
        pass
    if done.returncode != 0:
        tail = _stdout_tail((done.stdout or "") + (done.stderr or ""))
        step = _refusing_step(tail)
        return False, "%s refused: %s - or run " \
                      "extension\\host\\install_host.ps1 -ExtensionId " \
                      "%s yourself" % (step, tail, ext_id)
    # the fresh host's own reply is the proof-of-install: the cache is
    # reset so THIS ask is the new host, not the one installed an hour
    # ago (the TTL would otherwise answer the stale answer).
    _cache.update(until=0.0, caps=None)
    caps = capabilities(force=True)
    if caps is None:
        # The onefile host EXE unpacks to temp on its first launch
        # (and AV may inspect that unpack): the proof-of-install probe
        # can legitimately miss a healthy host exactly once, exactly
        # at THIS moment - the gate's finding 1 (Oct 16). One pause,
        # one re-ask, before we blame a binary that is fine.
        time.sleep(1.0)
        caps = capabilities(force=True)
    if caps is None:
        return False, ("the installer reported success but the fresh "
                       "host answers no capabilities - or run "
                       "extension\\host\\install_host.ps1 -ExtensionId "
                       "%s yourself" % ext_id)
    return True, "helper installed - " + _caps_line(caps)


def _stdout_tail(out):
    """The last quotable line of an installer's stdout, or one honest
    word when it printed nothing."""
    lines = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "the installer said nothing"


def _refusing_step(tail):
    """The step the installer's OWN line names - id, build, register,
    write - so the words tell the user WHICH of build, register, or
    write refused. The ps1's lines: the bad-id line, 'host build
    failed', the host.json write, the register (any of them dying
    surfaces as a Write-Output of its own error, which is what these
    keywords quote). An un-named failure answers the honest generic -
    never a guessed step."""
    t = (tail or "").lower()
    if "bad extension id" in t:
        return "the extension id"
    if "build" in t:
        return "the build"
    if "host.json" in t:
        return "the host.json write"
    if "native messaging hosts" in t or "registry" in t or \
            "set-itemproperty" in t:
        return "the register"
    if "manifest" in t or "host-manifest" in t:
        return "the manifest write"
    return "the install"


def _caps_line(caps):
    """The capabilities reply as the card's line - the same render
    companion._caps_line shows the card (mirrored here, not imported -
    companion imports nmhost, the circle stays one-way) so install's
    success word IS the fresh host's own reply."""
    opnames = tuple(x for x in ops(caps) if isinstance(x, str))
    fields = tuple(x for x in veil_fields(caps) if isinstance(x, str))
    line = "companion API: " + ", ".join(opnames) if opnames else \
        "companion API: (no ops)"
    if isinstance(caps.get("auto"), dict):
        line += ", auto on play"
    if fields:
        line += " - veil sends " + "/".join(fields)
    return line


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