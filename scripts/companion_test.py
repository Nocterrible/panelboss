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
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PANELBOSS_CONFIG_DIR"] = tempfile.mkdtemp(prefix="panelboss_cmp_")

from panelboss import config   # noqa: E402
from panelboss import companion   # noqa: E402
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
            "idle_sec": 15, "level": 20, "fade": False},
      "junk on folds to False and the retired keys never survive the "
      "normalizer")

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
_dark = os.path.join(os.environ["PANELBOSS_CONFIG_DIR"], "no-rect")
videoeye.RECT_PATH = _dark
try:
    check(companion.bridge_state() is None,
          "no doorway file answers None, never raises")
    check(companion.say({"videodim": {"on": True}}) == companion.NO_BUDDY,
          "the say line names the missing buddy as an installation step")
    check(companion.veil_now({"videodim": {"on": True}})
          == companion.NO_BUDDY,
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
    words = companion.veil_now({})
    check(words.startswith("saw the rect"),
          "a click with the eye unarmed says so, no state fed")
    check(isinstance(companion.door_dir(), str)
          and companion.door_dir() == _dark,
          "door_dir() answers the redirected doorway path")
finally:
    videoeye.RECT_PATH = _real_rect

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
    check(words.startswith("buddy API: capabilities, veil")
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
          == "buddy API: (no ops) - veil sends rect",
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
check(nmhost.NOT_INSTALLED == "the buddy's helper is not installed - "
                              "press install the helper above",
      "NOT_INSTALLED answers the button phrasing (exact)")
check(companion.NO_BUDDY == "the buddy's helper is not installed - "
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
nmhost._spawn.run = _spy
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
    check(words.startswith("helper installed - buddy API:"),
          "the success word IS the fresh host's capability line "
          "(the probe is the proof-of-install): %r" % (words,))
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
finally:
    nmhost._spawn.run = _real_run
    nmhost._INSTALL_PS1 = _real_ps1
    nmhost._ask = _real_ask
    nmhost.HOST_JSON = _real_host_json
    nmhost._cache.update(until=0.0, caps=None)

print("COMPANION-PIN OK (%d)" % len(passed) if not fails
      else "COMPANION-PIN FAILED: %s" % fails)
sys.exit(1 if fails else 0)