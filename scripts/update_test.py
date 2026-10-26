"""The updater's offline suite: a fake urllib (no live network in
suites), the version table, the honest error line, the download's
one-file-cheap sweep, the apply.bat content pins, and the FROZEN
branch's command shape (the console-verb ledger's second line:
cmd.exe /c + creationflags=0). Run from repo root:
python scripts/update_test.py
"""
import io
import json
import os
import shutil
import sys
import tempfile
import types
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelboss import update                                    # noqa: E402
from panelboss.ui.window import _general as G                   # noqa: E402

TMP = tempfile.mkdtemp(prefix="pb_update_test_")
API = update.RELEASE_API
ASSET_URL = "https://example.test/PanelBoss-0.3.3-user.msi"
REAL_OPEN = urllib.request.urlopen
CALLS = []

# THE RUNNING-VERSION PIN (the 0.3.3 bump is what made this load-
# bearing): check()'s default current binds panelboss.__version__ at
# import, and the fake releases below all live at v0.3.3 - the day
# the build ships the version the fakes announced, an unpinned
# 'behind' silently becomes 'current' and the suite reds on the
# CALENDAR, not on the code. The suite's running version is 0.3.2
# here, explicit and forever (the never-the-desk doctrine the state
# suites already obey for timers and confidence; the updater's own
# semver table above is baseline-free and untouched).
_real_check = update.check


def _pinned_check(current=None):
    return _real_check("0.3.2" if current is None else current)


update.check = _pinned_check


def release(tag, names=("PanelBoss-0.3.3-user.msi", "src.zip")):
    return {"tag_name": tag,
            "assets": [{"name": n,
                        "browser_download_url":
                            ASSET_URL if n.endswith("-user.msi")
                            else "https://example.test/" + n}
                       for n in names]}


class Resp:
    """a urlopen answer: reads like a socket for json.load AND for
    shutil.copyfileobj."""
    def __init__(self, payload):
        self.buf = io.BytesIO(payload if isinstance(payload, bytes)
                              else json.dumps(payload).encode())

    def read(self, n=-1):
        return self.buf.read(n if n is not None else -1)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def route(json_body, msi_body=b"MSIDATA"):
    """the fake network: the API url answers json_body (or raises it),
    anything else streams msi_body."""
    def fake(req, timeout=None):
        url = req.full_url if isinstance(req, urllib.request.Request) \
            else str(req)
        CALLS.append((url, timeout))
        if url == API:
            if isinstance(json_body, Exception):
                raise json_body
            return Resp(json_body)
        return Resp(msi_body)
    return fake


def use(fake):
    urllib.request.urlopen = fake


def stub_win():
    """the smallest body _msi_handoff/_check_updates can live on -
    after() fires inline (the thread shim below runs workers on the
    spot), the status widget records its sentences."""
    class Status:
        text = None

        def configure(self, text=None):
            Status.text = text
    win = types.SimpleNamespace(
        _update_flight=False, saved=0, events=[],
        update_status=Status(),
        after=lambda ms, fn: fn() or 0,        # the marshal fires on
        monitor=types.SimpleNamespace(         # the spot
            events=types.SimpleNamespace(put=lambda e:
                                         win.events.append(e))),
        _save_now=lambda: setattr(win, "saved", win.saved + 1))
    for name in ("_check_updates", "_update_status_line",
                 "_msi_handoff", "_msi_done", "_update_now"):
        setattr(win, name, types.MethodType(
            getattr(_GeneralMixin, name), win))
    return win


from panelboss.ui.window._general import _GeneralMixin           # noqa: E402

# ---- 1) the release json: tag strips, only the -user.msi counts --
use(route(release("v0.3.3")))
rel = update.latest_release()
assert rel == {"version": "0.3.3", "url": ASSET_URL,
               "asset": "PanelBoss-0.3.3-user.msi"}, rel
