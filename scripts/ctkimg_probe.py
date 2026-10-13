"""CTkLabel image-cycle probe - the wizard-preview freeze's regression
net (UAT find, Oct 13). CTkLabel.configure processes TEXT BEFORE
IMAGE (ctk_label.py:238/250), and the image=None branch leaves the
inner Tk label holding a dangling pyimage NAME after the Python
reference is dropped: a frame -> image=None -> frame cycle raises
TclError "image pyimageN doesn't exist" on the second frame's text
set. The wizard pump must therefore never blank a configured label;
the BUSY state travels in the note line. This probe pins that
conclusion to the installed CTk build - if the library ever fixes
the None branch, the probe says so (and only then may the workaround
move). No hardware, no window shown."""
import gc
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import customtkinter as ctk
import numpy as np
from PIL import Image

ctk.set_appearance_mode("dark")
root = ctk.CTk()
lbl = ctk.CTkLabel(root, text="init")


def img():
    a = Image.fromarray(np.random.randint(0, 255, (60, 80, 3), np.uint8))
    return ctk.CTkImage(light_image=a, dark_image=a, size=(80, 60))


hold = img()
lbl.configure(image=hold, text="")
print("[PASS] 1: first frame configures")
lbl.configure(image=None, text="BUSY")
print("[PASS] 2: image=None cycle survives the call itself")
del hold
gc.collect()
try:
    hold = img()
    lbl.configure(image=hold, text="")
except Exception as exc:
    if type(exc).__name__ == "TclError" and "doesn't exist" in str(exc):
        print("[PASS] 3: the dangling-name trap STILL fires on this CTk"
              " build - the note-line BUSY route in _camid is load-"
              "bearing, do not reintroduce image=None after a frame")
        root.destroy()
        sys.exit(0)
    print("[FAIL] unexpected error shape:", type(exc).__name__, exc)
    sys.exit(1)
print("[FAIL] the trap did NOT fire - CTk changed; _camid's workaround"
      " may now be simplified, and this probe must be re-thought, not"
      " silently left asserting the old world")
root.destroy()
sys.exit(1)
