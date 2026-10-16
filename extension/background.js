/* PanelBoss Companion - the manual "veil this video" trigger, v0.2.0.
 *
 * One click on the toolbar icon, once, no timers, no pumps: ask the
 * active tab ONE question with chrome.scripting - the same class of
 * call every ad blocker uses to find things on a page (the owner's
 * ruling, Oct 16, after v0.1.1's debugger route proved it can hold a
 * silent, banner-raising conversation with Opera: "we need to not do
 * that this way if we can avoid it"). The answer is the SAME string
 * the RECT_JS constant holds - the byte-twin of panelboss/videoeye.py's
 * constant (the suite pins the pairing) - and the geometry lands in
 * the bridge file via chrome.downloads (the zero-native-host-plumbing
 * writer: the blob lands at <browser download dir>\PanelBoss\rect,
 * where PanelBoss reads; the %APPDATA%\PanelBoss\rect doorway waits
 * for the future native host - see README, including the two manifest
 * shapes that died on this Edge and why the next lane should not
 * retry them).
 *
 * NO DEBUGGER, NO BANNER, NO PORT: nothing to attach, nothing that
 * can outlive the click, nothing that tells the page a measuring tool
 * arrived. The awaits still ride withTimeout - every way this flow can
 * die answers with its own badge word (att/ask/slow/novid/json/win/dl
 * /veiled), because the v0.1.0 build's silent wordless death is the
 * reason the word list exists at all.
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
  let inj;
  try {
    // the ad-blocker class of call: one function, serialized into the
    // tab's world, its return value handed back. The function is
    // SELF-CONTAINED (executeScript serializes it alone - no closures
    // ride), so the eye's own string comes in as an ARG and eval runs
    // it there; the suite pins that the shipped string is byte-exact.
    inj = await withTimeout(chrome.scripting.executeScript({
      target: {tabId: tab.id, injectImmediately: true},
      func: (src) => eval(src),
      args: [RECT_JS],
    }), 5000, "slow");
  } catch (e) {
    say("ask");                // the injection itself was refused
    return;                    // (restricted page, or a browser that
}                              // says no to scripting)
  const v = inj && inj[0] && inj[0].result;
  if (!v || v === "null") {
    say("novid");              // the page answers no video element:
    return;                    // nothing to veil, nothing to write
  }
  let row;
  try { row = JSON.parse(v); }
  catch (e) { say("json"); return; }
  let win;
  try {
    win = await withTimeout(chrome.windows.get(tab.windowId),
                            5000, "slow");
  } catch (e) {
    say("win");                // the desk bounds are the one thing
    return;                    // the fold cannot be computed without
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
    say("dl");                 // the download was REFUSED (a blocked
  }                            // downloads permission reads exactly
}                              // like this word

function say(word) {
  try {
    chrome.action.setBadgeText({text: word});
    chrome.action.setBadgeBackgroundColor({color: "#333"});
  } catch (e) {}
}

chrome.action.onClicked.addListener(veil);
