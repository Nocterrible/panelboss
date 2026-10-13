"""Skins: the seam between how the window looks and what it does.

A Skin is only a palette plus the style kwargs window.py asks each
widget for; layout and behavior never live here. That is deliberate:
the fun skin gets designed later and should need exactly one file to
change - this one - not a rewrite of the window.

CTk resolves colors by the appearance mode, so a single hex applies to
light and dark alike; each skin picks the mode it wants. box_bgr is the
detection-box color for the debug preview (cv2 wants BGR), so the fun
skin can draw pink boxes without window.py knowing.
"""

from __future__ import annotations

from dataclasses import dataclass

import logging

import customtkinter as ctk

log = logging.getLogger("theme")

# ------------------------------------------------- design-system tiers --
# docs/UI-PLAN.md "Design system" (UI-1c): three surfaces, one accent,
# four spacing numbers. THE single source - call sites take these names
# (raw hexes here and nowhere else); a missing name raises at import,
# loud, there is no silent fallback.
PAGE = "#17181A"           # window background
CARD = "#202123"           # card / frame fill
RAISED = "#2A2C2F"         # buttons, fields, combo faces
BORDER_CARD = "#141517"    # card border: one step DARKER than the card
BORDER_RAISED = "#3A3D41"  # raised-control border and hover: LIGHTER
ACCENT = "#2dd6a6"         # the shipped green - active tab, primary
                           # button, selected state; the ONLY accent
ACCENT_HOVER = "#25b890"   # accent's own press shade (accent-derived)
ON_ACCENT = "#10131a"      # dark ink on accent fills (accent-derived)
TXT_1 = "#e7e9ea"          # primary text
TXT_2 = "#a0a4a8"          # secondary: hints, unit labels, status lines
TXT_3 = "#6b6e72"          # disabled
# the only four layout numbers in the UI (label->value, row, section,
# page) - shared by both skins: this is layout, not palette
S_PAGE, S_SECTION, S_ROW, S_FIELD = 24, 16, 8, 4


@dataclass
class Skin:
    key: str
    label: str                       # name shown in the skin picker
    mode: str = "dark"               # CTk appearance mode
    # palette (the defaults ARE the modern skin's design-system tiers)
    bg: str = PAGE                   # window background
    panel: str = CARD                # card / frame fill
    border: str = BORDER_CARD        # card border, one step darker
    border_raised: str = BORDER_RAISED   # raised controls, one lighter
    text: str = TXT_1
    subtext: str = TXT_2
    txt3: str = TXT_3                # disabled tier
    accent: str = ACCENT             # primary button, switch on
    accent_hover: str = ACCENT_HOVER
    on_accent: str = ON_ACCENT       # text drawn on accent fills
    button: str = RAISED             # secondary button
    button_hover: str = BORDER_RAISED
    field_bg: str = RAISED           # slider track, entry, combo face
    # status chip colors (kept in step with the tray icon meaning)
    ok: str = "#4caf62"
    counting: str = "#d9a13c"
    off: str = "#5b6470"
    paused: str = "#e0662f"
    danger: str = "#ff5d5d"           # a real display holder on screen
    # preview overlay (cv2 is BGR)
    box_bgr: tuple = (140, 200, 60)
    # chrome
    radius: int = 10
    font_family: str = ""            # empty = the CTk default font

    def font(self, size=14, weight="normal"):
        if self.font_family:
            return ctk.CTkFont(family=self.font_family, size=size,
                               weight=weight)
        return ctk.CTkFont(size=size, weight=weight)

    # -- style kwargs, one per widget kind, so window.py stays generic --
    def panel_style(self):
        # elevation = contrast tiers + a 1px border DARKER than the
        # card, never a shadow (the Monitorian/PowerToys recipe)
        return dict(fg_color=self.panel, border_color=self.border,
                    border_width=1, corner_radius=self.radius)

    def primary(self):
        return dict(fg_color=self.accent, hover_color=self.accent_hover,
                    text_color=self.on_accent,
                    border_color=self.border_raised, border_width=1,
                    corner_radius=self.radius)

    def secondary(self):
        return dict(fg_color=self.button, hover_color=self.button_hover,
                    text_color=self.text,
                    border_color=self.border_raised, border_width=1,
                    corner_radius=self.radius)

    def text_style(self, kind="text"):
        color = (self.txt3 if kind == "disabled"
                 else self.subtext if kind == "sub" else self.text)
        return dict(fg_color="transparent", text_color=color)

    def slider_style(self):
        return dict(fg_color=self.field_bg, progress_color=self.accent,
                    button_color=self.accent,
                    button_hover_color=self.accent_hover,
                    border_color=self.border_raised,
                    corner_radius=self.radius)

    def menu_style(self):
        # the combo face is a RAISED control, not decoration: it takes
        # the field tier, and the accent stays reserved for live state
        return dict(fg_color=self.field_bg, button_color=self.field_bg,
                    button_hover_color=self.button_hover,
                    dropdown_fg_color=self.panel,
                    dropdown_hover_color=self.button_hover,
                    text_color=self.text, corner_radius=self.radius,
                    font=self.font(13))

    def switch_style(self):
        # one dict for the eight CTkSwitch call sites (they used to
        # hand-pick progress/border and let the defaults color the
        # rest - the audit's job is exactly to stop that)
        return dict(fg_color=self.field_bg, progress_color=self.accent,
                    border_color=self.border_raised,
                    button_color=self.text,
                    button_hover_color=self.accent_hover)
                    # (no hover_color: CTkSwitch rejects it, measured -
                    # that kwarg belongs to buttons only)

    def segmented_style(self):
        # CTkSegmentedButton takes NO border_color (measured: it raises
        # __init__ TypeError on it, unlike the switch) - the tier is
        # carried by fg/unselected, which is the whole visible frame
        # for this widget anyway.
        return dict(fg_color=self.field_bg,
                    unselected_color=self.field_bg,
                    unselected_hover_color=self.button_hover,
                    selected_color=self.accent,
                    selected_hover_color=self.accent_hover,
                    text_color=self.text, corner_radius=self.radius)

    def chip(self, state):
        return {"active": self.ok, "counting": self.counting,
                "off": self.off, "paused": self.paused}.get(state,
                                                            self.subtext)


