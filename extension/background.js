/* PanelBoss Companion - the manual "veil this video" trigger, v0.1.1.
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
 *
 * v0.1.1 (Oct 16, the owner's silent first click): every way this
 * flow can now die answers with its OWN badge word - the old build
 * labeled every attach failure 'busy' (honest only when DevTools
 * owned the tab) and died wordless after the attach, which is
 * exactly the no-evidence state the owner found (the debugging
 * banner up, no file, no word). The awaits that can HANG (Opera's
 * CDP can hold a question forever) run behind withTimeout: the
 * banner must never outlive the click's own patience, and the
 * finally-detach stays the one door out.
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

function withTimeout(p, ms, word) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject({badge: word}), ms);
    p.then(v => { clearTimeout(t); resolve(v); },
           e => { clearTimeout(t); reject(e); });
  });
}

async function veil(_tab) {
  const tab = _tab && _tab.id !== undefined ? _tab : await activeTab();
  if (!tab || tab.id === undefined) return;
  try {
    await chrome.debugger.attach({tabId: tab.id}, "1.3");
  } catch (e) {
    // 'busy' is reserved for the truth it names (DevTools owns the
    // tab); any OTHER handshake refusal is its own word now, because
    // the old catch-all made every attach death look like the one
    // the user could fix themselves (measured Oct 16: banner UP
    // after the click, so attach is NOT our failure on GX - but the
    // next family that blocks the API will name itself here).
    say(/being debugged|Cannot access a chrome/i.test(String(e && e.message))
        ? "busy" : "att");
    return;
  }
  try {
    let r;
    try {
      r = await withTimeout(chrome.debugger.sendCommand(
          {tabId: tab.id}, "Runtime.evaluate",
          {expression: RECT_JS, returnByValue: true}), 5000, "slow");
    } catch (e) {
      say(e && e.badge ? e.badge : "ask");    // 'slow' = Opera held
      return;                                // the question open;
    }                                        // 'ask' = the answer
                                               // was refused
    const v = r && r.result && r.result.value;
    if (!v || v === "null") {
      say("novid");            // the page answers no video element:
      return;                  // nothing to veil, nothing to write
    }
    let row;
    try { row = JSON.parse(v); }
    catch (e) { say("json"); return; }
    let win;
    try {
      win = await withTimeout(chrome.windows.get(tab.windowId),
                              5000, "slow");
    } catch (e) {
      say("win");              // the desk bounds are the one thing
      return;                  // the fold cannot be computed without
    }
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
        conflictAction: "overwrite"});
      say("veiled");
    } catch (e) {
      say("dl");               // the download was REFUSED (a blocked
    }                          // downloads permission reads exactly
  } finally {                  // like this word, and reads like
    // NOTHING when you have no
    try { await chrome.debugger.detach({tabId: tab.id}); } catch (e) {}
  }                            // word at all
}

function say(word) {
  try {
    chrome.action.setBadgeText({text: word});
    chrome.action.setBadgeBackgroundColor({color: "#333"});
  } catch (e) {}
}

chrome.action.onClicked.addListener(veil);
