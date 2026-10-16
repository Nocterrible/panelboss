# PanelBoss Companion (extension, v1)

The manual "veil this video" trigger for PanelBoss's video-dim. One
click on the toolbar icon: attach `chrome.debugger` to the active tab,
evaluate the eye's script once, write the answer to the bridge file
(`PanelBoss/rect` under the Downloads folder — the zero-native-host-
plumbing writer of v1, via `chrome.downloads`), detach. No timers, no
pumps. The video rect PanelBoss folds to physical pixels the same way
it does for the debug-port path (`Browser.getWindowBounds` truth beats
`window.screenX`, which measures (0,0) lies on occluded windows).

The data path of the FEATURE is the debug port
(`--remote-debugging-port`, which PanelBoss sets by launching the
browser with the flag). This extension is the manual trigger and the
future DRM/content-script seat — it is not required for the automatic
veil.

## Load it (measured on Opera GX, Oct 15)

1. Open `opera://extensions` and enable **Download from Chrome Web
   Store** (Opera's Chrome-extension door; with it off there is no
   unpacked door at all).
2. **Load unpacked** appears - point it at this folder (the one
   holding `manifest.json`). Pin the icon (puzzle-piece → PanelBoss
   Companion).
3. Once published, the Chrome Web Store route replaces steps 1-2
   (Opera installs it through the same door); the unpacked route
   stays the developer's.

The click itself needs a video tab: one press of the icon writes the
bridge file (a rect rides `Downloads\PanelBoss\rect`, the
zero-plumbing writer); PanelBoss's video eye picks the click up on
its next tick (freshest source wins, ties the file's).

**The dev-mode caveat (measured, twice this week):** an unpacked
load is **silently ignored** without developer mode - the flag or the
button lands, the extension does not, and nothing says so (Edge 156
with `--load-extension`; Opera GX keeps the same discipline behind
its Chrome door). When the feature "does nothing", check the toggle
before suspecting the code.

**The id is the ACL.** The extension id on the browser's details page
is the bridge's access-control entry: the native host (when it
lands) accepts *that exact origin* and nothing else - the open-API
ruling (Oct 15): the schema ships open, any project may consume the
rect, and the browser's own install check is the whole handshake. No
pairing, no token, no app allow-list.

## v1 manifest notes

`permissions: ["debugger", "nativeMessaging", "tabs", "downloads"]` —
`downloads` is here because v1 writes the bridge file through
`chrome.downloads` (the blob download overwriting
`Downloads\PanelBoss\rect`): it is the only file write an MV3 service
worker can do with **zero** native-host plumbing. `nativeMessaging`
rides along for the future host, below.

## Future: the native-messaging host (measured dead twice today)

When the DRM lanes need a content script (a world the debugger attach
cannot always read), the bridge should ride `nativeMessaging` instead
of the download dance. Today's measurement burned the two obvious
manifest shapes on this box — **the next lane should skip them:**

1. **The .cmd-wrapper manifest shape dies at stdin EOF.** A host
   manifest pointing at a `.cmd` that pipes into python arrives with
   the pipe's ownership confused: the wrapper exits at stdin EOF
   before the host has answered, and Chrome reports the disconnected
   port. Do not re-derive it; it is the wrapper, not the host.
2. **The two-token `pythonw` manifest form FAILED on this Edge**
   (`path: pythonw.exe` + one script argument): Edge 156 does not
   hand the host its stdin length-prefixed frames the way the token
   split expects — the host boots and never hears the message.

The shape that remains untried (and the one the next lane should
start from): one absolute exe path, no wrapper, no shell, with the
stdin reading the 4-byte LE length prefix the spec mandates before
EVERY frame, and the host registered under the extension's own ID.
