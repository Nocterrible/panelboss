"""The companion's config pin (Oct 16, the native-messaging v0.3 move).
The debug-flag route is dead AND now removed: the debug port handed any
local process full CDP (the infostealer classic), and the companion is
the native-messaging extension - the extension measures the video, the
local host writes the app's own doorway file, the eye reads it. This pin
proves the one-consent shape: [videodim].on is the only rail, the
retired enabled/flag_families/sites keys parse away without surprise,
and the module (companion.on/say/veil_now) answers the off words on junk
and the live words on a click. The doorway is redirected to a temp dir
so the owner's real rect file never touches the suite.
Run: .venv\\Scripts\\python.exe scripts\\companion_test.py
"""
import json
import os
import struct
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PANELBOSS_CONFIG_DIR"] = tempfile.mkdtemp(prefix="panelboss_cmp_")

from panelboss import config   # noqa: E402
from panelboss import companion   # noqa: E402
from panelboss import nmhost   # noqa: E402
from panelboss import videoeye   # noqa: E402

fails = []
passed = []


def check(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    (passed if cond else fails).append(name)


D = config.DEFAULTS["videodim"]
check("on" in D and "enabled" not in D and "flag_families" not in D
      and "sites" not in D,
      "the default is the one-consent shape: on present, enabled/"
      "flag_families/sites absent")
check(D.get("on") is False,
      "the companion default is on False (the default-off law)")

# a stock get_config carries only on, and the normalizer passes it
# through while DROPPING the retired keys a pre-ruling file may carry
c = config.get_config(verbose=False)
check(c["videodim"].get("on") is False and "enabled" not in c["videodim"],
      "get_config answers on False and carries no enabled on a virgin "
      "file")

# a pre-ruling config with the retired keys still loads - the retired
# words are dropped, the single consent survives
path = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"], "config.toml")
with open(path, "w", encoding="utf-8") as f:
    f.write("[videodim]\non = true\nenabled = false\n"
            "flag_families = ['chrome']\nsites = ['netflix.com']\n")
c2 = config.get_config(verbose=False)
check(c2["videodim"].get("on") is True and "enabled" not in c2["videodim"]
      and "flag_families" not in c2["videodim"]
      and "sites" not in c2["videodim"],
      "a pre-ruling file on=true loads; the retired enabled/"
      "flag_families/sites words are gone")

n = config.normalize_videodim({"on": "junk", "enabled": True,
                               "flag_families": ["chrome"],
                               "sites": ["youtube.com"]})
check(n == {"on": False, "min_rect_px": 200000, "grace_s": 3,
            "idle_sec": 15, "level": 20, "fade": False,
            "hole": "video", "monitors": {}},
      "junk on folds to False and the retired keys never survive the "
      "normalizer (the per-panel monitors table defaults to the "
      "legacy empty - the Oct-16 wave's shape; the hole word lands on "
      "the Oct-24 video default)")

# the companion module: junk answers the off words, never raises
for junk in (None, {}, {"videodim": "junk"}, {"videodim": 7},
             {"videodim": {"on": "yes"}}):
    try:
        words = companion.say(junk)
    except Exception as e:      # noqa: BLE001
        words = "RAISED %s" % e
    check(words == "video-dim off - arm it and the click is honored",
          "junk config %r answers the off words, never an exception"
          % (junk,))
check(companion.on({"videodim": {"on": True}}) is True
      and companion.on({"videodim": {"on": "yes"}}) is False,
      "on is strict like the normalizer: only True is on")

# redirect the doorway to a temp file the desk cannot own
_real_rect = videoeye.RECT_PATH
_real_host_json = nmhost.HOST_JSON
_dark = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"], "no-rect")
videoeye.RECT_PATH = _dark
# AND the host registration - the _no_companion fork (installed vs never)
# reads host.json too, and since the owner's install button the REAL
# one exists on a live desk: the suite must answer its own questions,
# never the machine's. (Oct-16: the first post-install run caught this
# isolation gap - the pin was true only on an uninstalled box.)
nmhost.HOST_JSON = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"],
                                "no-host.json")
