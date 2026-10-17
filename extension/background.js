/* PanelBoss Companion - the manual "veil this video" trigger + the
 * AUTOMATIC lane, v0.4.0.
 *
 * TWO lanes, one host:
 *   - AUTOMATIC (the new default): a declared content script
 *     (content.js) lives in the page, measures the video natively, and
 *     listens for play/pause/ended. A play pushes the row here via
 *     runtime.sendMessage; this background folds in the window bounds
 *     (content scripts have no chrome.windows) and hands it to the host.
 *     A video STARTS playing -> the desk frames it, no click.
 *   - CLICK (stays): the toolbar icon asks the active tab ONE question
 *     with chrome.scripting (the ad-blocker class of call - the owner's
 *     Oct 16 ruling after the debugger's banner) and hand the answer to
 *     the LOCAL native host over chrome.runtime native messaging. It is
 *     the owner's calibration gesture, and all the DRM lane will ever
 *     get from this design.
 *
 * The host writes the geometry to the app's own doorway file; the
 * app's eye reads it. No network, no remote code, no eval, no timers
 * (a play event is exactly the timer this extension never writes).
 *
 * THE API IS OPEN (MIT): every message is a plain JSON object with an
 * "op", and the "capabilities" op self-describes what this extension
 * can send - including the automatic lane it now announces ("auto").
 * The one ACL is the extension's own id: the native-host manifest lists
 * OUR origin, the browser's install check is the whole handshake, no
 * pairing, no token.
 *
 * Every way the click can die answers with its own badge word
 * (ask/slow/novid/json/win/nm), so a silent wordless death - the class
 * that sank v0.1.0 - can never recur. The automatic lane is quiet by
 * design (a page push must not nag: the veil either lands or it does
 * not, and the app's grace law retracts either way).
 */

// the measure, as a STATIC function (never eval'd): executeScript
// serializes it alone into the tab's world, no closures ride. It
// returns the same row shape every version ships - rect (viewport CSS
// px), devicePixelRatio, paused, the scroll pair (the future DRM lane
// reads document space from it), and the inner size the fold needs.
function measureVideo() {
  const v = document.querySelector("video");
  if (!v) return null;
  return {
    rect: v.getBoundingClientRect(),
    dpr: window.devicePixelRatio,
    paused: v.paused,
    scroll: [window.scrollX, window.scrollY],
    view: [window.innerWidth, window.innerHeight],
  };
}

const HOST = "com.nocterrible.panelboss";

const FAMILY = /OPR\//.test(navigator.userAgent) ? "opera_gx"
             : /Edg\//.test(navigator.userAgent) ? "edge"
             : "chrome";

function withTimeout(p, ms, word) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject({ badge: word }), ms);
    p.then(v => { clearTimeout(t); resolve(v); },
           e => { clearTimeout(t); reject(e); });
  });
}

function say(word) {
  try {
    chrome.action.setBadgeText({ text: word });
    chrome.action.setBadgeBackgroundColor({ color: "#333" });
  } catch (e) {}
}

// one native message to the host, answer back (the host replies with a
// frame we read once; a missing host or a broken pipe reads as the nm
// death word, never a hung click).
function sendNative(msg, ms) {
  return new Promise((resolve, reject) => {
    let port;
    try {
      port = chrome.runtime.connectNative(HOST);
    } catch (e) {
      reject({ badge: "nm" });
      return;
    }
    let done = false;
    const finish = (fn, v) => {
      if (done) return;
      done = true;
      clearTimeout(t);
      try { port.disconnect(); } catch (e) {}
      fn(v);
    };
    const t = setTimeout(() => finish(reject, { badge: "slow" }), ms);
    port.onMessage.addListener((m) => finish(resolve, m));
    port.onDisconnect.addListener(() => finish(reject, { badge: "nm" }));
    port.postMessage(msg);
  });
}

// the shared fold: a content-space row -> stamp bounds + lane + ts,
// then push to the host. Both lanes land here; the click lane reports
// a badge word and is IMMEDIATE (lane "click"), the automatic lane
// stays quiet and is delayed app-side (lane "auto" - the app's
// [videodim].delay_s rail holds a play-push before it frames).
async function push(row, windowId, lane, badgeWord) {
  let win;
  try {
    win = await withTimeout(chrome.windows.get(windowId), 5000,
                            badgeWord || "win");
  } catch (e) { return; }
  const payload = {
    rect: row.rect, dpr: row.dpr, paused: row.paused,
    scroll: row.scroll, view: row.view, lane: lane,
    bounds: { left: win.left, top: win.top,
              width: win.width, height: win.height },
    family: FAMILY, ts: Date.now() / 1000,
  };
  try {
    const ans = await sendNative({ op: "veil", payload }, 5000);
    if (badgeWord) say(ans && ans.ok ? "veil" : "nm");
  } catch (e) {
    if (badgeWord) say(e && e.badge ? e.badge : "nm");
  }
}

async function veil(_tab) {
  const tab = _tab && typeof _tab.id === "number" ? _tab
            : (await chrome.tabs.query({ active: true,
                                         currentWindow: true }))[0];
  if (!tab || typeof tab.id !== "number") return;

  let inj;
  try {
    inj = await withTimeout(chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: measureVideo,
    }), 5000, "slow");
  } catch (e) {
    say("ask");                    // the injection was refused (a
    return;                        // restricted page, or a browser that
  }                                // says no to scripting)
  const row = inj && inj[0] && inj[0].result;
  if (!row) {
    say("novid");                  // no <video> element: nothing to
    return;                        // veil, nothing to send
  }
  await push(row, tab.windowId, "click", "veil");
}

chrome.action.onClicked.addListener(veil);

// the AUTOMATIC lane: the content script measures and sends here; this
// background folds the bounds and pushes to the host. Quiet (no badge)
// and lane "auto" (the app's delay rail governs it) - a page push must
// not nag, the veil lands or the grace retracts.
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.op !== "veil" || !msg.payload) return;
  const row = msg.payload;
  // the content script can't know its own window id; the sender does.
  const windowId = sender.tab && sender.tab.windowId;
  if (typeof windowId !== "number") return;
  push(row, windowId, "auto", null);   // quiet lane, no badge word
  sendResponse({ ok: true });          // ack so a lost send reads in
  return false;                        // the page's devtools, no hang
});