url, timeout = CALLS[-1]
assert url == API and timeout == 5, CALLS[-1]        # the 5 s promise
use(route(release("0.3.3")))
assert update.latest_release()["version"] == "0.3.3"  # bare tag rides
use(route(release("v0.3.3", names=("src.zip", "src.msi"))))
try:
    update.latest_release()
    raise AssertionError("a release without a -user.msi must raise")
except ValueError:
    pass
print("ok - release json: v-strip, msi rule, honest raise")

# ---- 2) the version table: ints, not strings; unequal counts ----
table = [("0.3.2", "0.3.2", False), ("0.4", "0.3.2", True),
         ("10.0", "9.9.9", True), ("0.3.3", "0.3.2", True),
         ("0.3", "0.3.0", False), ("0.3.2", "0.3.3", False),
         ("junk", "1.0", False), ("1.0", "junk", True)]
for a, b, want in table:
    assert update.is_newer(a, b) is want, (a, b, want)
print("ok - version table (int compare, zero fill, junk-safe)")

# ---- 3) the error line: URLError is a sentence, not a raise; and
#         4) behind/current + the stored url that outlives a flaky API
update._LAST = None
use(route(urllib.error.URLError("no route to host")))
assert update.check() == ("error", None)
assert update.stored_release() is None, "a blank check stores nothing"
use(route(release("v0.3.3")))
assert update.check() == ("behind", "0.3.3")
assert update.stored_release()["url"] == ASSET_URL, "the retry's lifeline"
use(route(release("v0.3.2")))
assert update.check("0.3.2") == ("current", "0.3.2")
assert update.stored_release() is None, "current clears the store"
print("ok - error lane + behind/current + the stored url")

# ---- 5) the download: the dir appears, PRIOR *.msi leaves, txt stays
old_dir = os.path.join(TMP, "drop")
os.makedirs(old_dir)
stale = os.path.join(old_dir, "PanelBoss-0.3.1-user.msi")
open(stale, "wb").write(b"old")
keeper = os.path.join(old_dir, "notes.txt")
open(keeper, "w").write("keep")
path = update.download(ASSET_URL, old_dir)
assert path == os.path.join(old_dir, "PanelBoss-0.3.3-user.msi"), path
assert not os.path.exists(stale), "one-file-cheap: the prior msi left"
assert os.path.exists(keeper), "only *.msi answers to the sweep"
assert open(path, "rb").read() == b"MSIDATA"
print("ok - download: one-file-cheap, named for the asset")

# ---- 6) the apply.bat content pins (the bat the frozen copy earns) -
text = update.apply_text(r"C:\u\PanelBoss-0.3.3-user.msi",
                         r"C:\p\PanelBoss.exe", 1234, r"C:\u\update.log")
assert 'tasklist /fi "PID eq 1234"' in text, "waits on the dying pid"
assert "if %tries% geq 15" in text and "ping -n 3" in text, \
    "2 s cadence, 30 s cap - the bat's OWN ping idiom"
assert '/qn' in text and '/l*v' in text, "silent install, receipt stays"
launch = ('start "PanelBoss" "C:\\p\\PanelBoss.exe"')
assert launch in text, "relaunch mirrors update.bat's line"
assert "--autostart" not in text, \
    "update.bat:48 carries no stamp (a relaunch is not a login) - \
mirrored: none here either"
assert 'del "%~f0"' in text, "one-shot: it deletes itself"
# THE STORE FIRST (owner law, Oct-24): both handoff paths back the
# store up before anything installs or pulls. The placement IS the
# pin: the copies sit AFTER the :install label (both goto paths pass
# them - a pre-label insert the `goto install` jumps over would be
# dead code on the normal death path, the deviation the dossier's
# literal wording hides) and BEFORE msiexec; one echo names the
# folder into the console; update.bat mirrors the lines before its
# git pull.
i_lab = text.find(":install")
assert i_lab > 0 and i_lab < text.find("%bkdir%\\profiles.json.bak") \
    < text.find("%bkdir%\\config.toml.bak") < text.find("msiexec /i "), \
    "the backup must sit after the label (both goto paths) and " \
    "before the install verb"