try:
    check(companion.bridge_state() is None,
          "no doorway file answers None, never raises")
    check(companion.say({"videodim": {"on": True}}) == companion.NO_COMPANION,
          "the say line names the missing companion as an installation step")
    check(companion.veil_now({"videodim": {"on": True}})
          == companion.NO_COMPANION,
          "the manual one-shot on a dark desk answers the installation "
          "words (absent doorway), never a fault's words")

    # a click: a temp file through the eye's own doorway, folded to
    # physical px and fed - the button's contract
    body = {"rect": {"left": 0, "top": 0, "width": 800, "height": 450},
            "dpr": 1.5, "paused": False, "scroll": [0, 0],
            "view": [1920, 1080], "family": "chrome",
            "bounds": {"left": 100, "top": 50, "width": 1920,
                       "height": 1080}}
    with open(_dark, "w", encoding="utf-8") as f:
        f.write(json.dumps(body) + "\n")
    words = companion.veil_now({"videodim": {"on": True,
                                             "min_rect_px": 1}})
    check(words.startswith("companion rect 1200x675 at 150,75"),
          "the click folds through the eye's own door: %r" % (words,))
    st = videoeye._STATE.get("chrome")
    check(st is not None and st["row"] is not None
          and st["row"]["rect"]["width"] == 800,
          "the one-shot feeds the eye's state fresh-wins: the dimmer's "
          "next tick frames it")
    # the ghost branch (Oct 19 gate round): a click-test on an
    # OFF-DESK picture must confess the ghost, not promise a frame
    # the visible-picture law will veto on the tick
    body["bounds"] = {"left": -32000, "top": -32000, "width": 1920,
                      "height": 1080}
    with open(_dark, "w", encoding="utf-8") as f:
        f.write(json.dumps(body) + "\n")
    words = companion.veil_now({"videodim": {"on": True,
                                             "min_rect_px": 1}})
    check("OFF the desk" in words and "next tick" not in words,
          "a click on a suspended tab answers the ghost, not the "
          "promise: %r" % (words,))
    body["paused"] = True
    with open(_dark, "w", encoding="utf-8") as f:
        f.write(json.dumps(body) + "\n")
    words = companion.veil_now({"videodim": {"on": True,
                                             "min_rect_px": 1}})
    check("waits for play" in words,
          "a PAUSED ghost keeps the paused fork's precedence (the "
          "eye's own order): %r" % (words,))
    body["paused"] = False
    words = companion.veil_now({})
    check(words.startswith("saw the rect"),
          "a click with the eye unarmed says so, no state fed")
    check(isinstance(companion.door_dir(), str)
          and companion.door_dir() == _dark,
          "door_dir() answers the redirected doorway path")
finally:
    videoeye.RECT_PATH = _real_rect
    nmhost.HOST_JSON = _real_host_json

# --- capability discovery (the owner's mandate, Oct 16 close) ---------
# The card asks the HOST what the API can send, not a stored guess. The
# fake host is sys.executable + a script twin that speaks the host's own
# frame codec (native-order length prefix) and answers capabilities - so
# the pin proves the app READ the answer, and a wedged/absent host reads
# as the honest not-installed words, never a hang.
from panelboss import nmhost   # noqa: E402

_fake_host = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"],
                          "fakehost.py")
with open(_fake_host, "w", encoding="utf-8") as f:
    f.write(
        'import json, struct, sys\n'
        'n = struct.unpack("@I", sys.stdin.buffer.read(4))[0]\n'
        'sys.stdin.buffer.read(n)\n'
        'caps = {"op": "capabilities", "protocol": "panelboss-v1",\n'
        '        "host": "com.nocterrible.panelboss",\n'
        '        "ops": ["capabilities", "veil"],\n'
        '        "veil": {"fields": ["rect", "dpr", "paused",\n'
        '                            "scroll", "view", "bounds",\n'
        '                            "family", "ts"]}}\n'
        'out = json.dumps(caps).encode()\n'
        'sys.stdout.buffer.write(struct.pack("@I", len(out)) + out)\n'
        'sys.stdout.buffer.flush()\n')

_real_host_json = nmhost.HOST_JSON
_real_ask = nmhost._ask
nmhost.HOST_JSON = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"],
                                "host.json")
with open(nmhost.HOST_JSON, "w", encoding="utf-8") as f:
    json.dump({"path": _fake_host}, f)      # the twin stands in as the
                                             # "exe" - the seam is the
                                             # spawn, redone below
