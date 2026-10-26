"""Page-attributed dirty marks: when is a page still a LIE?

The tab-switch cure (see _pageprint) shows a cached still of the page
under the progressive paint. A still that no longer matches its page is
exactly the thing that must never reach the glass, so this module
answers one question for every content change in the house: WHICH page
moved?

The seat is CTkBaseClass._draw - the one method every CTk widget's
redraw passes through (each concrete widget's _draw calls
super()._draw), so a single wrapper covers every fill, sync, render and
repaint there is, with no list of call sites to keep in step. A drawn
widget is walked up its master chain; the first page frame it belongs
to is marked dirty, and a widget that belongs to no page (the title
bar, a dialog) marks nothing - the idle clock must not invalidate the
whole cache once a second.

BEST-EFFORT BY DESIGN: if CTk ever renames the seat, `watch` fails
once, logs, and installs nothing. The caller then sees no dirty marks
at all, which is exactly why the snapshot path treats "no mark" as
"cannot trust the cache" and renders the page fresh instead: the
failure path is slower, never a lie.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger("ui")

# By-design residency (reviewer, Oct 25): owners are added on watch and
# never removed - one shell per process is the app's own law, so the
# tax is one entry; a test process making many shells pays a per-
# redraw list walk, not a leak of OS handles.
_WATCH = []
_WRAPPED = [False]
_HOPS = 24                       # page depth: a page frame is <= 6 deep


def watch(owner):
    """call owner._page_drawn(widget) on every CTk widget redraw"""
    if not _WRAPPED[0]:
        try:
            from customtkinter.windows.widgets.core_widget_classes \
                .ctk_base_class import CTkBaseClass
            _real = CTkBaseClass._draw

            def _draw(self, *a, **k):
                _real(self, *a, **k)
                for who in list(_WATCH):
                    try:
                        who._page_drawn(self)
                    except Exception:
                        pass     # a dying shell: a miss, not a raise
            CTkBaseClass._draw = _draw
            _WRAPPED[0] = True
        except Exception:
            log.debug("page dirty hook unavailable", exc_info=True)
    if owner not in _WATCH:
        _WATCH.append(owner)


def owner_page(widget, pages):
    """the page key `widget` lives on, or None for house furniture.
    `pages` maps id(page_frame) -> key (the shell's own index)."""
    w, hops = widget, 0
    while w is not None and hops < _HOPS:
        key = pages.get(id(w))
        if key is not None:
            return key
        w = getattr(w, "master", None)
        hops += 1
    return None


def stamp(marks, key):
    """Mark `key` dirty now; `marks` is the shell's {key: {...}} dict.

    The still's IMAGE reference survives the mark on purpose: the
    backdrop may be showing that very image while the page behind it is
    raised, and freeing a Tk image that is on screen would blank (or
    break) what the user is looking at. The mark is about TRUST - the
    next switch refuses to use it and renders fresh - never about
    ownership; the shell drops the image when it replaces it."""
    st = marks.setdefault(key, {})
    st["dirty"] = True
    st["t_dirty"] = time.monotonic()
