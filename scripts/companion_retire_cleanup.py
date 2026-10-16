"""Flip the companion opt-in off the way the app would (the file's own
answer, not the in-memory default). config.set_value does not exist on
this tip; the app's own writers (ui, loops) all call write_config(cfg)
after mutating the merged dict - the same shape here. videodim is the
real opt-in rail (no 'companion' section on this tip), and 'on' is its
consent key."""
import sys
sys.path.insert(0, ".")
from panelboss import config

c = config.get_config(verbose=False)
print("before:", {k: c["videodim"].get(k) for k in ("enabled", "on",
                                                    "flag_families")})
c["videodim"]["enabled"] = False        # the companion's opt-in rail
c["videodim"]["on"] = False             # the app's consent key (same
                                        #   rail, the pre-companion
                                        #   shape of the section)
c["videodim"]["flag_families"] = []     # zero families flagged
path = config.write_config(c)
print("saved:", path)
