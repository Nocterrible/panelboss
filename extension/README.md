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

## Loading it in Opera GX (the shipped route)

Opera GX reads Chrome extensions through the **Chrome AI / Chrome
App Launcher-style "Install Chrome Extensions" add-on** from the Opera
add-ons store:

1. Install the "Install Chrome Extensions" add-on from
   `addons.opera.com` (search "Chrome extensions" there).
2. Open this folder's parent in the loader: Menu → Extensions →
   ⚙ (Manage Extensions in Opera / the add-on's own "Load unpacked"
   affordance) → pick `extension/` (the folder holding
   `manifest.json`).
3. Pin the icon (puzzle-piece → PanelBoss Companion). One click on it
   inside a YouTube/Netflix/Twitch/Vimeo/Disney+/Prime Video tab
   writes the bridge file; PanelBoss's video eye picks the click up on
   its next tick (freshest source wins, ties the file's).

## The measured dev-mode fact (Oct 15, this Edge)

`--load-extension=<dir>` on **Edge 156 is silently ignored** unless
the profile has *developer mode* enabled in `edge://extensions` —
the flag lands, the extension does not, and nothing says so. That
is why the shipped install path is the store/loader flow (or the
`edge://extensions` → "Load unpacked" button with the developer-mode
toggle ON), not a launch flag: a flag-launched extension on a
developer-mode-off profile reads as "the feature is broken" when
the truth is one silent policy. (Opera GX carries the same discipline
through its Chrome-extension add-on; enable developer mode there
before expecting an unpacked load.)

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