assert 'echo store backed up to %bkdir%' in text, \
    "the echo naming the backup folder is gone"
ub = open(os.path.join(os.path.dirname(os.path.dirname(
             os.path.abspath(__file__))), "update.bat"),
          encoding="utf-8").read()
assert "%bkdir%\\profiles.json.bak" in ub and \
    "%bkdir%\\config.toml.bak" in ub, "the mirror lines left update.bat"
assert ub.find("config.toml.bak") < ub.find("git pull"), \
    "the mirror must back up BEFORE the pull moves the ground"

# GATE ROUND 2 (Oct 25): the host bundle copy list is SIX files - the
# five under extension\host plus the extension manifest at
# dist\<exe>\extension\manifest.json (derive_unpacked_id's key branch;
# the store-id fallback is rung three, but the bundle must not NEED
# the fallback). An unlisted file ships as absence - the silent-drop
# class - so the list is parsed, not admired.
ob = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "build_onedir.ps1"), encoding="utf-8").read()
for _f in ("install_host.ps1", "panelboss_host.py", "webrect.py",
           "panelboss-host.exe", "host-manifest.template.json"):
    assert "'%s'" % _f in ob, "the host bundle copy lost %s" % _f
assert "'extension\\manifest.json'" in ob, \
    "the extension manifest left the bundle copy (id derivation dies)"
assert ob.index("'extension\\manifest.json'") < ob.index("onedir ready"), \
    "the manifest copy must precede the build's ready line"
# DOSSIER G, CLOSED IN THE PACKAGER (Oct 25): the tray art must
# ride the bundle or the public build paints the interim circle
assert "--icon" in ob and "'assets\\panelboss.ico'" in ob, \
    "the exe lost its PB icon (the taskbar shows the no-icon tile)"
# the UpgradeCode family's one flag that makes a same-version
# reinstall REPLACE instead of coexist (three ghost installs,
# Oct 25, proved the hard way)
wx = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    os.pardir, "packaging", "msi",
                    "panelboss.wxs"), encoding="utf-8").read()
assert "AllowSameVersionUpgrades" in wx, \
    "same-version reinstalls land BESIDE the old copy without it"
import xml.etree.ElementTree as _ET
_ET.fromstring(wx)  # candle's parser is stricter, but a well-
                   # formedness gate stops whole classes of typo
assert '--version-file' in ob, \
    "the exe lost its version resource (Properties would lie blank)"
assert "'assets\\tray_master.png'" in ob, \
    "the tray art left the bundle - the public icon is the fallback"
assert ob.index("'assets\\tray_master.png'") < ob.index("onedir ready"), \
    "the art copy must precede the build's ready line"
# THE LOOSE .ICO (Oct 26): the exe's EMBEDDED icon styles only the
# file on disk; the taskbar tile is WM_SETICON, and Tk reads it from
# the loose .ico - an installed build without it logs 'not found' and
# paints the generic blue tile. Pinned as the two-file loop it is
# (the --icon flag line names the same path for the exe resource;
# the copy loop is a distinct string) plus the reader's frozen seam.
assert "'assets\\tray_master.png', 'assets\\panelboss.ico'" in ob, \
    "the loose-art copy is no longer the two-file loop " \
    "(no loose .ico = the blue tile returns)"
assert ob.index("'assets\\panelboss.ico'") < ob.index("onedir ready"), \
    "the .ico copy must precede the build's ready line"
_ic = open(os.path.join(os.path.dirname(os.path.dirname(
               os.path.abspath(__file__))),
               "panelboss", "ui", "window", "_icon.py"),
           encoding="utf-8").read()
assert "iconbitmap(default=path)" in _ic, \
    "the window lost its WM_SETICON call (the blue tile returns)"
