"""The Chromium debug-port transport: a stdlib-only RFC 6455 client on
top of the endpoint --remote-debugging-port opens.

Everything this app needs to see a running browser's content side
rides this door: /json/version (the port's proof), /json (the target
list), and the WebSocket call/reply (json with id match and a hard
timeout). The handshake is the spec's plain GET + Sec-WebSocket-Key
(base64 nonce, the accept is sha1(nonce + the magic GUID)); frames
are FIN+text, client->server MASKED, server->client unmasked; 7-,
16- and 63-bit payloads all parse (63-bit is read, never written).
No third-party websocket package (the MSI size law, and stdlib means
no version drift). The verbs are pinned through the same
discipline as the dimmer's user32 block: named functions, named
failures - a dead port, a refused handshake, a wrong id, a timeout,
a hang-up all fail OPEN (None / CdpError), and the caller's job is
to treat the answer as "the browser has nothing to say this tick."
"""

import base64
import hashlib
import json
import os
import socket
import struct
import urllib.request

MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
HINT_PORTS = (9222, 9333)        # the usual debug ports; the
                                  # DevToolsActivePort file is the
                                  # truth when a custom one is set


class CdpError(Exception):
    """A socket-level or protocol-level failure mid-conversation."""


def read_json(url, timeout=2.0):
    """GET url -> the parsed json body, or None: a dead port, a slow
    browser and a refused connection all mean "no answer this tick."
    The opener is proxy-less on purpose: a system proxy in the
    environment must not sit between us and 127.0.0.1."""
    import urllib.request as _ur
    try:
        with _ur.build_opener(_ur.ProxyHandler({})).open(
                url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def find_port(profile_dirs, timeout=2.0):
    """The running browser's debug port: the hint list first, then -
    if the family's profile dir holds a DevToolsActivePort file -
    its first line. The ANSWER to /json/version is the proof, not
    the port's mere listening: a stale file on a dead browser fails
    OPEN to None, the feature's root."""
    ports = list(HINT_PORTS)
    for d in profile_dirs or ():
        try:
            with open(os.path.join(d, "DevToolsActivePort")) as f:
                ports.append(int(f.readline().strip()))
        except (OSError, ValueError):
            pass
    for p in dict.fromkeys(ports):
        if read_json("http://127.0.0.1:%d/json/version" % p,
                     timeout) is not None:
            return p
    return None


def _ws_parts(url):
    p = url.split("//", 1)[1]
    host, _, path = p.partition("/")
    h, _, port = host.partition(":")
    return h, int(port) if port else 80, "/" + path


class Socket:
    """One attached browser session: a connected socket plus the
    frame discipline. talk() is the only public door - one json
    call/reply with id match; everything before the reply (events,
    pings) is skipped, a refusal dict raises with the browser's own
    message, and the socket closes on every exit path."""

    def __init__(self, url, timeout=4.0):
        host, port, path = _ws_parts(url)
        self._s = socket.create_connection((host, port), timeout=timeout)
        self._s.settimeout(timeout)
        self._id = 0
        self._rest = b""
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        self._s.sendall(("GET %s HTTP/1.1\r\nHost: %s:%d\r\n"
                         "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                         "Sec-WebSocket-Key: %s\r\n"
                         "Sec-WebSocket-Version: 13\r\n\r\n"
                         % (path, host, port, key)).encode("ascii"))
        head, sep, self._rest = self._fill(4).partition(b"\r\n\r\n")
        if not sep or b"101" not in head.split(b"\r\n", 1)[0]:
            raise CdpError("handshake refused: %r" % head[:80])
        accept = ""
        for line in head.split(b"\r\n")[1:]:
            if line.lower().startswith(b"sec-websocket-accept:"):
                accept = line.split(b":", 1)[1].strip().decode("ascii")
        want = base64.b64encode(hashlib.sha1(
            (key + MAGIC).encode("ascii")).digest()).decode("ascii")
        if accept != want:
            raise CdpError("handshake key mismatch")

    def _fill(self, need):
        while len(self._rest) < need:
            chunk = self._s.recv(65536)
            if not chunk:
                raise CdpError("the browser hung up mid-frame")
            self._rest += chunk
        return self._rest

    def _frame(self):
        """One complete frame from the wire -> (opcode, payload)."""
        b0, b1 = self._fill(2)[:2]
        self._rest = self._fill(2)[2:]
        n = b1 & 0x7F
        if n == 126:
            n = struct.unpack(">H", self._fill(2)[:2])[0]
            self._rest = self._fill(2)[2:]
        elif n == 127:
            n = struct.unpack(">Q", self._fill(8)[:8])[0]
            self._rest = self._fill(8)[8:]
        if b1 & 0x80:
            self._rest = self._fill(4)[4:]    # the server does not mask
        data = self._fill(n)
        self._rest = data[n:]                 # the payload rides out
        return b0 & 0x0F, data[:n]

    def send_text(self, s):
        """Client->server: a FIN text frame, MASKED (the law)."""
        self._send(0x1, s.encode("utf-8"))

    def _send(self, opcode, b):
        n = len(b)
        if n < 126:
            head = bytearray([0x80 | opcode, 0x80 | n])
        elif n < (1 << 16):
            head = bytearray([0x80 | opcode, 0x80 | 126])
            head += struct.pack(">H", n)
        else:
            head = bytearray([0x80 | opcode, 0x80 | 127])
            head += struct.pack(">Q", n)
        mask = os.urandom(4)
        head += mask
        self._s.sendall(bytes(head)
                        + bytes(x ^ mask[i % 4] for i, x in enumerate(b)))

    def talk(self, method, params=None, timeout=4.0):
        """The json call/reply: send the call, read frames until the
        id answers (events before it are skipped - the page talks
        on this socket too), a CDP error dict raises with the
        browser's message. The socket STAYS OPEN (the attach rides
        across ticks; close() is the caller's - see videoeye's
        one-retry seam)."""
        self._id += 1
        req = {"id": self._id, "method": method}
        if params:
            req["params"] = params
        self.send_text(json.dumps(req))
        self._s.settimeout(timeout)
        while True:
            op, payload = self._frame()
            if op == 0x8:
                raise CdpError("the browser closed the socket")
            if op == 0x9:
                self._send(0xA, payload)     # ping: pong it, keep
                continue                     # reading (long-lived
            if op == 0xA:                    # attaches DO get pinged
                continue
            if op not in (0x1, 0x2):
                raise CdpError("opcode %#x is not text" % op)
            msg = json.loads(payload.decode("utf-8"))
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise CdpError("%s refused: %s" % (
                        method,
                        (msg.get("error") or {}).get("message")))
                return msg.get("result")

    def close(self):
        try:
            self._s.close()
        except OSError:
            pass
