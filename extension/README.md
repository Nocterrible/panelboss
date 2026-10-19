# PanelBoss Companion (extension, v0.4)

The automatic lane for PanelBoss's Movie theater mode. A declared
content script lives in the page and measures the playing video
natively (`getBoundingClientRect` is a DOM call it owns); on
`play`/`pause`/`ended` it hands the row to the **local native host**
over `chrome.runtime.sendMessage` → `connectNative`, done. The host
writes the geometry to PanelBoss's own doorway file; PanelBoss's eye
reads it on its next beat. Since v0.4.3 the toolbar icon opens a
*popup readout*: the live row the eye sees (video box, dpr, paused,
viewport, window origin - asked of the page's own content script
through the same open `{op:"measure"}` API), plus the demoted *test*
button - one click measures RIGHT NOW, no waiting, and the button
echoes the host's word back in place of the old badge gesture.
No timers, no pumps, no banner, no network, no eval, and — the big win
of v0.4 — **no `scripting`, no `activeTab`, no `<all_urls>`**: the
measure lives in the content script, so the manifest asks for
`nativeMessaging` and nothing else.

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
  "auto": { "trigger": "video play", "pause": "veil lifts",
            "ended": "veil lifts" },
  "veil": { "fields": ["rect", "dpr", "paused", "scroll",
                        "view", "origin", "webrect", "bounds",
                      "family", "lane", "ts"],
            "lane": ["click", "auto"] }
}
```

`veil` payload (the row the eye folds): `rect` is the biggest
playing-ish `<video>`'s viewport box in CSS px (`left/top/width/
height`), `dpr` the device pixel ratio, `paused` whether playback is
stopped, `scroll` the `[scrollX, scrollY]` pair (the future DRM lane
reads document space from it), `view` the inner `[width, height]`, `origin` the window's
`[screenX, screenY]` in CSS px, `webrect` the tab's REAL web-content
rectangle `[left, top, width, height]` in physical pixels — stamped by
the local host from the OS's own answer (the render-widget window's
rect) when it can measure it, absent otherwise —
`bounds` the window's outer `left/top/width/height` in DIP px, `family`
one of `chrome` / `edge` / `opera_gx`, `lane` `click` (a one-shot test
snapshot) or `auto` (a durable play state), `ts` the wall-clock seconds
stamp. Consumers fold `rect` onto the most exact anchor a row carries:
`webrect` first, then `origin`, then `bounds` — each older lane is a
compatibility fallthrough, never an error.

### How PanelBoss reads it (the capability-discovery close)

The host is the API, and PanelBoss asks it directly — the app does *not*
know which browser or extension build is installed; it spawns the same
exe `install_host.ps1` built, feeds `{"op":"capabilities"}`, reads the
framed reply (native-order 4-byte length prefix, 2 s timeout, cached for
a few minutes), and the Movie theater card renders what the API **can**
send (the `ops` list and the `veil` fields). `install_host.ps1` writes
the exe's path to `%APPDATA%\PanelBoss\host.json` (the doorway's
neighbor) so the app knows where to ask. No host → the card says so
plainly ("run extension\host\install_host.ps1"), never a guess.
(`panelboss/nmhost.py` is the reader; the card's line is
`companion.caps_words()`.)

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
   The manifest carries a pinned `"key"` (Oct 16), so the id is
   permanent — `feolhiokchmpphlhllagimnilceldegk` for every folder,
   machine, and the store copy alike — and PanelBoss's in-app install
   button computes it for you anyway.

The readout's test button needs a video tab on the site list: one
click asks the tab's own content script to measure, hands the row to
the host, and answers in two places - the button echoes the word and
the icon badges it - `veil` (geometry written; the badge
clips past four chars, so the success word is short), `novid` (no
`<video>`), `site` (the tab is off the site list, so no content script
lives there; a present-but-stalled script answers `slow` instead, the
gate's word-split so a hang is never misread as absence), `slow`/`win`/`nm` (which step refused; `nm` = the native
host is missing or the id doesn't match). The automatic lane is quiet by
design — a page push must not nag; the veil either lands or the app's
grace retracts it. TOP-FRAME LAW: content_scripts ships `all_frames`
false, so the measure is top-frame only — a player inside an iframe
(twitch embeds, SPA shells) is off the map SILENTLY; the honest word
for that is this paragraph, and the fix rides the DRM dossier.
The doorway is `%APPDATA%\PanelBoss\rect` — **fixed**, not the browser's
download dir: the downloads writer (v0.2) needed the "shelf law" to find
where chrome.downloads had *actually* put the file; the native host
writes where it is told, every browser, every config. The shelf law is
retired with it.

## Manifest notes (v0.4) — the store form

`permissions: ["nativeMessaging"]` — one permission, nothing else. The
v0.3 shape (`scripting`, `activeTab`) is retired: the measure moved into
a **declared content script** (static `content_scripts` in the manifest,
scoped to the site list in `matches`), so there is no injection API left
to ask for and no host-permission warning for the review to question.
This is the store-grade minimum, and it is deliberate:

- **No `<all_urls>`, no `host_permissions` at all.** The site list in
  `content_scripts.matches` is the widest door the extension ever
  opens, and it lists streaming hosts, not the web.
- **`nativeMessaging`** is the one sanctioned channel from an extension
  to a local desktop application. The review's question is answered by
  the `allowed_origins` list (our id, and only our id) and the host's
  single-file-write behavior.
- **`tabs`/`downloads` left the manifest** (v0.2's file-bridge writer);
  **`scripting`/`activeTab`** left with v0.4's static content script.
- **No remote code, no eval.** The measure function is bundled and
  static; MV3's CSP rejects eval strings and remotely-hosted code at
  review, and the old v0.2 `eval`-of-a-string was exactly that class.

Justification for the store form (the one line, for submission):

- *nativeMessaging*: "hands the measured video rectangle to the local
  PanelBoss desktop app via a host that writes one file to the app's
  own folder; the host accepts only this extension's id."

## The debug port is gone, the engine reader retired

The `--remote-debugging-port` lane and every reader that assumed it
(`flag_families`, the port probe, the OS-window fallback) left with the
v0.2→v0.3 move. The extension IS the answer; PanelBoss now reads what
this API can send and nothing it merely used to expect.