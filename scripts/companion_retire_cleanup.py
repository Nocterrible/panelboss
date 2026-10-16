"""Retire the companion opt-in's old shape off the owner's live config
(the file's own answer, not the in-memory default). The pre-ruling file
carried the enabled/flag_families pair (the debug-flag rail); v0.3
retired those keys - [videodim].on is the ONE consent now. This script
converges the file: on stays the owner's word, the retired keys drop.
config.set_value does not exist on this tip; the app's own writers
(ui, loops) all call write_config(cfg) after mutating the merged dict -
the same shape here."""
import sys
sys.path.insert(0, ".")
from panelboss import config

c = config.get_config(verbose=False)
vd = c.setdefault("videodim", {})
print("before:", {k: vd.get(k) for k in ("on", "enabled",
                                         "flag_families", "sites")})
vd.pop("enabled", None)          # the companion's retired opt-in rail
vd.pop("flag_families", None)    # the launch-with-port list (dead)
vd.pop("sites", None)            # the trusted-host list (dead)
vd["on"] = vd.get("on") is True  # the ONE consent, the owner's word
# normalize folds and clamps (min_rect_px, grace_s), keeps on
path = config.write_config(c)
print("saved:", path)
print("after:", {k: c["videodim"].get(k) for k in
                 ("on", "min_rect_px", "grace_s")})