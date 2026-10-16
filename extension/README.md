# PanelBoss Companion (extension, v0.3)

The manual "veil this video" trigger for PanelBoss's Movie theater
mode. One click on the toolbar icon: measure the playing video with
`chrome.scripting.executeScript` (the ad-blocker class of call, a
static bundled function — never an eval string), hand the answer to the
**local native host** over `chrome.runtime.connectNative`, done. The
host writes the geometry to PanelBoss's own doorway file; PanelBoss's
eye reads it on its next beat. No timers, no pumps, no banner, no
network, no eval.

## The API (open, MIT, self-describing)

The extension IS an API. Every message is a plain JSON object carrying
an `op`; the host answers the `capabilities` op with what this build can
send. Any project may consume it — the schema ships open, the id of the
extension is the only ACL, and the browser's own install check is the
whole handshake (no pairing, no token).

| op | direction | meaning |
|----|-----------|---------|
| `capabilities` | ext → host | answer with the self-description |
| `veil` | ext → host | payload = the measured row (below) |

`capabilities` reply (from the host):

```json
{
  "op": "capabilities",
  "protocol": "panelboss-v1",
  "host": "com.nocterrible.panelboss",
  "ops": ["capabilities", "veil"],
  "veil": { "fields": ["rect", "dpr", "paused", "scroll",
                        "view", "bounds", "family", "ts"] }
}
```

`veil` payload (the row the eye folds): `rect` is the first `<video>`'s
viewport box in CSS px (`left/top/width/height`), `dpr` the device
pixel ratio, `paused` whether playback is stopped, `scroll` the
`[scrollX, scrollY]` pair (the future DRM lane reads document space from
it), `view` the inner `[width, height]`, `bounds` the window's outer
`left/top/width/height` in DIP px, `family` one of `chrome` / `edge` /
`opera_gx`, `ts` the wall-clock seconds stamp.

## The three dead shapes (do not re-derive)

The history that earned native messaging its place — measured, not
guessed, on this desk:

1. **nativeMessaging `.cmd` wrapper** died at stdin EOF (the wrapper
   exits before the host answers; Chrome reports a disconnected port).
2. **nativeMessaging `pythonw.exe` + script-arg** boots but is deaf:
   the length-prefixed frames never arrive (text-mode stdin corrupts
   `\n`→`\r\n`, and the token split is not what the spec delivers).
3. **`chrome.debugger` attach-on-click** raised the *"X is debugging
   this tab"* banner and hung silent — the owner's ruling on sight.

What works is the **one shape the spec always documented**: a single
absolute exe (no wrapper, no shell), `O_BINARY` stdin/stdout, the 4-byte
**native-order** length prefix read before **every** frame (little-endian
on this platform — the spec says *native*, not LE; a port to a
big-endian platform must not hard-code the byte order. This correction
is the fixer's, Oct 16: v0.3 shipped `<I` and this line said "LE"). That
is `panelboss_host.py`, frozen to `panelboss-host.exe` by
`install_host.ps1`.

## Load it (measured on Opera GX, Oct 15-16)

1. `opera://extensions` → enable **Developer mode** (and the Chrome Web
   Store door for a store publish).
2. **Load unpacked** → point at the `extension/` folder (the one holding
   `manifest.json`). Pin the icon. After any change, hit **reload**.
3. Run `host/install_host.ps1 -ExtensionId <id>` where `<id>` is the
   extension id on the browser's extensions page — this builds the host
   exe and registers it under HKCU (no admin; Chrome, Edge, and Opera
   read the same `NativeMessagingHosts` key). Without the id the
   manifest ships with a placeholder and the host refuses everyone.

The click needs a video tab: one press measures, hands the row to the
host, and the icon answers on itself with a word — `veiled` (geometry
written), `novid` (no `<video>`), `ask`/`slow`/`win`/`nm` (which step
refused; `nm` = the native host is missing or the id doesn't match).
The doorway is `%APPDATA%\PanelBoss\rect` — **fixed**, not the browser's
download dir: the downloads writer (v0.2) needed the "shelf law" to find
where chrome.downloads had *actually* put the file; the native host
writes where it is told, every browser, every config. The shelf law is
retired with it.

## Manifest notes (v0.3) — the store form

`permissions: ["scripting", "activeTab", "nativeMessaging"]`. This is
the store-grade minimum, and it is deliberate:

- **`activeTab` instead of `<all_urls>`.** The click is a user gesture on
  the tab they are looking at; `activeTab` grants access to *that tab*
  for *that moment* — the host-permission warning "*read and change all
  your data on all websites*" never appears, and the review never asks
  why a video-measuring trigger wants every site.
- **`scripting`** is the inject-and-measure call, self-contained
  function, nothing left attached.
- **`nativeMessaging`** is the one sanctioned channel from an extension
  to a local desktop application. The review's question is answered by
  the `allowed_origins` list (our id, and only our id) and the host's
  single-file-write behavior.
- **`tabs`/`downloads` left the manifest** (v0.2's file-bridge writer).
- **No remote code, no eval.** The measure function is bundled and
  static; MV3's CSP rejects eval strings and remotely-hosted code at
  review, and the old v0.2 `eval`-of-a-string was exactly that class.

Justification for the store form (the one line each, for submission):

- *scripting*: "measures the bounding box of the playing video in the
  active tab on the toolbar click, so the companion desktop app can dim
  the desk around it."
- *activeTab*: "the measurement runs only in the tab the user clicked
  from, only for that click — no persistent page access."
- *nativeMessaging*: "hands the measured rectangle to the local PanelBoss
  desktop app via a host that writes one file to the app's own folder;
  the host accepts only this extension's id."

## The debug port is gone, the engine reader retired

The `--remote-debugging-port` lane and every reader that assumed it
(`flag_families`, the port probe, the OS-window fallback) left with the
v0.2→v0.3 move. The extension IS the answer; PanelBoss now reads what
this API can send and nothing it merely used to expect.