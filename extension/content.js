/* PanelBoss Companion - the AUTOMATIC lane + the measure for the test
 * button, v0.4.1 (the hole follows the video - motion events re-push,
 * deduped).
 *
 * A declared content script (manifest content_scripts.matches). It
 * already lives in the page, so it measures the <video> natively:
 * getBoundingClientRect is a DOM call it owns. No executeScript, no
 * activeTab, no host permission - and it is the ONE measure in the
 * whole extension: the automatic lane reads it on play/pause/ended,
 * and the test button (background.js, action.onClicked) asks for it
 * via chrome.runtime.sendMessage({op:"measure"}).
 * ADMITTED (the gate, Oct 16): content_scripts defaults all_frames
 * false, so this is a TOP-FRAME measure - a player inside an iframe
 * (twitch embeds, SPA shells) is off the map SILENTLY. The honest
 * word lives here and in the README rather than in a feature: the
 * iframe lane rides the DRM dossier, not this wave.
 *
 * EVENT-DRIVEN, no timers, no pumps: a video "play" event is exactly
 * the timer this extension is NOT allowed to write. On play it measures
 * and sends the row to the background (chrome.runtime.sendMessage - the
 * background folds in the window bounds and hands it to the native
 * host). On pause/ended it sends the same row with paused:true - the
 * app's eye skips a paused row, so the veil lifts on the next tick,
 * faster than the grace ever could. The ring's hole FOLLOWS the video
 * (the owner's first-UAT clip, Oct-16): resize, scroll, fullscreen and
 * the SPA's DOM churn all re-measure; the push dedupes on identical
 * rows, so the tracking is event law, not a poll, and noise is one
 * string compare.
 */

// the measure - the SAME row shape every lane ships, so the app's fold
// treats all of them identically. rect is the video's viewport box
// (left/top/width/height in CSS px), dpr the device pixel ratio,
// paused the live playback state, scroll the [scrollX, scrollY] pair
// (the future DRM lane reads document space from it), view the inner
// [width, height] the fold's chrome correction needs.
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
// feature).
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
// DEDUPE (the Oct-16 clip cure): pushes ride every event that can
// MOVE the video (play, pause, resize, scroll, fullscreen, the SPA's
// DOM churn), so the ring must not shout - an identical row (JSON
// compare) is not a change and never travels. `paused` is the EVENT's
// word (play false, pause/ended true); null means "trust the
// measured state" - the motion pushes, where no play/pause happened.
let lastSent = "";
function push(paused) {
  const row = measure();
  if (!row) return;
  if (paused != null) row.paused = paused;   // != null covers both
                                             // undefined and null (the
                                             // measured state stands)
  const wire = JSON.stringify(row);
  if (wire === lastSent) return;
  lastSent = wire;
  try {
    chrome.runtime.sendMessage({ op: "veil", payload: row });
  } catch (e) {
    // a dead background is not the page's problem - BUT the dedupe
    // must not let a transient SW death become a sticky clip (gate
    // finding 3): the refused row is un-sent, so the next event of
    // any kind re-offers it.
    lastSent = "";
  }
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
  // The churn handler ALSO re-measures (the clip cure): the SPA
  // repositions the player (theater mode, the engagement panel) with
  // no resize, no scroll - the dedupe in push() makes the re-measure
  // cost a string compare when the geometry stands still.
  const onMove = () => push(null);
  new MutationObserver(() => {
    arm();
    onMove();
  }).observe(document.body || document.documentElement,
    // attributes INCLUDED (gate finding 4): YouTube's theater-mode and
    // engagement-panel reflow is largely class/style flips on
    // containers - childList never fires, and an internal resize
    // fires neither window event. The batch is microtask-coalesced
    // and the push dedupes, so the extra signal costs a measure and
    // a string compare per reflow.
    { childList: true, subtree: true,
      attributes: true, attributeFilter: ["style", "class"] });
  // the size/position events a re-laid-out player fires outright:
  window.addEventListener("resize", onMove);
  window.addEventListener("scroll", onMove, { passive: true });
  document.addEventListener("fullscreenchange", onMove);
  arm();
  // a video that is ALREADY playing when the script lands (a reload
  // mid-playback) is armed by the same observer; the playing event has
  // already fired, so ask once, synchronously, for the current state.
  for (const v of document.querySelectorAll("video")) {
    if (!v.paused && v.readyState >= 2) push(false);
  }
}

// the test button's question (background.js --> this page): measure
// RIGHT NOW. Answer with the same row shape; a null row means "no
// video here", which the background reads as its "novid" word.
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.op !== "measure") return;
  sendResponse(measure());
  return false;
});

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", wire);
} else {
  wire();
}