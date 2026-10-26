"""Raw Win32 plumbing for the page stills, in one place: the ctypes
bindings (argtypes set, because a truncated 64-bit handle is a silent
wrong answer on this platform, not an error), a compatible-DIB readback,
and the two calls the stills ride - a screen BitBlt, and WindowFromPoint
for the guard that asks whose pixels are at a point.

Nothing here decides anything: _pageprint owns the camera and its guards,
this module only talks to gdi32/user32.
"""
from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger("ui")

SRCCOPY = 0x00CC0020
GA_ROOT = 2


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


try:
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    for _fn, _res, _args in (
            (user32.GetDC, ctypes.c_void_p, [ctypes.c_void_p]),
            (user32.ReleaseDC, ctypes.c_int,
             [ctypes.c_void_p, ctypes.c_void_p]),
            (user32.GetAncestor, ctypes.c_void_p,
             [ctypes.c_void_p, ctypes.c_uint]),
            (user32.WindowFromPoint, ctypes.c_void_p, [POINT]),
            (gdi32.CreateCompatibleDC, ctypes.c_void_p, [ctypes.c_void_p]),
            (gdi32.CreateCompatibleBitmap, ctypes.c_void_p,
             [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]),
            (gdi32.SelectObject, ctypes.c_void_p,
             [ctypes.c_void_p, ctypes.c_void_p]),
            (gdi32.BitBlt, ctypes.c_int,
             [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
              ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
              ctypes.c_uint]),
            (gdi32.GetDIBits, ctypes.c_int,
             [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
              ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p,
              ctypes.c_uint]),
            (gdi32.DeleteDC, ctypes.c_int, [ctypes.c_void_p]),
            (gdi32.DeleteObject, ctypes.c_int, [ctypes.c_void_p])):
        _fn.restype, _fn.argtypes = _res, _args
    OK = True
except Exception:                    # non-Windows, or a locked-down box
    OK = False


class _BMIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class _BMPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BMIH), ("bmiColors", wintypes.DWORD * 3)]


def blit_to_image(w, h, draw):
    """One compatible bitmap, `draw(mdc, sdc)` fills it, read back as a
    PIL image (or None): the DIB is top-down 32bpp BGRX, the shape every
    camera in the house reads. `sdc` is the screen DC the grab blits
    from; `draw` returns falsy and the caller gets None."""
    from PIL import Image
    try:
        sdc = user32.GetDC(None)
        mdc = gdi32.CreateCompatibleDC(sdc)
        bmp = gdi32.CreateCompatibleBitmap(sdc, w, h)
        gdi32.SelectObject(mdc, bmp)
        try:
            if not draw(mdc, sdc):
                return None
            buf = ctypes.create_string_buffer(w * h * 4)
            bmi = _BMPINFO()
            hdr = bmi.bmiHeader
            hdr.biSize, hdr.biWidth, hdr.biHeight = \
                ctypes.sizeof(_BMIH), w, -h
            hdr.biPlanes, hdr.biBitCount, hdr.biCompression = 1, 32, 0
            if not gdi32.GetDIBits(mdc, bmp, 0, h, buf,
                                   ctypes.byref(bmi), 0):
                return None
            return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX",
                                    0, 1).copy()
        finally:
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mdc)
            user32.ReleaseDC(None, sdc)
    except Exception:
        log.debug("blit_to_image failed", exc_info=True)
        return None
