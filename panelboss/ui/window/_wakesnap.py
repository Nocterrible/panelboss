"""The "What woke the screens" dialog: the wake-frames ring's viewer
(feature, Oct 27). Built lazily on the button press, JPEGs decoded
only while it lives, destroyed on close - the dialog must never grow
the window's paint budget, so all of its weight is born here and
dies here (the pictures ride self._imgs and go with the widgets).

The who-woke-it text log lives on the camera card itself (free);
this pane adds the pictures, under [camera] wake_snap. Entries with
no jpg (input wakes, or a wake that predates the switch) caption
without art - no broken-image placeholder."""

from __future__ import annotations

import logging
import time

import cv2
import customtkinter as ctk
import numpy as np
from PIL import Image

from ... import wakesnap
from .. import theme
from ._scroll import ScrollHost

log = logging.getLogger("ui")

WIDTH = 320                       # the picture's width, the dial the
                                  # feature shipped on
SUB = ("Frames stay in memory only \u2014 never saved to disk, and gone "
       "when the app restarts.")
OFF_NOTE = "off \u2014 turn it on above to catch the next wake."
EMPTY_NOTE = "Nothing has woken the screens since the app started."


class WakeSnapDialog(ctk.CTkToplevel):
    def __init__(self, host):
        super().__init__(host)
        self._host = host
        self._imgs = []           # strong refs: the CTk trap the live
                                  # pane already knows (a bitmap without
                                  # an owner is a blank label)
        self.title("What woke the screens")
        self.configure(fg_color=host.skin.bg)
        self.transient(host)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(anchor="w", fill="x", padx=theme.S_SECTION,
                  pady=(theme.S_SECTION, 0))
        self.box = ctk.CTkCheckBox(
            head, text="keep the last five wake frames",
            command=self._toggled, font=host.skin.font(12),
            checkbox_width=18, checkbox_height=18,
            border_color=host.skin.border_raised,
            fg_color=host.skin.accent, hover_color=host.skin.accent,
            text_color=host.skin.text,
            text_color_disabled=host.skin.txt3)
        self.box.pack(anchor="w")
        self.box.set(bool(host.cfg["camera"].get("wake_snap")))
        ctk.CTkLabel(head, text=SUB, font=host.skin.font(11),
                     justify="left", anchor="w", wraplength=360,
                     **host.skin.text_style("sub")).pack(anchor="w",
                                                          pady=(2, 0))
        self._notice = ctk.CTkLabel(self, text="", font=host.skin.font(11),
                                    justify="left", anchor="w",
                                    wraplength=360,
                                    **host.skin.text_style("sub"))
        self._notice.pack(anchor="w", padx=theme.S_SECTION,
                          pady=(theme.S_ROW, 0))
        page = ScrollHost(self, bg=host.skin.bg, width=WIDTH + 60,
                          height=430)
        page.pack(anchor="w", fill="both", expand=True,
                  padx=theme.S_SECTION, pady=(theme.S_ROW, theme.S_ROW))
        entries = wakesnap.frames()
        for e in entries:
            row = ctk.CTkFrame(page.inner, fg_color="transparent")
            row.pack(anchor="w", pady=(theme.S_ROW, 0))
            if e["jpg"]:
                art = self._photo(e["jpg"])
                if art is not None:
                    self._imgs.append(art)
                    ctk.CTkLabel(row, image=art, text="").pack(anchor="w")
            # the caption the packet formatted: "22:10:29 - score 0.83
            # - desk"; an input wake has no score to wear, so its slot
            # says so rather than printing a fake 0.00 (the implication
            # lie the wake log itself fixed at the owner's desk)
            ctk.CTkLabel(row, text=self._caption(e),
                         font=host.skin.font(10),
                         **host.skin.text_style("sub")).pack(anchor="w")
        self._refresh_notice()

        def retire():
            # the _prof_apply law: destroy inside a live callback is the
            # double-destroy shape - withdraw now, die in the next turn
            self.withdraw()
            self.after(0, self.destroy)
        self.protocol("WM_DELETE_WINDOW", retire)

    def _toggled(self):
        on = bool(self.box.get())
        self._host._wake_snap_toggled(on)   # cfg write + set_enabled +
        #                              the window's debounced save
        self._refresh_notice()

    def _refresh_notice(self):
        """One row carries the pane's mood, in the packet's two shapes:
        the disabled word (it outranks the empty word - rows with no
        pictures under a dead switch are exactly what it explains),
        else the empty word, else quiet."""
        if not self.box.get():
            text = OFF_NOTE
        elif not wakesnap.frames():
            text = EMPTY_NOTE
        else:
            text = ""
        self._notice.configure(text=text)

    def _photo(self, jpg):
        arr = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            log.debug("wakesnap: a ring row refused to decode")
            return None                  # caption-only, the honest shape
        h = int(WIDTH * arr.shape[0] / max(arr.shape[1], 1))
        rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb).resize((WIDTH, h))
        # the live pane's own idiom (ctk.CTkImage over raw ImageTk):
        # the DPI scaling the window does everywhere rides it
        return ctk.CTkImage(light_image=img, dark_image=img,
                            size=(WIDTH, h))

    @staticmethod
    def _caption(e):
        score = ("score %.2f" % e["score"] if e["score"] is not None
                 else "no score")
        return "%s \u2014 %s \u2014 %s" % (
            time.strftime("%H:%M:%S", time.localtime(e["ts"])),
            score, e["cam"])
