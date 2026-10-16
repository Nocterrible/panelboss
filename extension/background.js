/* PanelBoss Companion - the manual "veil this video" trigger, v0.3.0.
 *
 * One click on the toolbar icon, once, no timers, no pumps: ask the
 * active tab ONE question with chrome.scripting (the ad-blocker class
 * of call - the owner's Oct 16 ruling after the debugger's banner), and
 * hand the answer to the LOCAL native host over chrome.runtime
 * native messaging. The host writes the geometry to the app's own
 * doorway file; PanelBoss's eye reads it. No network, no remote code,
 * no eval - the measure function is a static, bundled FUNCTION (MV3's
 * CSP law: an eval string is remote-code-shaped and a store rejection).
 *
 * THE API IS OPEN (MIT): every message is a plain JSON object with an
 * "op", and the "capabilities" op self-describes what this extension
 * can send (the veil rect today; the DRM observer, site metadata, more
 * tomorrow). PanelBoss reads the capabilities the way any project may -
 * discover, never assume. The one ACL is the extension's own id: the
 * native-host manifest lists OUR origin, the browser's install check is
 * the whole handshake, no pairing, no token.
 *
 * Every way the click can die answers with its own badge word
 * (ask/slow/novid/json/win/nm), so a silent wordless death - the class
 * that sank v0.1.0 - can never recur.
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

  let win;
  try {
    win = await withTimeout(chrome.windows.get(tab.windowId),
                            5000, "slow");
  } catch (e) {
    say("win");                    // the desk bounds are the one thing
    return;                        // the fold cannot be computed without
  }
  row.bounds = { left: win.left, top: win.top,
                 width: win.width, height: win.height };
  row.family = FAMILY;
  row.ts = Date.now() / 1000;

  try {
    const ans = await sendNative({ op: "veil", payload: row }, 5000);
    say(ans && ans.ok ? "veiled" : "nm");
  } catch (e) {
    say(e && e.badge ? e.badge : "nm");
  }
}

chrome.action.onClicked.addListener(veil);