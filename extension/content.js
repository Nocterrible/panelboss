/* PanelBoss Companion - the AUTOMATIC lane, v0.4.0.
 *
 * A declared content script (manifest content_scripts.matches - the
 * site list the owner reads as "the tubes people actually watch"). It
 * already lives in the page, so it measures the <video> natively:
 * getBoundingClientRect is a DOM call it owns, no executeScript, no
 * activeTab, no host permission.
 *
 * EVENT-DRIVEN, no timers, no pumps: a video "play" event is exactly
 * the timer this extension is NOT allowed to write. On play it measures
 * and asks the background for the window bounds (content scripts have
 * no chrome.windows); the background folds the row and hands it to the
 * native host. On pause/ended it sends the same row with paused:true -
 * the app's eye skips a paused row, so the veil lifts on the next tick,
 * faster than the grace ever could.
 *
 * The click lane (background.js, action.onClicked) STAYS: it is the
 * owner's calibration gesture and the only thing the DRM lane will ever
 * get from this design. The automatic lane is the new default: a video
 * STARTS playing -> the desk frames it, no click.
 */

const HOST = "com.nocterrible.panelboss";

// the measure, native to the content script's world - the SAME row shape
// the click lane ships, so the app's fold treats both identically.
function measure() {
  const v = currentVideo();
  if (!v) return null;
  return {
    rect: v.getBoundingClientRect(),
    dpr: window.devicePixelRatio,
    paused: v.paused,
    scroll: [window.scrollX, window.scrollY],
    view: [window.innerWidth, window.innerHeight],
  };
}

// the "biggest playing-ish video" is the one the user is watching, not
// the first <video> in a sidebar (an ad-in-article timer is not the
// feature). A paused poster with no size is not a video yet.
function currentVideo() {
  const vids = Array.from(document.querySelectorAll("video"));
  if (!vids.length) return null;
  let best = null, bestArea = -1;
  for (const v of vids) {
    const r = v.getBoundingClientRect();
    const area = r.width * r.height;
    if (area > bestArea) { bestArea = area; best = v; }
  }
  return best;
}

// one hop to the background for the window bounds + the native send.
// The background answers nothing on purpose - a fire-and-forget push
// does not block the page, and the host's own reply is its receipt.
function push(paused) {
  const row = measure();
  if (!row) return;
  row.paused = paused;
  try {
    chrome.runtime.sendMessage({ op: "veil", payload: row });
  } catch (e) { /* a dead background is not the page's problem */ }
}

// attach to every video, once; listen for the events that matter. No
// interval, no polling - a play is an event, and events are free.
function wire() {
  const seen = new WeakSet();
  function arm() {
    for (const v of document.querySelectorAll("video")) {
      if (seen.has(v)) continue;
      seen.add(v);
      v.addEventListener("play", () => push(false));
      v.addEventListener("pause", () => push(true));
      v.addEventListener("ended", () => push(true));
    }
  }
  // the player may replace its <video> on navigation (YouTube SPA) -
  // re-arm on DOM churn, but only on a mutation, never on a clock.
  new MutationObserver(arm).observe(document.body || document.documentElement,
    { childList: true, subtree: true });
  arm();
  // a video that is ALREADY playing when the script lands (a reload
  // mid-playback) is armed by the same observer; the playing event has
  // already fired, so ask once, synchronously, for the current state.
  for (const v of document.querySelectorAll("video")) {
    if (!v.paused && v.readyState >= 2) push(false);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", wire);
} else {
  wire();
}