nmhost._ask = lambda exe: _real_ask(sys.executable, _fake_host)
nmhost._cache.update(until=0.0, caps=None)
try:
    # absent host.json first: no file, honest words, never a spawn
    nmhost.HOST_JSON = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"],
                                    "no-host.json")
    nmhost._cache.update(until=0.0, caps=None)
    check(companion.caps_words() == nmhost.NOT_INSTALLED,
          "no host installed answers the honest not-installed words")
    check(nmhost.capabilities() is None,
          "capabilities() answers None on an absent host")

    # the fake twin answers: caps_words reads the ops and veil fields
    nmhost.HOST_JSON = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"],
                                    "host.json")
    # THE BOM PIN (2nd-pass gate finding 1, HIGH): install_host.ps1
    # writes host.json with Windows PowerShell's Set-Content -Encoding
    # UTF8, which EMITS A BOM (measured EF BB BF on this box). The
    # reader must tolerate it - a BOM-rejecting reader would tell the
    # FRESHLY INSTALLED user "not installed" forever, and this suite
    # could never see it because Python's json.dump writes no BOM.
    with open(nmhost.HOST_JSON, "wb") as f:
        f.write(b"\xef\xbb\xbf" + json.dumps({"path": _fake_host}).
                encode("utf-8"))
    nmhost._cache.update(until=0.0, caps=None)
    check(nmhost.capabilities() is not None,
          "a BOM'd host.json (PowerShell's Set-Format UTF8 signature) "
          "reads like any other - the installer and the reader speak "
          "one file")
    with open(nmhost.HOST_JSON, "w", encoding="utf-8") as f:
        json.dump({"path": _fake_host}, f)
    caps = nmhost.capabilities()
    check(caps is not None and caps.get("protocol") == "panelboss-v1"
          and "veil" in caps.get("ops", ()),
          "capabilities() spawns the host and reads the framed reply")
    words = companion.caps_words()
    check(words.startswith("companion API: capabilities, veil")
          and "rect" in words and "family" in words,
          "caps_words renders the ops list and the veil field names: "
          "%r" % (words,))
    check(companion.caps_words() == words,
          "the capsule answer is cached (the TTL holds between beats)")

    # JUNK MEMBERS (2nd-pass gate finding 2): a well-shaped reply with
    # rotten contents - {"ops":[1,2]} - must read as words, never a
    # TypeError out of a function that promises it never raises.
    check(companion._caps_line({"ops": [1, 2],
                                "veil": {"fields": ["rect", None]}})
          == "companion API: (no ops) - veil sends rect",
          "junk members inside a well-shaped list answer honest words")

    # the wedged-host law: a path that answers nothing must time out
    # into None, never hang the beat
    wedged = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"],
                          "wedged.py")
    with open(wedged, "w", encoding="utf-8") as f:
        f.write("import time\ntime.sleep(30)\n")
    with open(nmhost.HOST_JSON, "w", encoding="utf-8") as f:
        json.dump({"path": wedged}, f)
    nmhost._cache.update(until=0.0, caps=None)
    nmhost._ask = lambda exe: _real_ask(sys.executable, wedged)
    t0 = time.monotonic()
    check(nmhost.capabilities() is None,
          "a wedged host answers None")
    check(time.monotonic() - t0 < 5.0,
          "a wedged host is killed inside the timeout, never a hang")
finally:
    nmhost._ask = _real_ask
    nmhost.HOST_JSON = _real_host_json
    nmhost._cache.update(until=0.0, caps=None)

# --- the helper-install law (Oct 16): the browser's id derivation and
# the app's one-click. TWO BRANCHES (Oct 16 key pin): if the manifest
# carries "key" (base64 SPKI DER), the id is SHA-256 over the DECODED
# KEY BYTES, first 16, nibbles a-p - permanent across folders,
# machines, and the store. Only keyless folders use the PATH law:
# SHA-256 over the absolute load path exactly as the browser
# normalizes it (drive letter UPPERCASE, backslashes, UTF-8 bytes).
# THE PERMANENT ID (key branch, companion_key.txt):
#   extension/ (manifest carries the key)
#     -> feolhiokchmpphlhllagimnilceldegk
# PATH-branch vectors, pinned before the key existed and still true
# of keyless folders (the first is the historical value of THIS folder
# while it was keyless):
#   sha256(rb"F:\Projects\panelboss-reskin\extension")[:16], a-p
#     -> jagfnepkfnioappmbloibkcjofhgaaai
#   sha256(b"F:\workspace").digest()[:16], nibbles a-p
#     -> jeafefjdigahcngkajpclimdpjjamadc
check(nmhost.derive_unpacked_id(
    r"F:\Projects\panelboss-reskin\extension")
    == "feolhiokchmpphlhllagimnilceldegk",
    "the KEY BRANCH pins the permanent id: the manifest's key wins "
    "over the path, so the store copy, this folder, and every machine "
    "agree on one id (the browser derives the same way)")
