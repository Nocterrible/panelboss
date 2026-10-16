"""panelboss_host: the PanelBoss Companion native-messaging host.

The ONE untried manifest shape, built to the spec the last two attempts
skipped: a single absolute exe (no wrapper, no shell, no argv split),
stdin read as 4-byte LE length-prefixed UTF-8 JSON frames in O_BINARY
mode (the \n->\r\n text-mode corruption is the silent killer that made
the pythonw form pipe-blind), every reply written back the same way.

The host is a PURE TRANSPORT + one file write. It does not bind a port,
does not touch the network, does not run PanelBoss: it receives the
extension's message and hands the payload to the app by writing the
single app-owned doorway file (%APPDATA%\\PanelBoss\\rect). That is the
whole feature - the extension measures a playing video in the page and
this host drops the geometry where the app's eye already looks.

The id of the extension is the ACL (the registry key and the
manifest's allowed_origins carry the SAME origin), the browser's own
install check is the whole handshake - no pairing, no token. The wire
schema is OPEN (MIT) and self-describing: every message carries an
"op" and the "capabilities" op answers with what this host can do, so
any project may consume it, PanelBoss merely being the first.

SIZE LAW (~130): the file is ONE seam - read one frame, dispatch one
or two ops, write one reply. The frame discipline is 12 lines; splitting
it would separate the length-prefix law from the code that reads it.
"""

import json
import os
import struct
import sys


# the host name the registry and connectNative() both spell - the
# manifest's allowed_origins keys on the extension's own id, so this is
# the only string that must stay byte-identical across three files.
HOST_NAME = "com.nocterrible.panelboss"

# where the app's eye reads a manual trigger - the app-owned doorway,
# NOT the browser's download dir (the whole reason the shelf law exists
# is the downloads writer; native messaging needs no shelf: the write
# lands here deterministically, every browser, every config).
RECT_PATH = os.path.join(os.environ.get("APPDATA", ""), "PanelBoss",
                          "rect")

# the self-describing answer: what this host understands. PanelBoss
# reads this the same way any other consumer would - discover what the
# API can send, never assume a file on a shelf.
CAPABILITIES = {
    "op": "capabilities",
    "protocol": "panelboss-v1",
    "host": HOST_NAME,
    "ops": ["capabilities", "veil"],
    "veil": {
        "fields": ["rect", "dpr", "paused", "scroll", "view",
                   "bounds", "family", "ts"],
        "rect": ["left", "top", "width", "height"],
    },
}


def _read_frame(stream):
    """One native-messaging frame: 4-byte LE unsigned length, then
    exactly that many UTF-8 bytes, json-decoded. A short read or bad
    json returns None - the browser owns the lifecycle, a dead frame is
    the end of the conversation, never a traceback on stdout."""
    head = stream.read(4)
    if len(head) != 4:
        return None
    (n,) = struct.unpack("<I", head)
    if n > 1024 * 1024:                # the spec's own 1 MB host cap
        return None
    body = stream.read(n)
    if len(body) != n:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def _write_frame(stream, obj):
    """The reply, length-prefixed the same way; O_BINARY is set once at
    top so the length byte-count and the written bytes can never drift
    on a Windows newline."""
    data = json.dumps(obj).encode("utf-8")
    stream.write(struct.pack("<I", len(data)))
    stream.write(data)
    stream.flush()


def _veil(msg):
    """op=veil: write the payload to the app's doorway file, one json
    line exactly as the eye parses it, and answer with the disk truth
    (the app's eye is the reader; the host's job ends at the write)."""
    payload = msg.get("payload")
    if not isinstance(payload, dict):
        return {"op": "veil", "ok": False, "why": "payload is not an "
                "object"}
    try:
        # the eye reads the FIRST line and json.loads it - write one
        # line, a trailing newline, no atomic temp (a torn write reads
        # as a failed parse and the next good click overwrites it). The
        # directory is made if the app never created it (the host is
        # standalone; the app downs the door on install, but the host
        # must not depend on that ordering).
        os.makedirs(os.path.dirname(RECT_PATH), exist_ok=True)
        with open(RECT_PATH, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except OSError as e:
        return {"op": "veil", "ok": False, "why": "could not write "
                "the app's doorway: %s" % e}
    return {"op": "veil", "ok": True, "path": RECT_PATH}


def main():
    """One frame loop: the browser starts us, feeds frames on stdin,
    and our every stdout byte must be a length-prefixed reply. argv[1]
    is the caller origin (chrome-extension://<id>/), unchecked here
    because the manifest's allowed_origins IS the gate - the browser
    already refused anyone whose origin is not on the list."""
    if sys.platform == "win32":
        import msvcrt
        # os.O_BINARY (0x8000) is the flag; msvcrt carries none (the
        # C runtime's _O_BINARY never made it to the module's surface -
        # measured here: AttributeError on Python 3.10).
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    stdin = sys.stdin.buffer if hasattr(sys.stdin, "buffer") else sys.stdin
    stdout = sys.stdout.buffer if hasattr(sys.stdout, "buffer") else sys.stdout
    while True:
        msg = _read_frame(stdin)
        if msg is None:
            return                      # EOF: the browser closed the pipe
        op = msg.get("op")
        if op == "capabilities":
            _write_frame(stdout, CAPABILITIES)
        elif op == "veil":
            _write_frame(stdout, _veil(msg))
        else:
            _write_frame(stdout, {"op": "error",
                                  "why": "unknown op %r" % (op,),
                                  "capabilities": CAPABILITIES})


if __name__ == "__main__":
    main()