MODERN = Skin(
    key="modern", label="modern", mode="dark",
    # the defaults above ARE the modern skin; only identity is set here
    # - except the font: the CTk default (bundled Roboto, GDI-unhinted)
    # reads terminal-y at our sizes; Segoe UI is the native Win11
    # settings font, DirectWrite-hinted, and matches the OS chrome the
    # window's own title bar already uses
    font_family="Segoe UI",
)

# The fun skin is a palette stub. Its full look (art, fonts, corner
# language, maybe animation) is defined later; until then it just
# reskins in place, which already proves the seam works.
FUN = Skin(
    key="fun", label="fun", mode="dark",
    bg="#140a1f", panel="#24122f", border="#3d1f52",
    text="#ffe9ff", subtext="#b892c9",
    accent="#ff3ba0", accent_hover="#e02c89",
    button="#3d1f52", button_hover="#4f2a68",
    field_bg="#1c0f27",
    ok="#3dffa3", counting="#ffd23a", off="#6a4f7a", paused="#ff8a3d",
    box_bgr=(60, 200, 255),          # hot pink boxes in the preview
    radius=18, font_family="Consolas",
)

SKINS = {"modern": MODERN, "fun": FUN}
DEFAULT_SKIN = "modern"
_skin_warned = False            # the fallback confesses ONCE (audit LOW)


def apply_ctk_font(skin):
    """Re-point CTk's OWN default font (the ThemeManager's CTkFont
    entry every button/switch/entry falls back to when the call site
    passes no font) at the skin's family. Without this, button labels
    keep rendering the bundled Roboto - GDI-unhinted and old-school -
    while only our explicit CTkLabels got the skin font."""
    import customtkinter as ctk
    fam = skin.font_family or "Segoe UI"
    ctk.ThemeManager.theme.setdefault("CTkFont", {})["family"] = fam


def get_skin(name):
    """The old one-liner returned MODERN for an unknown key with zero
    confession (audit LOW): a typo'd ui.skin silently loses the fun
    skin forever. The fallback STAYS (a bad string must never brick
    the UI), but it now confesses once per process, naming the key."""
    global _skin_warned
    skin = SKINS.get(name)
    if skin is None:
        if not _skin_warned:
            log.warning("ui.skin %r is not a skin - serving %r",
                        name, DEFAULT_SKIN)
            _skin_warned = True
        return MODERN
    return skin
