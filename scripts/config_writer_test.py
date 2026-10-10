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
from awaywatch import config  # noqa: E402

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
print("ok - dict + backslash round-trip survives write/read")
os.remove(path)
print("CONFIG WRITER TESTS OK")