check(nmhost.derive_key_id(
    r"F:\Projects\panelboss-reskin\extension")
    == "feolhiokchmpphlhllagimnilceldegk",
    "the key branch answers the id on its own, not only as a "
    "fallthrough inside the path branch")
check(nmhost.derive_unpacked_id(r"F:\workspace")
      == "jeafefjdigahcngkajpclimdpjjamadc",
      "the path-branch vector pins the fallback law on a keyless dir "
      "(F:\\workspace carries no manifest.json)")
check(nmhost.derive_key_id(r"F:\workspace") is None,
      "a keyless folder answers None from the key branch - the "
      "fallthrough to the path law is the browser's own behavior")
import json as _json
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "extension", "manifest.json"),
          encoding="utf-8") as _m:
    _real_key = _json.load(_m)["key"]
_with_key = tempfile.mkdtemp(prefix="panelboss_keydir_")
with open(os.path.join(_with_key, "manifest.json"), "w") as _f:
    _json.dump({"key": _real_key}, _f)
_bad_key = tempfile.mkdtemp(prefix="panelboss_badkey_")
with open(os.path.join(_bad_key, "manifest.json"), "w") as _f:
    _f.write("{ not json")
check(nmhost.derive_unpacked_id(_with_key)
      == nmhost.derive_unpacked_id(
          r"F:\Projects\panelboss-reskin\extension"),
      "folder independence: a SYNTHETIC dir carrying the same key "
      "derives the same id - this is the property that makes the pin "
      "survive folder moves and the store")
check(nmhost.derive_unpacked_id(_bad_key)
      == nmhost.derive_unpacked_id(os.path.abspath(_bad_key)),
      "a broken manifest falls through to the path law, never raises "
      "- the same answer the keyless folder gets")
check(nmhost.derive_unpacked_id(r"f:\workspace")
      == "jeafefjdigahcngkajpclimdpjjamadc",
      "the casing law is the NORMALIZATION, not the caller's "
      "spelling: a lowercase drive folds to the browser's uppercase "
      "before the hash")
check(nmhost.derive_unpacked_id("") is None
      and nmhost.derive_unpacked_id("  ") is None
      and nmhost.derive_unpacked_id(None) is None,
      "no dir answers None, never a guess of an id")

# THE WORDS MOVED WITH THE BUTTON (Oct 16 wave): the absent-host line
# points at the card's install verb, the ps1 stays the documented
# manual route. Exact strings - no substring drift. (Moved by the
# helper-install wave, companion_test's pin moves with them in the
# same commit.)
check(nmhost.NOT_INSTALLED == "the companion's helper is not installed - "
                              "press install the helper above",
      "NOT_INSTALLED answers the button phrasing (exact)")
check(companion.NO_COMPANION == "the companion's helper is not installed - "
                            "press install the helper below (or run "
                            "extension\\host\\install_host.ps1)",
      "the say-line words point at the button and keep the ps1 "
      "manual route (exact)")

# install() refuses a malformed override WITHOUT touching powershell
# (the spy wraps the spawn itself: the real ps1 validates the same
# shape, the app must refuse earlier and say so). The twin: a .ps1 in
# the suite's own temp dir that echoes and writes a host.json - the
# REAL subprocess call runs it through the redirected doorway
# (the owner's real %APPDATA% install is not this suite's to move).
_twin = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"],
                     "fake_install.ps1")
with open(_twin, "w", encoding="utf-8") as f:
    f.write(
        'param([string]$ExtensionId = "")\n'
        '$here = Split-Path -Parent $MyInvocation.MyCommand.Path\n'
        'Write-Output ("fake installer: id " + $ExtensionId)\n'
        '@{ path = "' + sys.executable + '" } | ConvertTo-Json | '
        'Set-Content -Path (Join-Path $here "host.json") '
        '-Encoding UTF8\n'
        '@{ name = "companion_test.twin"; allowed_origins = '
        '@("chrome-extension://" + $ExtensionId + "/") } | '
        'ConvertTo-Json | Set-Content '
        '-Path (Join-Path $here "host-manifest.json") -Encoding UTF8\n'
        "Write-Output ('host installed for origin chrome-extension://"
        "$ExtensionId/')\n")
_ftwin = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"],
                      "failing_install.ps1")
