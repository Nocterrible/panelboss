"""The checkbox contract, faked: tick ON => the task EXISTS (verified by
query even when every exit code is a liar); tick OFF => the task is
GONE. Regression: the user's revert-bug was trusting rc over reality."""
import sys
import types

sys.path.insert(0, r"F:\Projects\ICU-PresenceDetector")
from awaywatch import power


class R:
    returncode = 0


def make_fakes(state):
    def fake_run(args, timeout=15):
        r = R()
        verb = args[1] if len(args) > 1 else ""
        if verb == "/Query":
            r.returncode = 0 if state["installed"] else 1
            return r
        if verb == "/Create":
            r.returncode = state.get("create_rc", 1)
            if r.returncode == 0:
                state["installed"] = True
            return r
        if verb == "/Delete":
            r.returncode = state.get("delete_rc", 0)
            if r.returncode == 0:
                state["installed"] = False
            return r
        if verb == "/Run":
            return r
        return r

    def fake_elevate(args):
        # PowerShell lost the handle; who cares. If the scenario says
        # the elevation would have created/deleted it, the store moves.
        if args[0] == "/Create" and state.get("elev_creates"):
            state["installed"] = True
        if args[0] == "/Delete" and state.get("elev_deletes"):
            state["installed"] = False
    return fake_run, fake_elevate


def scenario(state, expect_ok, expect_gone=None, label=""):
    power.CHECK_SEC = 0.05
    power.CONFIRM_TIMEOUT = 2
    power.REMOVE_TIMEOUT = 2
    real_run, real_elev, real_start = power._run, power._need_elevation, power._start
    power._start = lambda: (True, "started")
    fr, fe = make_fakes(state)
    power._run, power._need_elevation = fr, fe
    try:
        if "delete_rc" in state or state.get("start_installed"):
            state.setdefault("installed", True)
            ok, msg = power.uninstall()
            gone = not state["installed"]
        else:
            ok, msg = power.install()
            gone = None
        assert ok == expect_ok, "%s: ok=%s msg=%s" % (label, ok, msg)
        if gone is not None and expect_gone is not None:
            assert gone == expect_gone, label
    finally:
        power._run, power._need_elevation = real_run, real_elev
        power._start = real_start
    print("scenario OK:", label, "->", msg)


# 1) the user's bug: direct refused, elevation created it, but rc lied
scenario({"installed": False, "create_rc": 1, "elev_creates": True},
         True, label="on: refused rc but task really exists -> stays ON")

# 2) genuinely refused: task never appears -> flips back OFF
scenario({"installed": False, "create_rc": 1}, False,
         label="on: nobody confirmed -> flips back OFF")

# 3) app elevated: direct create just works, no elevation
scenario({"installed": False, "create_rc": 0}, True,
         label="on: elevated app, direct create -> ON")

# 4) off: delete succeeds -> task gone
scenario({"delete_rc": 0, "start_installed": True}, True,
         expect_gone=True, label="off: delete verified gone")

# 5) off: delete refused everywhere -> stays installed
scenario({"delete_rc": 1, "start_installed": True}, False,
         expect_gone=False, label="off: delete refused -> task stays")

print("ALL TASK CONTRACT TESTS OK")