assert '"wm", "iconbitmap", self._w' in _ic, \
    "the per-window WM_SETICON went class-only again - the taskbar " \
    "reads the window, not the class (measured: WM_GETICON 0x0)"
assert '("..", "..", "assets", "panelboss.ico")' in _ic, \
    "the reader lost its frozen seam - the shipped .ico would go unread"
assert "assets/panelboss.ico not found - the stock " in _ic \
    and "icon will do" in _ic, \
    "the once-warning line is gone (a silent icon miss is the old disease)"
print("ok - the onedir host bundle carries six files, manifest "
      "included, and the tray art AND the loose .ico ride _internal; "
      "_icon.py keeps the WM_SETICON call, the frozen seam, the words")
bat = update.write_apply(r"C:\u\PanelBoss-0.3.3-user.msi",
                         r"C:\p\PanelBoss.exe", 1234, os.path.join(TMP, "drop"))
assert bat == os.path.join(old_dir, "apply.bat") and os.path.exists(bat)
print("ok - apply.bat: waits-on-pid, /qn /l*v, unstamped relaunch, "
      "self-delete; the store (.bak pair) rides first, mirrored in "
      "update.bat before the pull")

# ---- 7) the FROZEN branch, simulated: fake sys.frozen + a LOCALAPPDATA
#         pointing into TMP; the spawn must be cmd.exe /c +
#         creationflags=0 (the ledger's second registered console line)
class InlineThread:
    def __init__(self, target=None, **kw):
        self._t = target

    def start(self):
        self._t()


G.threading = types.SimpleNamespace(Thread=InlineThread)   # workers on
real_popen = G.subprocess.Popen                            # the spot
popped = []
G.subprocess.Popen = lambda *a, **k: popped.append((a, k))
real_exe = sys.executable
real_lad = os.environ.get("LOCALAPPDATA")
sys.frozen = True
sys.executable = r"C:\p\PanelBoss.exe"
os.environ["LOCALAPPDATA"] = os.path.join(TMP, "lad")
try:
    use(route(release("v0.3.3")))
    w = stub_win()
    w._update_now()                        # kind-aware: frozen dispatch
    assert popped, "the frozen click spawned nothing"
    (args, kwargs), = popped
    bat_path = os.path.join(os.environ["LOCALAPPDATA"], "PanelBoss",
                            "update", "apply.bat")
    assert args == (["cmd.exe", "/c", bat_path], ), args
    assert kwargs.get("creationflags") == 0, "the declared console opt-out"
    assert kwargs.get("cwd") == os.path.dirname(bat_path)
    assert w.saved == 1, "the debounced save keeps its promise first"
    assert ("quit", True) in w.events, "then the quit event, source-style"
    msi = os.path.join(os.environ["LOCALAPPDATA"], "PanelBoss",
                       "update", "PanelBoss-0.3.3-user.msi")
    assert os.path.exists(msi), "the msi landed in the update dir"
    # and the 'current' click: no download, no quit, the row says so
    popped.clear()
    use(route(release("v0.3.2")))
    w2 = stub_win()
    w2._msi_handoff()
    assert not popped and not w2.events, "current must not quit"
    assert w2.update_status.text == "up to date (0.3.2)", \
        w2.update_status.text
    # the in-flight flag: while a round trip lives, clicks are ignored
    use(route(release("v0.3.3")))
    w3 = stub_win()
    w3._update_flight = True
    w3._msi_handoff()
    w3._check_updates()
    assert not popped and not w3.events, "one flight at a time"
finally:
    urllib.request.urlopen = REAL_OPEN
    G.subprocess.Popen = real_popen
    del sys.frozen
    sys.executable = real_exe
    if real_lad is not None:
        os.environ["LOCALAPPDATA"] = real_lad
    G.threading = __import__("threading")
shutil.rmtree(TMP, ignore_errors=True)
print("ok - frozen branch: cmd.exe /c + creationflags=0, save, quit;"
      " current stays; one flight")
print("UPDATE TESTS OK")
