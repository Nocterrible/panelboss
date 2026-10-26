"""The README's own receipts: every figure the copy points at exists on
disk, and the two quoted promises stay verbatim.

A reader-facing 404 is a broken manual, and this suite is why it cannot
happen quietly. The pump label is the owner's words byte for byte; the
escape-hatch config word is the one sentence the theater paragraph
promises. Line wrapping is not wording, so the text is flattened before
the compare.

Run from repo root: python scripts/readme_test.py
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, "README.md")

with open(README, encoding="utf8") as fh:
    TEXT = fh.read()

FLAT = re.sub(r"\s+", " ", TEXT)

# ---- the figures: whatever the copy references has to be on disk --------
IMGS = re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", TEXT)
assert IMGS, "the README references no figures at all"
missing = [p for p in IMGS if not os.path.isfile(
    os.path.join(ROOT, p.replace("/", os.sep)))]
assert not missing, "README figure(s) missing on disk: %r" % (missing,)
print("ok - %d README figure path(s) resolve: %s"
      % (len(IMGS), ", ".join(IMGS)))

# ---- the quoted promises ------------------------------------------------
PUMP = ("Does your shit occasionally decide it wants to keep Windows awake?")
assert PUMP in FLAT, "the pump label left the README (owner words, verbatim)"
assert '[videodim] hole = "window"' in FLAT, \
    "the theater escape-hatch config word left the README"
print("ok - the pump label and the [videodim] hole word are verbatim")
print("README TESTS OK")
