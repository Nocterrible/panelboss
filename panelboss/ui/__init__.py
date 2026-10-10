"""Settings window package.

run() must be called on the MAIN thread (Tk rule). is_available() lets
the CLI degrade to headless quietly when CTk cannot be imported.
"""

from __future__ import annotations

import logging

log = logging.getLogger("ui")


def is_available():
    try:
        import tkinter                    # noqa: F401 probed, not used
        import customtkinter              # noqa: F401 probed, not used
        return True
    except Exception:
        return False


def run(cfg, monitor, ui_events):
    from .window import run as main_loop
    main_loop(cfg, monitor, ui_events)    # raises are the caller's
