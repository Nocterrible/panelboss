"""Package the companion extension for Chrome Web Store upload (Oct 16).

The store zip is the LOADABLE files only: manifest.json, background.js,
content.js, and icons/ once the art lands. The host/ tree is PanelBoss's
own install payload (the button ships it), README.md is store listing
prose - neither belongs in the crx. Files sit at the zip ROOT (the
store rejects a wrapping folder).

The manifest must carry "key" (the Oct 16 pin): without it the store
copy would get a publisher-derived id that no longer matches the
registry allow-list the install button writes. This script refuses -
not warns - a keyless manifest for exactly that reason.

Run:  .venv\\Scripts\\python.exe scripts\\package_extension.py
Out:  dist\\panelboss-companion-<version>.zip
"""
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "extension")
OUT = os.path.join(ROOT, "dist")

LOADABLE = ["manifest.json", "background.js", "content.js"]


def main():
    manifest_path = os.path.join(EXT, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    missing = [n for n in LOADABLE if not os.path.isfile(os.path.join(EXT, n))]
    if missing:
        sys.exit("refusing: loadable files missing from extension\\: "
                 + ", ".join(missing))
    if not manifest.get("key"):
        sys.exit("refusing: manifest carries no \"key\" - an unpinned "
                 "store copy gets a different id than the install "
                 "button registers (see companion_key.txt)")

    version = manifest["version"]
    os.makedirs(OUT, exist_ok=True)
    out_path = os.path.join(OUT, "panelboss-companion-%s.zip" % version)

    names = list(LOADABLE)
    icons = os.path.join(EXT, "icons")
    if os.path.isdir(icons):
        for png in sorted(os.listdir(icons)):
            if png.lower().endswith(".png"):
                names.append(os.path.join("icons", png).replace("\\", "/"))

    # the teeth go BEFORE the write: nothing host-shaped or pem-shaped can
    # enter the name list in the first place (the reviewer caught that an
    # after-the-fact assert would only be asserting the whitelist back)
    for name in names:
        assert "host/" not in name and not name.endswith(".pem"), name

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            z.write(os.path.join(EXT, *name.split("/")), name)

    print("wrote", out_path)
    print("contains:", ", ".join(names))
    print("store id (permanent, key-pinned):",
          __import__("panelboss.nmhost", fromlist=["x"])
          .derive_key_id(EXT))


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    main()