with open(_ftwin, "w", encoding="utf-8") as f:
    f.write('param([string]$ExtensionId = "")\n'
            'Write-Output "host build failed (1)"\nexit 1\n')

_real_run = nmhost._spawn.run
_real_ps1 = nmhost._INSTALL_PS1
_calls = []


def _spy(args, **kw):
    _calls.append((list(args), dict(kw)))
    return _real_run(args, **kw)


_real_host_json = nmhost.HOST_JSON
_real_root = nmhost._APP_ROOT
_real_reg_read = nmhost._REG_READ
nmhost._spawn.run = _spy
# THE REGISTRY READ-BACK SEAM (gate round 2): the twin just writes
# host-manifest.json beside its host.json - the fake key points the
# probe at THAT file, so registered_origins runs its real json read
# on real Set-Content bytes (BOM and all).
nmhost._REG_READ = lambda: os.path.join(
    os.environ["PANELBOSS_CONFIG_DIR"], "host-manifest.json")
nmhost.HOST_JSON = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"],
                                "host.json")
nmhost._cache.update(until=0.0, caps=None)
try:
    ok, words = nmhost.install("TOO-SHORT")
    check(ok is False and "bad extension id" in words,
          "install refuses a malformed override id: %r" % (words,))
    check(not _calls,
          "the malformed-id refusal does NOT touch powershell")

    nmhost._INSTALL_PS1 = _twin
    nmhost._ask = lambda exe: _real_ask(sys.executable, _fake_host)
    ok, words = nmhost.install("abcdefghijklmnopabcdefghijklmnop")
    pw = [c for c in _calls if c[1].get("env") is not None]
    check(ok is True, "install answers True on a clean installer run")
    check(words.startswith("helper installed - registered for "
                           "abcdefghijklmnopabcdefghijklmnop"),
          "the success word NAMES the registered id (gate round 2: "
          "the registry read-back carried it): %r" % (words,))
    check("companion API:" in words,
          "the fresh host's capability line still rides behind the "
          "id (the probe is the proof-of-install): %r" % (words,))
    check(len(pw) == 1 and pw[0][0][:5] == ["powershell", "-NoProfile",
                                            "-ExecutionPolicy",
                                            "Bypass", "-File"],
          "the installer runs through powershell -NoProfile "
          "-ExecutionPolicy Bypass -File: %r" % (pw[0][0][:5],))
    check(pw[0][1]["env"]["PATH"].split(os.pathsep)[0]
          == os.path.dirname(sys.executable),
          "PATH is PREPENDED with the venv's Scripts dir "
          "(PyInstaller 6.22.3 lives there)")
    check(pw[0][0][-3:] == ["-ExtensionId",
                            "abcdefghijklmnopabcdefghijklmnop",
                            "-Rebuild"],
          "the resolved id reaches the installer, and the install "
          "route always rebuilds (gate finding 4: a partial exe from "
          "a killed build must not wedge reinstall behind Test-Path)")
    import codecs
    with open(nmhost.HOST_JSON, "rb") as f:
        raw = f.read()
    check(raw.startswith(codecs.BOM_UTF8),
          "the twin wrote host.json through the real Set-Content - "
          "the BOM the reader must survive is the producer's real "
          "signature, replayed through the app's own reader")
    with open(nmhost.HOST_JSON, encoding="utf-8-sig") as f:
        hp = json.load(f).get("path")
    check(hp == sys.executable,
          "the twin's host.json landed where the reader reads")

    _calls.clear()
    nmhost._INSTALL_PS1 = _ftwin
    ok, words = nmhost.install("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    check(ok is False and "the build refused" in words
          and "-ExtensionId bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" in words,
          "the failing installer names its step from its OWN line and "
          "keeps the manual route: %r" % (words,))

    # ---- GATE ROUND 2 (Oct 25): THE ID LADDER, three rungs, in a
    # bundle-shaped tmp world (extension/host/ files, manifest as the
    # trust gate). The twin echoes whatever id it is handed into the
    # registered manifest, so each rung's proof-of-install can pass.
    nmhost._INSTALL_PS1 = _twin
    _broot = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"], "bundle")
    os.makedirs(os.path.join(_broot, "extension", "host"))
    nmhost._APP_ROOT = _broot
    import logging as _lg
    _logs = []

    class _Cap(_lg.Handler):
        def emit(self, r):
            _logs.append(r.getMessage())

    _lh = _Cap()
    _lgr = _lg.getLogger("nmhost")
    _lgr.addHandler(_lh)
    # the desk default is root=WARNING; an unlevelled logger would
    # filter the branch line before the handler ever sees it (the
    # silent-capture class - the pin would pass on an empty list
    # forever).
    _lgr.setLevel(_lg.INFO)
    try:
        _calls.clear()
        ok, words = nmhost.install(None)
        check(ok is True and ("registered for " + nmhost.STORE_ID) in words,
              "rung three - no manifest -> the store constant, named in "
              "the success word: %r" % (words,))
        pw = [c for c in _calls if c[1].get("env") is not None]
        check(pw and pw[-1][0][-3:] == ["-ExtensionId", nmhost.STORE_ID,
                                        "-Rebuild"],
              "the store id reaches the installer")
        check(any("chosen by store id" in m for m in _logs),
              "the branch that CHOSE the id is logged (a support read "
              "sees the registration's reasoning): %r" % (_logs,))
        check(nmhost.STORE_ID == "feolhiokchmpphlhllagimnilceldegk",
              "the constant IS the published listing (the repo "
              "manifest's key-branch id - permanent once shipped)")

        # rung two: WITH a manifest the derivation outranks the
        # constant - a stranger key derives a stranger id, and THAT
        # is what registers (a load-unpacked desk is its own truth).
        with open(os.path.join(_broot, "extension", "manifest.json"),
                  "w", encoding="utf-8") as mf:
            mf.write(json.dumps({"key": "A" * 40}))   # valid base64
        derived = nmhost.derive_unpacked_id(
            os.path.join(_broot, "extension"))
        check(derived and derived != nmhost.STORE_ID,
              "a stranger-keyed manifest derives a stranger id (the "
              "test world is honest: derivation CAN disagree)")
        _calls.clear()
        ok, words = nmhost.install(None)
        check(ok is True and ("registered for " + derived) in words,
              "rung two - the on-disk derivation outranks the store "
              "constant: %r" % (words,))
        check(any("chosen by unpacked derivation" in m for m in _logs),
              "the derivation branch logs itself too")

        # rung one: the explicit arg outranks BOTH, even in this tmp
        # world (where derivation would say otherwise).
        _calls.clear()
        ok, words = nmhost.install("p" * 32)
        check(ok is True and ("registered for " + "p" * 32) in words,
              "rung one - the explicit id wins over derivation and "
              "store alike: %r" % (words,))

        # THE REGISTRY IS THE SECOND PROOF - the twin's exe answers
        # and the manifest names a STRANGER: no victory word.
        _stranger = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"],
                                 "stranger-manifest.json")
        with open(_stranger, "w", encoding="utf-8") as mf:
            json.dump({"allowed_origins":
                       ["chrome-extension://%s/" % ("m" * 32)]}, mf)
        nmhost._REG_READ = lambda: _stranger
        ok, words = nmhost.install("abcdefghijklmnopabcdefghijklmnop")
        check(ok is False and ("chrome-extension://%s/" % ("m" * 32))
              in words and "registered for" not in words,
              "a stranger in allowed_origins reads as FAILURE naming "
              "the stranger (the silent-lie class, dead): %r"
              % (words,))

        # and NO KEY AT ALL: read-back None is also not a victory.
        nmhost._REG_READ = lambda: None
        ok, words = nmhost.install("abcdefghijklmnopabcdefghijklmnop")
        check(ok is False and "be read back" in words
              and "com.nocterrible.panelboss" in words,
              "an unreadable registration fails honestly and names "
              "the key: %r" % (words,))
    finally:
        _lgr.removeHandler(_lh)
        _lgr.setLevel(_lg.NOTSET)
