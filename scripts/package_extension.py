"""Package the companion extension for Chrome Web Store upload.

The store zip is the LOADABLE files only: manifest.json, background.js,
content.js, and icons/ once the art lands. The host/ tree is PanelBoss's
own install payload (the button ships it), README.md is store listing
prose - neither belongs in the crx. Files sit at the zip ROOT (the
store rejects a wrapping folder).

ID STABILITY (the Oct 17 store lesson - the paperwork, not the plan,
was wrong): the repo manifest carries "key" (the public half) so an
UNPACKED dev load derives the SAME id the install button registers. But
the store REJECTS a "key" field on the FIRST upload - it wants the
PRIVATE key instead, as a file named key.pem at the zip root; it then
derives the id from THAT key (the same key), so the published id equals
the predicted feolhiok... This script: strips "key" from the zip's
manifest COPY, adds key.pem (the private half), and leaves the repo
manifest's key intact for dev. The private pem is the sole artifact this
build reads from the gitignored host/ dir - the store owns the private
key after first upload, so key.pem rides only on the FIRST submission
(a --reupload flag omits it for later versions).

Run:  .venv\\Scripts\\python.exe scripts\\package_extension.py [--reupload]
Out:  dist\\panelboss-companion-<version>.zip
"""
import json
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "extension")
OUT = os.path.join(ROOT, "dist")
PRIVATE = os.path.join(EXT, "host", "companion_private_key_pkcs8.pem")

LOADABLE = ["manifest.json", "background.js", "content.js"]
DESC_MAX = 132      # the store's own cap on the manifest description


def main():
    reupload = "--reupload" in sys.argv
    manifest_path = os.path.join(EXT, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    missing = [n for n in LOADABLE
               if not os.path.isfile(os.path.join(EXT, n))]
    if missing:
        sys.exit("refusing: loadable files missing from extension\\: "
                 + ", ".join(missing))
    if "key" not in manifest:
        sys.exit("refusing: repo manifest carries no \"key\" - unpacked "
                 "dev loads get a path-derived id that no longer matches "
                 "the install button (see companion_key.txt)")
    if len(manifest.get("description", "")) > DESC_MAX:
        sys.exit("refusing: manifest description is %d chars, the store "
                 "caps at %d" % (len(manifest["description"]), DESC_MAX))
    if not reupload and not os.path.isfile(PRIVATE):
        sys.exit("refusing: first upload needs the private key at "
                 "%s to ship as key.pem (pass --reupload if the item "
                 "already exists in the store)" % PRIVATE)

    version = manifest["version"]
    os.makedirs(OUT, exist_ok=True)
    out_path = os.path.join(OUT, "panelboss-companion-%s.zip" % version)

    names = list(LOADABLE)
    icons = os.path.join(EXT, "icons")
    if os.path.isdir(icons):
        for png in sorted(os.listdir(icons)):
            if png.lower().endswith(".png"):
                names.append(os.path.join("icons", png).replace("\\", "/"))
    if not reupload:
        names.append("key.pem")

    # the teeth BEFORE the write: nothing host-shaped may enter; the
    # ONLY .pem allowed is the root key.pem (the store's first-upload
    # id mechanism) - the private key never travels any other way.
    for name in names:
        assert "host/" not in name, name
        assert name == "key.pem" or not name.endswith(".pem"), name

    # the zip's manifest COPY has the key stripped (the store rejects
    # it on first upload); the repo file keeps it for unpacked dev.
    zip_manifest = {k: v for k, v in manifest.items() if k != "key"}

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            if name == "manifest.json":
                z.writestr("manifest.json",
                           json.dumps(zip_manifest, indent=2) + "\n")
            elif name == "key.pem":
                z.write(PRIVATE, "key.pem")
            else:
                z.write(os.path.join(EXT, *name.split("/")), name)

    print("wrote", out_path)
    print("contains:", ", ".join(names))
    print("mode:", "REUPLOAD (no key.pem - store already has the key)"
          if reupload else "FIRST UPLOAD (key.pem included)")
    print("store id (from key.pem = predicted):",
          __import__("panelboss.nmhost", fromlist=["x"])
          .derive_key_id(EXT))


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    main()
