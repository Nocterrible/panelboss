"""config writer round-trip: non-empty dicts and backslash-heavy
paths must survive write -> read (the 2026-10-10 lesson: str(dict)
wrote single quotes, tomli choked, next boot reset every setting;
and the old string escaper never escaped backslashes, so Windows
exe paths were bombs too)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
from panelboss import config  # noqa: E402

cfg = config.get_config(verbose=False)
cfg.setdefault("gaming", {})
cfg["gaming"]["game_hz"] = {"IOC912B": 240, "CMT 2704": "auto"}
cfg["gaming"]["games"] = ["palworld.exe"]
cfg.setdefault("tweaks", {})
cfg["tweaks"]["fso_apps"] = [r"F:\Games\Palworld\Palworld.exe"]
dirpath = os.path.join(tempfile.gettempdir(), "rt_config_dir")
os.makedirs(dirpath, exist_ok=True)
path = config.find_config(dirpath)     # whatever filename the
try:                                   # loader actually looks for
    os.remove(path)
except OSError:
    pass
config.write_config(cfg, path)
back = config.get_config(dir=dirpath, verbose=False)
assert back["gaming"]["game_hz"] == {"IOC912B": 240,
                                     "CMT 2704": "auto"}, \
    back["gaming"]["game_hz"]
assert back["gaming"]["games"] == ["palworld.exe"]
assert back["tweaks"]["fso_apps"] == [
    r"F:\Games\Palworld\Palworld.exe"], back["tweaks"]["fso_apps"]
# per-camera mode tables + wear-guard keys must round-trip: in memory
# {int: mode}, on disk string keys inside [camera.on]/[camera.off]
# sub-tables; a nested dict (gaming.game_hz) now also takes the
# sub-table shape
cfg["camera"]["on"] = {2: "always_on", 3: "boot_per_poll"}
cfg["camera"]["off"] = {4: "off"}
cfg["camera"]["always_timeout_sec"] = 3600
cfg["camera"]["always_fallback_poll_sec"] = 10
config.write_config(cfg, path)
with open(path, encoding="utf-8") as f:
    text = f.read()
assert "[camera.on]" in text, text
assert "[camera.off]" in text, text
assert "[gaming.game_hz]" in text, text
back2 = config.get_config(dir=dirpath, verbose=False)
assert back2["camera"]["on"] == {2: "always_on", 3: "boot_per_poll"}, \
    back2["camera"]["on"]
assert back2["camera"]["off"] == {4: "off"}, back2["camera"]["off"]
assert back2["camera"]["always_timeout_sec"] == 3600, \
    back2["camera"]["always_timeout_sec"]
assert back2["camera"]["always_fallback_poll_sec"] == 10, \
    back2["camera"]["always_fallback_poll_sec"]
# an empty table is dropped on write and reads back as the default {}
cfg["camera"]["on"] = {}
cfg["camera"]["off"] = {}
config.write_config(cfg, path)
with open(path, encoding="utf-8") as f:
    text = f.read()
assert "[camera.on]" not in text, text
assert "[camera.off]" not in text, text
back3 = config.get_config(dir=dirpath, verbose=False)
assert back3["camera"]["on"] == {} and back3["camera"]["off"] == {}, \
    (back3["camera"]["on"], back3["camera"]["off"])
print("ok - dict + backslash round-trip survives write/read")
print("ok - camera mode tables + wear-guard keys round-trip")
os.remove(path)
print("CONFIG WRITER TESTS OK")