finally:
    nmhost._spawn.run = _real_run
    nmhost._INSTALL_PS1 = _real_ps1
    nmhost._ask = _real_ask
    nmhost.HOST_JSON = _real_host_json
    nmhost._APP_ROOT = _real_root
    nmhost._REG_READ = _real_reg_read
    nmhost._cache.update(until=0.0, caps=None)

# --- v0.4.3 popup readout pins: the toolbar icon opens a live readout,
# the test gesture survives as a button INSIDE it. Pinned structure, not
# style: the manifest points at a popup.html that exists, the packager
# carries it (a popup the zip omits is a popup that does not exist in
# the store), and background must dispatch the button's {op:"veil_now"}
# BEFORE the sender.tab filter - a popup message has no tab and the old
# guard would drop it in silence (the classic class: 200s with nothing
# behind them).
_EXT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "extension")
with open(os.path.join(_EXT, "manifest.json"), encoding="utf-8") as _m:
    _man = _json.load(_m)
check(_man.get("action", {}).get("default_popup") == "popup.html"
      and os.path.isfile(os.path.join(_EXT, "popup.html"))
      and os.path.isfile(os.path.join(_EXT, "popup.js")),
      "the manifest points the icon at popup.html and both popup "
      "files exist beside it")
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "package_extension.py"), encoding="utf-8") as _f:
    _pkg = _f.read()
