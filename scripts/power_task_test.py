"""The checkbox contract, faked, against the CURRENT power.py seams
(_run, _elevate_ps, _poll on task_installed): tick ON => the task
EXISTS (verified by query even when every exit code is a liar); tick
OFF => the task is GONE. Regression: the original revert-bug was
trusting rc over reality."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelboss import power


class R:
    def __init__(self, rc):
        self.returncode = rc


def make_fakes(state):
    def fake_run(args, timeout=15):
        verb = args[1] if len(args) > 1 else ""
        if verb == "/Query":
            return R(0 if state["installed"] else 1)
        if verb == "/Delete":
            rc = state.get("delete_rc", 0)
            if rc == 0 and not state.get("lie"):
                state["installed"] = False
            return R(rc)
        return R(0)

    def fake_elevate_ps(body, name="x"):
        if "/Create" in body:
            if state.get("elev_creates"):
                state["installed"] = True
        if "/Delete" in body:
            if state.get("elev_deletes"):
                state["installed"] = False
        return state.get("elev_ok", True)
    return fake_run, fake_elevate_ps


def scenario(state, expect_ok, expect_gone=None, label=""):
    power.CHECK_SEC = 0.02
    power.CONFIRM_TIMEOUT = 1
    power.REMOVE_TIMEOUT = 1
    state.setdefault("installed", False)
    real_run, real_elevate, real_start = (power._run, power._elevate_ps,
                                          power._start)
    power._start = lambda: (True, "started")
    power._run, power._elevate_ps = make_fakes(state)
    try:
        if "delete_rc" in state:
            state["installed"] = True
            ok, msg = power.uninstall()
            gone = not state["installed"]
        else:
            ok, msg = power.install()
            gone = None
        assert ok == expect_ok, "%s: ok=%s msg=%s" % (label, ok, msg)
        if not ok:
            assert "dministrator privileges" in msg, msg
        if expect_gone is not None:
            assert gone == expect_gone, label
    finally:
        power._run, power._elevate_ps = real_run, real_elevate
        power._start = real_start
    print("scenario OK:", label, "->", msg)


# 1) the classic machine: elevation handed off, task really appears
scenario({"elev_creates": True}, True,
         label="on: elevated handoff created it -> stays ON")

# 2) consent refused/cancelled: the store never moves -> flips back OFF
scenario({}, False, label="on: nobody confirmed -> flips back OFF")

# 3) the handoff itself failed (ShellExecuteW <= 32) -> OFF fast
scenario({"elev_ok": False, "elev_creates": True}, False,
         label="on: handoff refused -> OFF without waiting")

# 4) off: direct delete verified gone
scenario({"delete_rc": 0}, True, expect_gone=True,
         label="off: delete verified gone")

# 5) off regression: rc says 0 but the store still has the task -
# must elevate and poll, not trust rc
scenario({"delete_rc": 0, "lie": True, "elev_deletes": True}, True,
         expect_gone=True, label="off: rc lied, store moved via elevate")

# 6) off refused everywhere: task survives -> error
scenario({"delete_rc": 1}, False, expect_gone=False,
         label="off: delete refused -> task stays, error shown")

print("ALL TASK CONTRACT TESTS OK")
