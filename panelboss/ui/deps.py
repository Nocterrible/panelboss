"""Ask-before-install: a feature that needs an optional package
(whircam today) should not fail quietly into the log - it says what
it needs and offers the one button that gets it: the same updater the
update-now button drives, with the deps argument, and the same
relaunch promise. The app closes for the moment pip needs (its own
files are what change) and reopens with the feature live; the window
says exactly that, because an unannounced restart is a broken
promise, not a surprise."""

from . import theme
import customtkinter as ctk


class Deprompt(ctk.CTkToplevel):

    def __init__(self, parent, skin, feature, package, why, on_install):
        super().__init__(parent)
        self.title("%s wants %s" % (feature, package))
        self.resizable(False, False)
        self.configure(fg_color=skin.bg)
        self.transient(parent)           # stays above the settings
        ctk.CTkLabel(self, text="%s needs %s" % (feature, package),
                     font=skin.font(15, "bold"),
                     **skin.text_style()).pack(anchor="w", padx=theme.S_SECTION,
                                               pady=(theme.S_SECTION, 0))
        ctk.CTkLabel(self, text=why, font=skin.font(12), wraplength=380,
                     justify="left", anchor="w",
                     **skin.text_style("sub")).pack(anchor="w",
                                                    padx=theme.S_SECTION,
                                                    pady=(theme.S_ROW, 0))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=theme.S_SECTION, pady=(theme.S_SECTION, theme.S_SECTION))
        self._on_install = on_install
        ctk.CTkButton(row, text="update & restart",
                      command=self._go, **skin.primary()).pack(
            side="right", padx=(theme.S_ROW, 0))
        ctk.CTkButton(row, text="not now", command=self._retire,
                      **skin.secondary()).pack(side="right")
        self.update_idletasks()
        # the measured activation trick from the overrides window:
        # Windows yanks focus back to the parent right after a toplevel
        # maps, and the topmost-blink is what wins the round
        self.after(30, self._claim_focus)

    def _retire(self):
        # scheduled destroy (owner crash law, the wizard-crash sweep):
        # never from the button's own stack - withdraw now, destroy
        # on the event loop's clean stack
        self.withdraw()
        self.after(0, self.destroy)

    def _go(self):
        job = self._on_install
        self._retire()
        if job:
            job()

    def _claim_focus(self):
        try:
            self.attributes("-topmost", True)
            self.lift()
            self.focus_force()
            self.after(140, self._drop_topmost)
        except Exception:
            pass                             # closed inside 30 ms

    def _drop_topmost(self):
        try:
            self.attributes("-topmost", False)
        except Exception:
            pass
