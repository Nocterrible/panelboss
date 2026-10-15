"""One-shot backup of the live PanelBoss config, for this incident only.

The agent's scripted config edit corrupted the owner's file on Oct 15;
the app quarantined and rebuilt it from defaults, and the rebuild lost
keys. From now the app keeps its own dated .bak (config.py, this wave);
this script is the belt for the HUMAN/tool side: back the file up
before anyone touches it, and never write it with a regex.
"""
import io
import os
import shutil
import time

SRC = os.path.expandvars(r"%APPDATA%\PanelBoss\config.toml")
DST_DIR = os.path.expandvars(r"%LOCALAPPDATA%\PanelBoss-backups")


def main():
    if not os.path.exists(SRC):
        print("no config to back up at", SRC)
        return 1
    os.makedirs(DST_DIR, exist_ok=True)
    dst = os.path.join(DST_DIR, "config-%s.toml" % time.strftime(
        "%Y%m%d-%H%M%S"))
    shutil.copy2(SRC, dst)
    shutil.copy2(SRC, os.path.join(DST_DIR, "config-latest.toml"))
    print("backed up", SRC, "->", dst)
    print("and the rolling copy at", os.path.join(DST_DIR,
                                                  "config-latest.toml"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
