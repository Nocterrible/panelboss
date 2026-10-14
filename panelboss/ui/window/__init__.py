"""The settings window, as a package.

The facade keeps the old single-module contract: every name
the rest of the codebase (and the UI suites) reached on
`panelboss.ui.window` still resolves here. Subject modules
own their pieces; _shell.py holds the SettingsWindow skeleton.
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import textwrap
import threading
import time

import cv2
import customtkinter as ctk
from PIL import Image

# UI-PLAN Phase 1 step 2, at the ONLY seam that guarantees the rule:
# this module is what creates SettingsWindow, and this block runs at
# its import time - before any CTk class anywhere is instantiated.
# CTk activates process DPI awareness on the first widget and then
# re-applies scaling from its poller; Tk's font metrics do NOT follow
# a late awareness flip, so the kill must come first, not early.
ctk.deactivate_automatic_dpi_awareness()
ctk.set_widget_scaling(1.0)         # device pixels, no hidden multipliers
# The Phase-1 ttk toolkit is optional at runtime (fail-open religion):
# absent or broken, the window still opens in its CTk skin. Imported
# only - the app owns zero ttk widgets today (grepped), so binding the
# dark style is the reskin packet's job; this is just the seam.
try:
    import ttkbootstrap  # noqa: F401 probed, not used
    import pywinstyles   # noqa: F401 probed, not used
except Exception:
    logging.getLogger("ui").info(
        "ttkbootstrap/pywinstyles unavailable - staying CTk-skinned")

from ... import config, profiles, wm
from .. import deps, theme
from ..helpbtn import Tips
from ..kofi import kofi_pil
from ..shield import shield_pil

from ._constants import \
    DEVICE_BY_LABEL, DEVICE_KEYS, HDR_ASK_LABELS, HDR_BY_LABEL, HDR_MENU_ORDER, HDR_SET_LABELS, MOTION_ROWS, PERSON_ROWS, RESTORE_LAST, RESTORE_SCOPES, RESTORE_WHENS, TABS, TIMER_SPECS, TIPS, WAIT_CHOICES

from ._widgets import \
    _SleepPrompt, _WidgetsMixin, _fresh_pin_edit

from ._runtime import \
    _RuntimeMixin

from ._detection import \
    _DetectionMixin

from ._away import \
    _AwayMixin

from ._preview import \
    _CameraMixin

from ._camedit import \
    _CamEditMixin

from ._profiles import \
    _ProfilesMixin

from ._prof_editor import \
    _EditorMixin

from ._prof_apply import \
    _ModeMixin

from ._prof_pins import \
    _PinMixin

from ._restore import \
    _RestoreMixin

from ._power import \
    _PowerMixin

from ._gaming import \
    _GamingMixin

from ._general import \
    _GeneralMixin

from ._shell import SettingsWindow, run

log = logging.getLogger("ui")

__all__ = [
    "DEVICE_BY_LABEL",
    "DEVICE_KEYS",
    "HDR_ASK_LABELS",
    "HDR_BY_LABEL",
    "HDR_MENU_ORDER",
    "HDR_SET_LABELS",
    "MOTION_ROWS",
    "PERSON_ROWS",
    "RESTORE_LAST",
    "RESTORE_SCOPES",
    "RESTORE_WHENS",
    "SettingsWindow",
    "TABS",
    "TIMER_SPECS",
    "TIPS",
    "WAIT_CHOICES",
    "_AwayMixin",
    "_CamEditMixin",
    "_CameraMixin",
    "_DetectionMixin",
    "_EditorMixin",
    "_GamingMixin",
    "_GeneralMixin",
    "_ModeMixin",
    "_PinMixin",
    "_PowerMixin",
    "_ProfilesMixin",
    "_RestoreMixin",
    "_RuntimeMixin",
    "_SleepPrompt",
    "_WidgetsMixin",
    "_fresh_pin_edit",
    "log",
    "run",
]