check('"popup.html"' in _pkg and '"popup.js"' in _pkg,
      "the packager's LOADABLE carries the popup (silent-drop class: "
      "an unlisted file ships as absence)")
with open(os.path.join(_EXT, "background.js"), encoding="utf-8") as _f:
    _bg = _f.read()
check(_bg.index('msg.op === "veil_now"')
      < _bg.index('if (!msg || !sender || !sender.tab)'),
      "the veil_now branch precedes the tab filter verbatim line - "
      "comments may mention either, the ORDER of code is what's pinned")
with open(os.path.join(_EXT, "content.js"), encoding="utf-8") as _f:
    _ct = _f.read()
check('op: "measure"' in _bg and '"measure"' in _ct,
      "the popup asks the ONE question: measure is served by content, "
      "relayed by background, shown by popup - there is no second "
      "measure")

# --- dossier H source pins: the ack-aware dedupe, the delivery ack,
# and the playing-only heartbeat live in the extension's own files -
# pin their seams verbatim so a regression can never read as a 200.
check('lastError || !res || !res.ok' in _ct
      and 'chrome.runtime.sendMessage({ op: "veil"' in _ct,
      "content.js carries the ack-aware dedupe: the callback form "
      "rolls lastSent back on lastError / a missing / a not-ok ack")
check('timeupdate' in _ct and 'push(false)' in _ct
      and 'setInterval' not in _ct,
      "content.js rides the timeupdate heartbeat (playing-only, the "
      "same push(false) dedupe path) and writes NO setInterval")
_vb = _bg[_bg.index('msg.op === "veil"'):]   # the AUTOMATIC branch,
                                             # not the popup's "veil_"
check('sendResponse({ ok: ok === true })' in _vb and 'return true;'
      in _vb,
      "background.js acks DELIVERY, not receipt: the veil branch "
      "awaits the push, answers with its truth, and returns true to "
      "hold the channel open for the async sendResponse")

# THE HOST FILE ITSELF gets a load-pin (V's leg-7 catch, Oct 25: the
# file had NO test at all, and the moved webrect import was silently
# NameError-ing into the belt - the catch-all made the wound invisible
# and every veil frame lost its OS-side measure). Load the real file,
# stub 'webrect' in sys.modules (the host imports it BARE, at use time,
# inside _veil's try), and drive _veil through BOTH lanes.
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "panelboss_host_under_test",
    os.path.join(_EXT, "host", "panelboss_host.py"))
_host = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_host)
_host.RECT_PATH = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"],
                               "veil_probe_rect")


class _WRect:
    @staticmethod
    def webrect(payload):
        return {"x": 1, "y": 2, "w": 3, "h": 4}


sys.modules["webrect"] = _WRect
_ans = _host._veil({"payload": {"view": [0, 0, 10, 10]}})
check(_ans.get("ok") is True,
      "the host writes the doorway when asked (op=veil answers ok)")
_row = json.loads(open(_host.RECT_PATH, encoding="utf-8").readline())
check(_row.get("webrect") == {"x": 1, "y": 2, "w": 3, "h": 4},
      "the import-in-the-try BINDS and runs (leg 7: the deleted "
      "module-level import NameError'd silently into the except - "
      "this pin cannot be satisfied by the catch-all)")

sys.modules["webrect"] = None        # a frozen import failure (missing
                                     # side-car): import raises at use
_ans = _host._veil({"payload": {"view": [0, 0, 10, 10]}})
check(_ans.get("ok") is True and "webrect" not in json.loads(
    open(_host.RECT_PATH, encoding="utf-8").readline()),
      "the import failure reads as NO MEASURE, not a raise: the write "
      "still lands, the fold's compat lanes carry the ring, the relay "
      "still never dialogs (the guard's real promise)")
del sys.modules["webrect"]

