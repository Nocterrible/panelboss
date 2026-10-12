"""The one-line hint face for the reskin (UI-1c): tooltips used to
live behind "?" chips you had to hunt; now every helpable control
carries a pre-allocated inline hint line (never added later - that
is what makes it layout-stable), and this is the pure text side of
that promise, split out of _widgets.py at the size-law gate.

What if it dies: no state, no IO, pure function - an empty tip is
an empty string, and a paragraph tip degrades to its first sentence
shortened to one line. Nothing upstream can half-crash on it."""

import re
import textwrap

# one hint line reads the card's width budget - the same wrap the card
# subtitle already uses, so hints and subs rhyme
HINT_WRAP = 480


def hint_text(tip, chars=90):
    """The one-line face of a tooltip's paragraph: first sentence,
    shortened to fit one line. Static at build time - the row never
    dances when help appears, because it never appears. `chars` is
    capped by the CALL SITE to the card's own width budget: the
    narrow cards clip, and a clipped hint reads worse than a short
    one (camera card measured 340 px at Roboto 11 = ~44 chars)."""
    if not tip:
        return ""
    first = re.split(r"\.(?:\s|$)", tip, maxsplit=1)[0].strip()
    return textwrap.shorten(first, width=chars, placeholder=" ...")
