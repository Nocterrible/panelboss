"""Crash receipts, offline: the Oct 19 WER Event 1000 (pythonw.exe
pid 23004, python310.dll+0x487d, 0xc0000005 - a native AV in the
camera-stack churn, no console, no dump, no atexit line) leaves a
word on every future death. Three pins, one scratch dir:
  (1) running the patched cli's boot (main(["config"]) - the receipt
      machinery lives in main) opens <LOG_DIR>\fault.log and enables
      faulthandler into it; a child that then takes
      faulthandler._sigsegv() - this 3.10.6 build ships _sigsegv, not
      _segv (probed) - exits nonzero and the file holds the
      Segmentation-fault / Thread 0x dump,
  (2) a child whose cli.main(["config"]) returns normally signs
      panelboss.log with "cli: panelboss exit pid=<its pid>" (the
      atexit receipt, silent-death dossier belt),
  (3) with a fake camera whose release() raises, posting
      camera_enabled False still leaves the toml written, and its
      mtime moved: the write-before-release order, pinned
      behaviorally (the vanished "No").
No real cameras, no wx. Run from repo root:
.venv\\Scripts\\python.exe scripts\\fault_receipt_test.py
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PY = sys.executable

scratch = tempfile.mkdtemp(prefix="panelboss-fault-")
# the test/belt surface: PANELBOSS_CONFIG_DIR wins over the APPDATA
# default at config.py:40 and the log dir derives from it at :42, so
# the whole config/log machinery boots inside the scratch dir and the
# owner's %APPDATA%\PanelBoss stays untouched
os.environ["PANELBOSS_CONFIG_DIR"] = scratch

CHILD = """
import os, sys, faulthandler
sys.path.insert(0, %r)
from panelboss import cli
from panelboss import config as cfg
rc = cli.main(["config"])            # boots the receipt machinery fully
assert rc == 0, rc                   # (faulthandler + atexit live in
assert cli._FAULT is not None, "faulthandler block never opened _FAULT"  # main)
assert os.path.realpath(cli._FAULT.name) == os.path.realpath(
    os.path.join(cfg.LOG_DIR, "fault.log")), cli._FAULT.name
faulthandler._sigsegv()               # the AV; the file is the witness
""" % (ROOT,)

CHILD_OK = """
import os, sys
sys.path.insert(0, %r)
from panelboss import cli
sys.exit(cli.main(["config"]))
""" % (ROOT,)


def test_segv_receipt():
    r = subprocess.run([PY, "-c", CHILD], capture_output=True, text=True,
                       env=dict(os.environ))
    assert r.returncode != 0, "the segv child survived: " + r.stderr[-400:]
    fault = os.path.join(scratch, "logs", "fault.log")
    assert os.path.exists(fault), "fault.log never appeared"
    text = open(fault, encoding="utf-8", errors="replace").read()
    assert re.search(r"Segmentation fault|Access violation", text), text
    assert re.search(r"[Tt]hread 0x[0-9a-fA-F]+", text), \
        "no thread id in the dump: " + text
    print("ok - segv left an Access violation receipt in fault.log")


def test_atexit_receipt():
    r = subprocess.run([PY, "-c", CHILD_OK], capture_output=True, text=True,
                       env=dict(os.environ))
    assert r.returncode == 0, "clean child died: " + r.stderr[-400:]
    plog = os.path.join(scratch, "logs", "panelboss.log")
    assert os.path.exists(plog), "the child's panelboss.log is missing"
    text = open(plog, encoding="utf-8", errors="replace").read()
    m = re.search(r"cli: panelboss exit pid=(\d+)", text)
    assert m, "no atexit receipt in panelboss.log"
    print("ok - the atexit receipt (pid %s) landed in the child's "
          "panelboss.log" % m.group(1))


def test_write_before_release():
    import panelboss.config as config
    assert config.CONFIG_DIR == scratch, config.CONFIG_DIR
    from panelboss.state import PresenceMonitor

    class Boom:
        """the dying hand: release() raises the way the 12:36 AV did"""

        def release(self):
            raise RuntimeError("the camera hand died mid-release")

    m = PresenceMonitor(config.get_config(), detector=None)
    m.camera = Boom()
    m.camera_cfg["enabled"] = True
    path = config.write_config(m.cfg)
    stamp = os.path.getmtime(path)
    m.events.put(("camera_enabled", False))
    try:
        m._drain_tray()
    except RuntimeError as exc:
        assert str(exc) == "the camera hand died mid-release", str(exc)
    else:
        raise AssertionError("the fake release death was swallowed")
    disk = open(path, encoding="utf-8").read()
    assert "enabled = false" in disk, \
        "the word never reached the toml: " + disk[:600]
    assert os.path.getmtime(path) > stamp, \
        "the toml predates the drain: release-before-write is back"
    print("ok - camera_enabled False: the toml was written BEFORE the "
          "dying release ran")


if __name__ == "__main__":
    test_segv_receipt()
    test_atexit_receipt()
    test_write_before_release()
    print("FAULT RECEIPT OK (3)")