# --- dossier H host-side session pin: drive the REAL host module's
# own main() (the harness above loaded it) through in-memory framed
# pipes: capabilities -> veil(row A) -> veil(identical A) ->
# veil(A-with-paused-true). Per frame the reply reads ok; the doorway
# carries the row after each; and the mtime MOVES for the paused row.
# The identical A must land too: the dedupe lives in the extension's
# lastSent, never in the host - the host rewrites, every frame.
import io as _io
import msvcrt as _msvcrt
sys.modules["webrect"] = _WRect        # the stub the load-pin used
_real_stdin, _real_stdout = sys.stdin, sys.stdout
_real_setmode = _msvcrt.setmode
_msvcrt.setmode = lambda *a: None      # in-memory pipes have no real fd


def _frame(obj):
    data = json.dumps(obj).encode("utf-8")
    return struct.pack("@I", len(data)) + data


class _Pipe:
    """main()'s stdin/stdout as in-memory binary (it wants .buffer,
    and the win32 branch wants a fileno() for msvcrt.setmode)."""

    def __init__(self, data):
        self.buffer = data

    def fileno(self):
        return -1


def _row_a(paused=False, ts=1):
    return {"rect": {"left": 0, "top": 0, "width": 800, "height": 450},
            "dpr": 1.0, "paused": paused, "scroll": [0, 0],
            "view": [1920, 1080], "lane": "auto", "origin": [0, 0],
            "bounds": {"left": 0, "top": 0, "width": 1920,
                       "height": 1080},
            "family": "chrome", "ts": ts}


def _session(*msgs):
    """One framed session through the host's real main(); the replies,
    read back with the host's own frame reader."""
    old_in, old_out = sys.stdin, sys.stdout
    sys.stdin = _Pipe(_io.BytesIO(b"".join(_frame(m) for m in msgs)))
    sys.stdout = _Pipe(_io.BytesIO())
    try:
        _host.main()
        data = sys.stdout.buffer.getvalue()
    finally:
        sys.stdin, sys.stdout = old_in, old_out
    out = _io.BytesIO(data)
    reps = []
    while True:
        rep = _host._read_frame(out)
        if rep is None:
            break
        reps.append(rep)
    return reps


def _door_lines():
    with open(_host.RECT_PATH, encoding="utf-8") as f:
        return f.readlines()


_W = {"x": 1, "y": 2, "w": 3, "h": 4}       # the stub's answer
try:
    _reps = _session({"op": "capabilities"})
    check(len(_reps) == 1 and _reps[0].get("op") == "capabilities"
          and _reps[0].get("protocol") == "panelboss-v1"
          and "veil" in _reps[0].get("ops", ()),
          "dossier H session: the capabilities frame round-trips the "
          "open wire's self-description through the host's main()")
    _reps = _session({"op": "veil", "payload": _row_a()})
    check(len(_reps) == 1 and _reps[0].get("ok") is True
          and _reps[0].get("path") == _host.RECT_PATH,
          "dossier H session: veil(row A) answers ok and names the "
          "doorway it wrote")
    check(_door_lines() == [json.dumps({**_row_a(), "webrect": _W})
                            + "\n"],
          "dossier H session: the doorway carries A after the veil - "
          "ONE line, the payload folded with the OS-side measure")
    _door_a = _door_lines()
    _mt_a = os.path.getmtime(_host.RECT_PATH)
    _reps = _session({"op": "veil", "payload": _row_a()})
    check(_reps[0].get("ok") is True and _door_lines() == _door_a,
          "dossier H session: the identical row A re-answers ok and "
          "the doorway still carries it - the host rewrites (the A/A "
          "dedupe is the app's, never the host's)")
    time.sleep(0.11)                        # outlast the fs tick
    _reps = _session({"op": "veil", "payload": _row_a(paused=True)})
    check(_reps[0].get("ok") is True
          and _door_lines() == [json.dumps({**_row_a(paused=True),
                                           "webrect": _W}) + "\n"]
          and os.path.getmtime(_host.RECT_PATH) > _mt_a,
          "dossier H session: A-with-paused-true answers ok, the "
          "doorway carries the paused row, and its mtime MOVED (a "
          "rewrite the app-side reader can see)")
finally:
    sys.stdin, sys.stdout = _real_stdin, _real_stdout
    _msvcrt.setmode = _real_setmode
    del sys.modules["webrect"]

print("COMPANION-PIN OK (%d)" % len(passed) if not fails
      else "COMPANION-PIN FAILED: %s" % fails)
sys.exit(1 if fails else 0)