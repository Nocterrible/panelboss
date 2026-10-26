"""THE APP ICON (owner art, Oct 19).

assets/panelboss.ico - drawn by scripts/make_icon.py from the owner's
master art - is the window's titlebar and taskbar icon. The TRAY stays
the live state circle by law (theme.py's status chips are "kept in
step with the tray icon meaning" - the 3-meter signal is the color,
the brand belongs to the window).

THE FEATHER PROBLEM (the gate caught what the docs promised, then the
vendored source confirmed - ctk_toplevel.py:68-70,208-215 of the
shipped 6.0.0): customtkinter re-mints ITS OWN feather onto every
CTkToplevel 200 ms after birth, unless that instance's own iconbitmap
was called first (the _iconbitmap_method_called flag is the veto).
The app has six toplevels (wizard, overrides, deprompt, sleep prompt,
two profile dialogs) - so _brand_toplevels() patches the class once:
every CTkToplevel brands itself with the owner art at birth, and the
200 ms feather pass finds the veto set and steps aside. The root
CTk needs no patch (its iconbitmap(default=...) sets its flag
synchronously); plain tk.Toplevels (veils, the help tip) have no
titlebar to brand and ride Tk's own default-icon rule untouched.

Fail-open with words: a missing .ico logs its absence ONCE (an app is
not a poster - no art, no crash) and the stock feather keeps its
place. THE FROZEN SEAM, landed (Oct 26): build_onedir copies the
loose assets\panelboss.ico into _internal\panelboss\assets beside the
tray master, and the third candidate below reads it. Until that copy
shipped, every installed build logged 'not found' and the taskbar
wore the generic blue tile - the exe's embedded resource only styles
the FILE on disk; WM_SETICON needs the loose file at runtime. And
-default alone was not enough either: it brands the CLASS, invisible
to cross-process readers - the per-window call below is what the
taskbar actually sees.
"""
import logging
import os

import customtkinter as ctk

log = logging.getLogger("ui")

_CANDIDATES = (
    ("..", "..", "..", "assets", "panelboss.ico"),   # dev tree: this
                                                # file sits three deep
                                                # (panelboss/ui/window)
                                                # - up thrice is the
                                                # repo root, where the
                                                # committed asset lives
    ("assets", "panelboss.ico"),                  # a package dir kept
                                                # beside this module
                                                # (belt; the frozen
                                                # seam is the MSI's)
    ("..", "..", "assets", "panelboss.ico"),    # frozen build (MSI):
                                                # _internal\panelboss\
                                                # ui\window up twice is
                                                # _internal\panelboss -
                                                # where build_onedir
                                                # copies the loose art
                                                # beside the tray
                                                # master (Oct 26)
)

_BRAND = None                 # the path the toplevel patch brands
_PATCHED = False              # class patch is once-per-process


def _brand_toplevels():
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True
    orig = ctk.CTkToplevel.__init__

    def __init__(self, *args, **kwargs):
        orig(self, *args, **kwargs)
        if _BRAND:
            try:
                # the call itself sets CTk's veto flag (its own
                # iconbitmap override); the feather pass at +200 ms
                # will find it True and mint nothing.
                self.iconbitmap(_BRAND)
            except Exception:
                pass        # a toplevel without art is the stock
                            # icon, loudly decided at the root already

    ctk.CTkToplevel.__init__ = __init__


class _IconMixin:

    def _set_app_icon(self):
        global _BRAND
        here = os.path.dirname(os.path.abspath(__file__))
        for rel in _CANDIDATES:
            path = os.path.join(here, *rel)
            if not os.path.isfile(path):
                continue
            try:
                # a .ico is not a photo image: the wm_iconphoto default
                # path would raise "should be image name" (measured);
                # iconbitmap is the Windows call the format is made for.
                self.iconbitmap(default=path)
                # THE TASKBAR NEEDS THE WINDOW, NOT THE CLASS (measured
                # Oct 26): -default lands on the window CLASS, and
                # cross-process readers (explorer's taskbar, my probe)
                # see WM_GETICON 0 and GetClassLongPtr 0 for a foreign
                # window's class icons. The per-window call sends the
                # real WM_SETICON on the root: the tile chain resolves.
                # Same path, so Tk loads the same .ico; the -default
                # above still sets the veto flag and brands future
                # toplevels (the class patch covers CTkToplevels).
                self.tk.call("wm", "iconbitmap", self._w, path)
                # the marker: Tk's query form for the app-default is
                # Tcl-version moody (a bare query answers '' even when
                # the default IS set - measured Oct 19), so the boot
                # pin reads THIS, plus the file; the real proof is the
                # titlebar the user looks at.
                self._app_icon_path = path
                _BRAND = path
                _brand_toplevels()
                log.info("app icon set from %s - the feather's late "
                         "pass is vetoed class-wide", path)
                return
            except Exception:
                log.warning("the icon refused to set from %s - "
                            "the stock icon keeps its place", path)
                return
        log.warning("assets/panelboss.ico not found - the stock "
                    "icon will do (make_icon.py can rebuild it)")
