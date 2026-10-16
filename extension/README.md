# PanelBoss Companion (extension, v0.2)

The manual "veil this video" trigger for PanelBoss's Movie theater
mode. One click on the toolbar icon: measure the playing video with
`chrome.scripting.executeScript` — the ad-blocker class of call, one
self-contained function into the tab and its answer back — write the
answer to the bridge file (`PanelBoss/rect` under the browser's OWN
download directory, the zero-native-host-plumbing writer, via
`chrome.downloads`), done. No timers, no pumps, no banner. The video
rect PanelBoss folds to physical pixels the same way it does for the
port path (`Browser.getWindowBounds` truth beats `window.screenX`,
which measures (0,0) lies on occluded windows).

## The banner lesson (Oct 16, why this is `scripting` and not `debugger`)

v0.1 attached `chrome.debugger` for the duration of one question. On
this desk's Opera GX the click raised the *"X is debugging this tab"*
banner, wrote no file, and gave no badge word — a silent, banner-
raising hang of the kind the debugger can hold when a CDP question
never answers. The owner's ruling killed the route on sight: *"we need
to not do that this way if we can avoid it — other extensions don't
need to debug pages to find things like ads."* Correct: the measuring
question needs the DOM, not the protocol; `scripting` answers it in
the page's world, leaves nothing attached, and cannot outlive its own
click. **The debugger is the third dead manifest shape** — with the
two native-host forms below — do not re-derive it for a click-once
trigger: the banner is user-visible cost, and the silent-hang class is
real on Opera.

The data path of the FEATURE remains the eye's own two channels: this
bridge file (manual, zero-plumbing) and — dormant by owner ruling,
config-readable but off the UI — the debug port for the automatic
lane. The extension is not required for a port-flagged launch.

## Load it (measured on Opera GX, Oct 15-16)

1. Open `opera://extensions` and enable **Download from Chrome Web
   Store** (Opera's Chrome-extension door; with it off there is no
   unpacked door at all) and **Developer mode**.
2. **Load unpacked** — point it at this folder (the one holding
   `manifest.json`). Pin the icon (puzzle-piece → PanelBoss
   Companion). After any file change here, hit the extension card's
   **reload** arrow.
3. Once published, the Chrome Web Store route replaces steps 1-2
   (Opera installs it through the same door); the unpacked route
   stays the developer's.

The click needs a video tab: one press writes the bridge file and the
icon answers on itself with a word — `veiled` (geometry written),
`novid` (the page has no `<video>`), `ask`/`slow`/`win`/`dl` (which
step refused; see `background.js`, every death is named). The shelf
is `<browser download dir>\PanelBoss\rect` — **the browser's own
directory, not the OS Downloads folder** (PanelBoss reads every
browser's `download.default_directory` out of its Preferences —
the "shelf law", pinned in `videoeye_test` — because on this desk GX
is configured to `C:\FastDLs` and a naive Downloads assumption left a
good click unread). PanelBoss's eye picks the click up on its next
tick (freshest source wins, ties the file's).

**The dev-mode caveat (measured, twice this week):** an unpacked
load is **silently ignored** without developer mode - the flag or the
button lands, the extension does not, and nothing says so (Edge 156
with `--load-extension`; Opera GX keeps the same discipline behind
its Chrome door). When the feature "does nothing", check the toggle
before suspecting the code.

**The id is the ACL.** The extension id on the browser's details page
is the bridge's access-control entry: the native host (when it
lands) accepts *that exact origin* and nothing else — the open-API
ruling (Oct 15): the schema ships open, any project may consume the
rect, and the browser's own install check is the whole handshake. No
pairing, no token, no app allow-list.

## Manifest notes (v0.2)

`permissions: ["scripting", "tabs", "downloads"]` — `downloads` is
here because the bridge file is written through `chrome.downloads`
(the blob download overwriting `PanelBoss\rect`): it is the only file
write an MV3 service worker can do with **zero** native-host plumbing.
`debugger` and `nativeMessaging` left Oct 16: the manifest's law is
that it carries its stated word, and neither call site survives any
more (the host, below, is a documented FUTURE doorway, not a
permission).

## Future: the native-messaging host (measured dead twice, Oct 15)

When the DRM lanes need a persistent content script (an observer the
one-shot `executeScript` cannot be — it answers once and is gone),
the bridge should ride `nativeMessaging` instead of the download
dance. That day the `nativeMessaging` permission returns WITH its
first call site, never before. The measurement burned the two obvious
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
