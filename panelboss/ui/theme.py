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

import customtkinter as ctk


@dataclass
class Skin:
    key: str
    label: str                       # name shown in the skin picker
    mode: str = "dark"               # CTk appearance mode
    # palette
    bg: str = "#1f2126"              # window background
    panel: str = "#2b2e34"           # card / frame fill
    border: str = "#3a3e46"
    text: str = "#eef1f4"
    subtext: str = "#9aa2ae"
    accent: str = "#2dd6a6"          # primary button, switch on
    accent_hover: str = "#25b890"
    button: str = "#3a3e46"          # secondary button
    button_hover: str = "#474c55"
    field_bg: str = "#20232a"        # slider track, option menu
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
        return dict(fg_color=self.panel, border_color=self.border,
                    border_width=1, corner_radius=self.radius)

    def primary(self):
        return dict(fg_color=self.accent, hover_color=self.accent_hover,
                    text_color="#10131a", corner_radius=self.radius)

    def secondary(self):
        return dict(fg_color=self.button, hover_color=self.button_hover,
                    text_color=self.text, corner_radius=self.radius)

    def text_style(self, kind="text"):
        color = self.text if kind == "text" else self.subtext
        return dict(fg_color="transparent", text_color=color)

    def slider_style(self):
        return dict(fg_color=self.field_bg, progress_color=self.accent,
                    button_color=self.accent,
                    button_hover_color=self.accent_hover,
                    border_color=self.border, corner_radius=self.radius)

    def menu_style(self):
        return dict(fg_color=self.field_bg, button_color=self.accent,
                    button_hover_color=self.accent_hover,
                    dropdown_fg_color=self.panel,
                    dropdown_hover_color=self.button_hover,
                    text_color=self.text, corner_radius=self.radius)

    def segmented_style(self):
        return dict(fg_color=self.panel,
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


def get_skin(name):
    return SKINS.get(name, MODERN)
