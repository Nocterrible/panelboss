"""Presence state machine, as a package.

one loop, every event source drains into it:
- keyboard idle (GetLastInputInfo): the gate; we never poll the camera
  while the user is typing
- camera frames: presence evidence, debounced so a single flaky frame
  never toggles the power
- the display watcher's queue: reports the screens came back without us
  (mouse jiggle, key press). wake_policy decides whether we hand them
  back to the user or turn them off again after re_off_grace_sec
- tray: pause, snooze, quit

screens-off logic: the camera never runs until idle_gate_sec of no
input; after that we poll on_poll_sec until absent_confirm_sec of
confirmed absence; worst case is 90 s from the last keystroke.
while the screens are dark we poll off_poll_sec with the camera held
open; two consecutive positive frames (min_hits) restore them.

This is the old single-module state, kept as the same namespace: the
engine is one class, so the subject parts are mixins over it (_boot:
construction and the tick, _phase: the lit/dark counting machines,
_power: the hold policy, the transitions and the wm layout memory,
_policy: the per-camera vote tables and wear clock, _cams: grab,
rotor, holds and releases, _preview: the debug lease and the frame
slot, _events: watcher queue, wake bursts, tray commands). Every old
name still resolves here, PresenceMonitor is the composition of the
mixins, and the module class at the bottom fans attribute WRITES
through to the parts - camera_policy_test patches state.time and the
bodies' bare-name call sites must keep seeing the patch, exactly as
they did when there was only one module to patch.
"""

from __future__ import annotations

import logging
import math
import queue
import sys
import threading
import time

from .. import display

from . import (_boot, _cams, _events, _phase, _policy, _power,
               _preview)

from ._boot import _BootMixin

from ._phase import _PhaseMixin

from ._power import _PowerMixin

from ._policy import _PolicyMixin

from ._cams import _CamsMixin

from ._preview import FrameBox, _PreviewMixin

from ._events import _EventsMixin

log = logging.getLogger("state")

# The mixin order is logical only: no diamond, no shared method name,
# every cross-subject call goes through self. (SIZE LAW note: this
# facade is ~135 lines and the bulk IS the contract - the old docstring
# plus the re-export roster every caller and test-patch site leans on.)
class PresenceMonitor(_BootMixin, _PhaseMixin, _PowerMixin,
                      _PolicyMixin, _CamsMixin, _PreviewMixin,
                      _EventsMixin):
    pass


__all__ = [
    "FrameBox",
    "PresenceMonitor",
    "_BootMixin",
    "_CamsMixin",
    "_EventsMixin",
    "_PhaseMixin",
    "_PolicyMixin",
    "_PowerMixin",
    "_PreviewMixin",
    "_boot",
    "_cams",
    "_events",
    "_phase",
    "_policy",
    "_power",
    "_preview",
    "display",
    "log",
    "logging",
    "math",
    "queue",
    "threading",
    "time",
]

_FANOUT = (_boot, _phase, _power, _policy, _cams, _preview, _events)


class _StatePackage(type(sys.modules[__name__])):
    """Module subclass: a write to this namespace rebinds the name in
    every part that holds it. The suites monkey-patch state (time, and
    anything else the old flat module exposed), and those names resolve
    as bare globals inside OTHER parts' bodies; copying them onto the
    facade alone would fork the state - internal calls keep answering
    to the old object. Reads need no magic: the re-exports are the
    parts' own objects."""

    def __setattr__(self, name, value):
        for _part in self.__dict__.get("_FANOUT", ()):
            if name in _part.__dict__:
                setattr(_part, name, value)
        object.__setattr__(self, name, value)


sys.modules[__name__].__class__ = _StatePackage
