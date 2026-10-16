/* PanelBoss Companion - the manual "veil this video" trigger, v1.
 *
 * One click on the toolbar icon, once, no timers, no pumps: attach
 * the debugger to the active tab, ask the SAME question PanelBoss
 * asks over the debug port (the RECT_JS below is the byte-twin of
 * panelboss/videoeye.py's constant - the suite pins it), and write
 * the answer to the bridge file via chrome.downloads (the zero-
 * native-host-plumbing writer: the blob lands at
 * <Downloads>\PanelBoss\rect, where PanelBoss also reads; the
 * %APPDATA%\PanelBoss\rect doorway waits for the future native
 * host - see README, including the two manifest shapes that died
 * on this Edge today and why the next lane should not retry them).
 *
 * The debugger rides the click only: detach the moment the answer
 * lands. chrome.windows.get carries the outer window bounds (DIP
 * px) so PanelBoss can fold content space to physical desktop px
 * exactly like the Browser.getWindowBounds path does.
 */
const RECT_JS = "(function(){var v=document.querySelector('video');return v?JSON.stringify({rect:v.getBoundingClientRect(),dpr:window.devicePixelRatio,paused:v.paused,scroll:[window.scrollX,window.scrollY],view:[window.innerWidth,window.innerHeight]}):'null';})()";

/* the family PanelBoss knows this browser as: the UA is the honest
 * tell - Opera GX answers OPR/, Edge answers Edg/, Chrome answers
 * Chrome/ and is the only one left standing */
const FAMILY = /OPR\//.test(navigator.userAgent) ? "opera_gx"
             : /Edg\//.test(navigator.userAgent) ? "edge"
             : "chrome";

async function activeTab() {
  const t = await chrome.tabs.query({active: true, currentWindow: true});
  return t && t[0];
}

async function veil(_tab) {
  const tab = _tab && _tab.id !== undefined ? _tab : await activeTab();
  if (!tab || tab.id === undefined) return;
  try {
    await chrome.debugger.attach({tabId: tab.id}, "1.3");
  } catch (e) {
    say("busy");   // already attached (DevTools open): say it, quit
    return;
  }
  try {
    const r = await chrome.debugger.sendCommand(
        {tabId: tab.id}, "Runtime.evaluate",
        {expression: RECT_JS, returnByValue: true});
    const v = r && r.result && r.result.value;
    if (!v || v === "null") {
      say("no vid");           // the page answers no video element:
      return;                  // nothing to veil, nothing to write
    }
    let row;
    try { row = JSON.parse(v); } catch (e) { return; }
    const win = await chrome.windows.get(tab.windowId);
    row.bounds = {left: win.left, top: win.top,
                  width: win.width, height: win.height};
    row.family = FAMILY;
    row.ts = Date.now() / 1000;
    const blob = new Blob([JSON.stringify(row) + "\n"],
                          {type: "application/octet-stream"});
    const url = URL.createObjectURL(blob);
    try {
      await chrome.downloads.download({
        url, filename: "PanelBoss/rect", saveAs: false,
        conflictAction: "overwrite", exists: "overwrite"});
      say("veiled");
    } finally {
      // the blob URL outlives the click; the download resolves by
      // the time this worker next wakes, and revoked URLs leak
      // nothing the next click cannot reuse
    }
  } finally {
    try { await chrome.debugger.detach({tabId: tab.id}); } catch (e) {}
  }
}

function say(word) {
  try {
    chrome.action.setBadgeText({text: word});
    chrome.action.setBadgeBackgroundColor({color: "#333"});
  } catch (e) {}
}

chrome.action.onClicked.addListener(veil);
