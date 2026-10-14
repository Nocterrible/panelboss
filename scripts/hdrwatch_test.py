"""The amendment-8 offline suite: the PDH/pipe vocabulary (path
strings and the engine-family matcher, against the shapes MEASURED
on this box - no live counters), the mpv matcher truth table, the
hysteresis machine on a fake clock, the arm over faked senses, and
the type-16 migration-canary pins. No window, no counters, no
pipes, no driver: the suite that needs those is the live probe, not
this file. Run: .venv\\Scripts\\python.exe scripts\\hdrwatch_test.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PANELBOSS_CONFIG_DIR"] = tempfile.mkdtemp(
    prefix="panelboss_hdr_")

from panelboss import config                      # noqa: E402
from panelboss.wm import _hdr, _videostats as vs  # noqa: E402
from panelboss.state import _hdrwatch as hw       # noqa: E402

fails = []


def check(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# ---- 1) the counter vocabulary: strings, not syscalls -----------------
check(vs.OBJECT == "GPU Engine"
      and vs.COUNTER == "Utilization Percentage"
      and vs.COUNTER_PATH == "\\GPU Engine(%s)\\Utilization Percentage",
      "path table is the one measured on this desk (English path, "
      "locale-proof door)")
check(vs.MPV_PIPE_DEFAULT
      == config.DEFAULTS["hdr"]["mpv_pipe"],
      "the pipe default in _videostats IS the config default (one truth)")
# the matcher over the instance shapes measured here (NVIDIA glues
# the words, the iGPU spells them with spaces - one normalizer eats
# both) and the rejections the law demands
check(vs.is_video_instance(
    "pid_104676_luid_0x00000000_0x0001A1DF_phys_0_eng_1_"
    "engtype_VideoDecode"), "NVIDIA VideoDecode instance is video")
check(vs.is_video_instance(
    "pid_9_luid_0x0_0x1_phys_0_eng_9_engtype_video decode 1"),
    "iGPU 'video decode 1' (spaces) is video")
check(vs.is_video_instance(
    "pid_9_luid_x_phys_0_eng_3_engtype_VideoProcessing"),
    "VideoProcessing(4) is video")
check(not vs.is_video_instance(
    "pid_9_luid_x_phys_0_eng_8_engtype_VideoEncode"),
    "VideoEncode(3) is NOT: recording is not watching")
check(not vs.is_video_instance(
    "pid_9_luid_x_phys_0_eng_10_engtype_JPEG_Decode_3"),
    "JPEG decode is not a movie")
check(not vs.is_video_instance(
    "pid_9_luid_x_phys_0_eng_10_engtype_video codec 0"),
    "the vendor codec catch-all stays out (the law names 2 and 4)")
check(not vs.is_video_instance(
    "pid_9_luid_x_phys_0_eng_0_engtype_3D")
      and not vs.is_video_instance("pid_1_luid_x_eng_1_engtype_copy"),
    "3D and copy are not video")

# ---- 2) the mpv matcher truth table -----------------------------------
check(vs.mpv_is_hdr({"primaries": "bt.2020", "gamma": "pq"}),
      "bt.2020 + pq is HDR content")
check(vs.mpv_is_hdr({"primaries": "BT.2020", "gamma": "HLG"}),
      "case does not move the answer")
check(vs.mpv_is_hdr({"primaries": "bt2020", "gamma": "smpte-st-pq"}),
      "the dotted/undotted spellings both read (loose per mpv's own "
      "warning)")
check(not vs.mpv_is_hdr({"primaries": "bt.709", "gamma": "srgb"}),
      "SDR is not HDR")
check(not vs.mpv_is_hdr({"primaries": "bt.2020"}), "gamma missing -> no")
check(not vs.mpv_is_hdr({"gamma": "pq"}), "primaries missing -> no")
check(not vs.mpv_is_hdr({}), "no dict parts -> no")
check(not vs.mpv_is_hdr(None), "None (the dead pipe's answer shape) -> no")
check(vs.mpv_hdr_playing(r"\\.\pipe\panelboss-absent-"
                         + str(os.getpid())) is False,
      "a pipe nobody owns answers False inside its bounded wait")

# ---- 3) the hysteresis machine, fake-clocked --------------------------
E, R, st0 = hw.ENGAGE_SEC, hw.RELEASE_SEC, {}
st, w = hw.hdr_step(st0, 0.0, True, False)
check(w is None and st["busy_since"] == 0.0,
      "the first busy tick only starts the clock")
st, w = hw.hdr_step(st, 0.0 + E - 0.001, True, False)
check(w is None, "under ENGAGE_SEC of busy: no engage")
st, w = hw.hdr_step(st, 0.0 + E, True, False)
check(w is True, "ENGAGE_SEC of unbroken busy lights the panel")
st, w = hw.hdr_step(st, 100.0, True, True)
check(w is None, "held busy with the light on: silence, no re-issue")
st, w = hw.hdr_step(st, 101.0, False, True)
check(w is None and st["idle_since"] == 101.0,
      "one idle tick only starts the release clock")
st, w = hw.hdr_step(st, 101.0 + R - 0.001, False, True)
check(w is None, "under RELEASE_SEC of idle: the owner keeps HDR")
st, w = hw.hdr_step(st, 101.0 + R, False, True)
check(w is False, "RELEASE_SEC of quiet hands it back")
st, w = hw.hdr_step(st, 200.0, False, False)
check(w is None and st["idle_since"] is None,
      "dark and idle: the clocks rest")
st, w = hw.hdr_step(st0, 5.0, False, True)
check(w is None, "an idle tick never commands an already-off panel")
# a flicker inside ENGAGE_SEC resets the engage clock, not a light
st, _ = hw.hdr_step(st0, 0.0, True, False)
st, w = hw.hdr_step(st, 1.0, False, False)
check(w is None and st["busy_since"] is None,
      "a flinch clears the engage clock (a two-second stutter must "
      "not flicker a desktop)")

# ---- 4) the arm over faked senses (the tick, not the thread) ---------
class FakeWM:
    def __init__(self, rows):
        self.rows, self.sets = rows, []

    def hdr_states(self):
        return [dict(r) for r in self.rows]

    def hdr_set(self, gdi, on):
        self.sets.append((gdi, on))
        for r in self.rows:
            if r["gdi"] == gdi:
                r["state"] = "on" if on else "off"
        return ""


class FakeVS:
    busy = False
    playing = False
    reads = 0

    @staticmethod
    def video_busy():
        FakeVS.reads += 1
        return 60.0 if FakeVS.busy else 0.0

    @staticmethod
    def mpv_hdr_playing(pipe=None):
        FakeVS.reads += 1
        return FakeVS.playing


class Mon(hw._HdrWatchMixin):
    def __init__(self, cfg):
        self.cfg = cfg


fake_wm, fake_vs = hw.wm, hw._videostats
try:
    fw = FakeWM([{"gdi": r"\\.\DISPLAY9", "model": "ZZZ1",
                  "supported": True, "state": "off", "precise": True}])
    hw.wm, hw._videostats = fw, FakeVS
    m = Mon({"hdr": {"auto": {"ZZZ1": "video"}}})
    mst = {}
    FakeVS.busy = True
    m._hdr_tick(mst, 0.0)
    check(fw.sets == [] and mst["ZZZ1"]["busy_since"] == 0.0,
          "tick 0: the busy clock starts, no command")
    m._hdr_tick(mst, hw.ENGAGE_SEC)
    check(fw.sets == [(r"\\.\DISPLAY9", True)],
          "the arm commands the engage edge EXACTLY once")
    m._hdr_tick(mst, hw.ENGAGE_SEC + 1)
    check(len(fw.sets) == 1, "held busy: no repeat command")
    FakeVS.busy = False
    for t in range(int(hw.RELEASE_SEC)):         # 100.0 .. 129.0
        m._hdr_tick(mst, 100.0 + t)
    check(len(fw.sets) == 1,
          "idle UNDER RELEASE_SEC: the owner keeps the light")
    m._hdr_tick(mst, 100.0 + hw.RELEASE_SEC)
    check(fw.sets == [(r"\\.\DISPLAY9", True),
                      (r"\\.\DISPLAY9", False)],
          "the release edge commands once too")
    # a claimed-but-incapable panel: no clocks, no commands, no lies
    fw.rows = [{"gdi": r"\\.\DISPLAY9", "model": "ZZZ1",
                "supported": False, "state": "off", "precise": True}]
    mst2 = {}
    m._hdr_tick(mst2, 200.0)
    check(mst2 == {} and len(fw.sets) == 2,
          "incapable hardware: no clocks, no commands, no lies")
    # the default-off shape: an empty tier map reads NO senses
    fw.sets.clear()
    before = FakeVS.reads
    Mon({"hdr": {"auto": {}}})._hdr_tick({}, 0.0)
    Mon({})._hdr_tick({}, 0.0)
    check(FakeVS.reads == before and fw.sets == [],
          "no tiers claimed (the virgin default): zero sense reads")
    # the content tier end to end through the same machine
    fw.rows = [{"gdi": r"\\.\DISPLAY9", "model": "ZZZ1",
                "supported": True, "state": "off", "precise": True}]
    m = Mon({"hdr": {"auto": {"ZZZ1": "content"},
                     "mpv_pipe": r"\\.\pipe\tested"}})
    mst3 = {}
    FakeVS.playing = True
    m._hdr_tick(mst3, 0.0)
    m._hdr_tick(mst3, hw.ENGAGE_SEC)
    check(fw.sets == [(r"\\.\DISPLAY9", True)],
          "the player-ipc tier engages on the pipe's HDR answer")
finally:
    hw.wm, hw._videostats = fake_wm, fake_vs

# ---- 5) the type-16 migration canary ----------------------------------
check(_hdr.DCI_SET_HDR_STATE == 16,
      "the SET door is type 16 (24H2): the legacy type-10 fused "
      "enable is what windows-display-settings broke on")
import inspect                                          # noqa: E402
_src = inspect.getsource(_hdr.hdr_set)
check("DCI_SET_HDR_STATE" in _src
      and "DCI_SET_ADVANCED_COLOR_STATE" not in _src,
      "hdr_set references the type-16 door and never the type-10 one")

print("ALL-HDRWATCH-TESTS-OK" if not fails
      else "hdrwatch FAILED: %s" % fails)
sys.exit(1 if fails else 0)
