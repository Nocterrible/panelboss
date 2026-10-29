/* PanelBoss Companion - the AUTOMATIC lane + the measure for the test
 * button, v0.4.6 (the page REPORTS its window origin - screenX/screenY
 * - so the fold stops guessing the borders, and the scroll listener
 * rides the CAPTURE phase so inner scrollers reach it too).
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
 * EVENT-DRIVEN, plus ONE CLOCK (v0.4.6, the boot-trust cure): the
 * app's boot law reads the doorway file's mtime against the machine's
 * uptime, so the stamp must stay ALIVE while a movie is - a stale row
 * is no longer a rumor, it is a corpse. A declared 10 s setInterval
 * beats while a video plays: if the media clock ADVANCED since the
 * last beat the row re-sends WITHOUT the dedupe judgement (the
 * refresh itself is the message: a real steady movie rewrites the
 * file every ten seconds); if the clock FROZE while the state said
 * playing, paused:true goes out - TESTIMONY against the RECEIPT, the
 * owner's restored-tab freeze (the state word lies, the media clock
 * cannot), and a frozen playback lifts within a beat instead of
 * haunting the desk until a manual resync. On play it measures and
 * sends the row to the background (chrome.runtime.sendMessage - the
 * background folds in the window bounds and hands it to the native
 * host). On pause/ended it sends
 * the same row with paused:true - the
 * app's eye skips a paused row, so the veil lifts on the next tick,
 * faster than the grace ever could. The ring's hole FOLLOWS the video
 * (the owner's first-UAT clip, Oct-16): resize, scroll, fullscreen and
 * the SPA's DOM churn all re-measure; the push dedupes on identical
 * rows, so the noise stays one string compare.
 */

// the measure - the SAME row shape every lane ships, so the app's fold
// treats all of them identically. rect is the video's viewport box
// (left/top/width/height in CSS px), dpr the device pixel ratio,
// paused the live playback state, scroll the [scrollX, scrollY] pair
// (the future DRM lane reads document space from it), view the inner
// [width, height] the fold's chrome correction needs, and origin the
// window's OWN report of where its viewport sits on the desk
// (screenX/screenY, DIP): a maximized window's borders hang OFF screen
// (measured bounds.left=-8, Oct 16), so the fold's even-split border
// guess is a guess and the report is the truth (v0.4.2).
function measure() {
  const v = currentVideo();
  if (!v) return null;
  return {
    rect: v.getBoundingClientRect(),
    dpr: window.devicePixelRatio,
    paused: v.paused,
    scroll: [window.scrollX, window.scrollY],
    view: [window.innerWidth, window.innerHeight],
    origin: [window.screenX, window.screenY],
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
// THE HOP, SPLIT (v0.4.6): sendRow is the transport - the ack
// rollback lives HERE, so a refused delivery un-commits the dedupe
// whichever lane sent it - and push keeps the DEDUPE JUDGEMENT for
// the event path (exactly today's law). The beat calls sendRow
// directly: it re-sends on purpose, the refresh itself is its
// message.
function sendRow(row) {
  try {
    // ACK-AWARE (dossier H): the commit happens BEFORE the send, and
    // the CALLBACK form is the refusal detector - the background acks
    // DELIVERY (the veil push to the host landed), so lastError (a
    // dead/absent background) or a not-ok ack un-sends the row. The
    // try/catch still covers the sync throw (gate finding 3): a
    // transient death is not a sticky clip - the next event of any
    // kind re-offers the row.
    chrome.runtime.sendMessage({ op: "veil", payload: row },
      (res) => {
        if (chrome.runtime.lastError || !res || !res.ok) lastSent = "";
      });
  } catch (e) {
    lastSent = "";
  }
}
function push(paused) {
  const row = measure();
  if (!row) return;
  if (paused != null) row.paused = paused;   // != null covers both
                                             // undefined and null (the
                                             // measured state stands)
  const wire = JSON.stringify(row);
  if (wire === lastSent) return;             // the judgement stays
  lastSent = wire;                           // here, event-path only
  sendRow(row);
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
      // PLAYING-ONLY HEARTBEAT (dossier H): timeupdate fires ~4/s,
      // and ONLY while the clock advances (a paused video goes quiet
      // - no clock is written, no pump). Throttled to one push(false)
      // per ~5s on the SAME wire()/dedupe path - a steady frame is a
      // no-op string compare, a moved row is a genuine re-offer the
      // pause/ended lanes never see.
      let lastBeat = 0;
      v.addEventListener("timeupdate", () => {
        const now = Date.now();
        if (now - lastBeat < 5000) return;
        lastBeat = now;
        push(false);
      });
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
  // CAPTURE phase (v0.4.2): a page's own scroller (YouTube's filmstrip,
  // any overflow container) fires scroll on the ELEMENT, and scroll
  // does not bubble - it only traverses the capture path. A window-level
  // listener without capture:true watched every page-level scroll and
  // never saw the ones that move the video.
  window.addEventListener("scroll", onMove,
                          { passive: true, capture: true });
  document.addEventListener("fullscreenchange", onMove);
  arm();
  // a video that is ALREADY playing when the script lands (a reload
  // mid-playback) is armed by the same observer; the playing event has
  // already fired, so ask once, synchronously, for the current state.
  for (const v of document.querySelectorAll("video")) {
    if (!v.paused && v.readyState >= 2) push(false);
  }
  // THE UNCONDITIONAL BEAT (v0.4.6, the boot-trust cure): the app's
  // boot law reads the doorway's mtime against the uptime, so the
  // stamp must stay alive while a movie is. Ten seconds, playing
  // only, and NO dedupe judgement on this branch - the refresh is
  // itself the message (the pins hold the shape). A clock FROZEN
  // while the state says playing is the owner's restored-tab freeze:
  // the state word is the receipt, the media clock is the testimony,
  // and testimony wins - paused:true goes out and the veil lifts
  // within a beat instead of haunting the desk until a manual
  // resync.
  let lastBeatTime = -1;
  function beat() {
    const v = currentVideo();
    if (!v || v.paused || v.readyState < 2) return;   // nothing to prove
    const row = measure();
    if (!row) return;
    if (v.currentTime !== lastBeatTime) {
      lastBeatTime = v.currentTime;
      sendRow(row);                                   // the beat lands
    } else {
      row.paused = true;
      sendRow(row);                                   // the clock spoke
    }
  }
  // GOODBYE (v0.4.6, the Oct 26 incident, the hidden GX sleeping-tab
  // class): a tab Chromium hides sleeps and fires no pause - it must
  // go to sleep SAYING paused, or the desk keeps a ring around a
  // movie no eye can see until the app restarts.
  function goodbye() {
    const row = measure();
    if (row) { row.paused = true; sendRow(row); }
  }
  window.addEventListener("pagehide", goodbye);
  document.addEventListener("visibilitychange",
                            () => { if (document.hidden) goodbye(); });
  setInterval(beat, 10000);
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