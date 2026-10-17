/* PanelBoss Companion - the AUTOMATIC lane + the manual test gesture,
 * v0.4.0.
 *
 * TWO lanes, one host, ONE measure (content.js owns it):
 *   - AUTOMATIC (the feature): a declared content script (content.js)
 *     lives in the page, measures the video natively, and listens for
 *     play/pause/ended. A play pushes the row here via
 *     runtime.sendMessage; this background folds in the window bounds
 *     (content scripts have no chrome.windows) and hands it to the host.
 *     A video STARTS playing -> the desk frames it, no click.
 *   - TEST (the button): the toolbar icon asks the tab's own content
 *     script to measure RIGHT NOW (chrome.tabs.sendMessage, no
 *     scripting, no activeTab) and hands the same folded row to the
 *     host. It is the owner's calibration gesture - demoted since the
 *     automatic lane landed - and all the DRM lane will ever get from a
 *     click.
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
 * Every way the test click can die answers with its own badge word
 * (site/novid/slow/win/nm), so a silent wordless death - the class that
 * sank v0.1.0 - can never recur. The automatic lane is quiet by design
 * (a page push must not nag: the veil either lands or it does not, and
 * the app's grace law retracts either way).
 */

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
// then push to the host. Both lanes land here; the test lane reports
// a badge word and is IMMEDIATE (lane "click"), the automatic lane
// stays quiet and is gated app-side (lane "auto" - the app's
// [videodim].idle_sec rail holds a play-push before it frames).
async function push(row, windowId, lane, badgeWord) {
  let win;
  try {
    win = await withTimeout(chrome.windows.get(windowId), 5000,
                            badgeWord || "win");
  } catch (e) { return; }
  const payload = {
    rect: row.rect, dpr: row.dpr, paused: row.paused,
    scroll: row.scroll, view: row.view, lane: lane,
    origin: row.origin || null,   // the window's own report (v0.4.2)
                                  // - pass-through, never derived
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

  // the tab's own content script measures (no scripting, no activeTab:
  // the measure lives in content.js, which the site list already
  // loaded). A tab off the site list has no content script - the send
  // rejects and we say so.
  let row;
  try {
    row = await withTimeout(
      chrome.tabs.sendMessage(tab.id, { op: "measure" }),
      5000, "slow");            // timeout is SLOWNESS, not absence -
  } catch (e) {                 // the gate's finding 3: one word for
    say(e && e.badge ? e.badge : // both made a present-but-stalled
        "site");                // content script read as off-list.
    return;                     // The timeout pre-labels (badge) and
  }                             // wins; true absence (no content
                                // script to answer) carries no badge
                                // and keeps the honest 'site'.
  if (!row) {
    say("novid");                  // no <video> element: nothing to
    return;                        // veil, nothing to send
  }
  await push(row, tab.windowId, "click", "veil");
}

chrome.action.onClicked.addListener(veil);

// the AUTOMATIC lane: the content script measures and sends here; this
// background folds the bounds and pushes to the host. Quiet (no badge)
// and lane "auto" (the app's idle rail governs it) - a page push must
// not nag, the veil lands or the grace retracts.
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !sender || !sender.tab) return;
  if (msg.op === "veil" && msg.payload) {
    push(msg.payload, sender.tab.windowId, "auto", null);
    sendResponse({ ok: true });
  }
  return false;                    // synchronous ack, no keep-alive
});