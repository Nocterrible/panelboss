/* PanelBoss Companion popup logic (v0.4.3): the readout.
 *
 * ONE question, the same open API the test button uses: the active
 * tab's content script answers {op:"measure"} with the exact row the
 * automatic lane would push (or null: no <video> here). No new
 * permissions (tabs.query works without the "tabs" permission as
 * long as we never read url/title - and we don't), no network, no
 * timers: the popup measures when it opens and when the button says
 * so. The words are honest: an off-list site has no content script
 * to answer (chrome.runtime.lastError), a listed page without a
 * video answers null. */

"use strict";

const $ = (id) => document.getElementById(id);

function setState(cls, text) {
  const el = $("state");
  el.className = cls;
  el.textContent = text;
}

function row(k, v) {
  const tr = document.createElement("tr");
  const a = document.createElement("td");
  a.className = "k";
  a.textContent = k;
  const b = document.createElement("td");
  b.className = "v";
  b.textContent = v;
  tr.append(a, b);
  $("rows").append(tr);
}

async function refresh() {
  $("rows").replaceChildren();
  let tab;
  try {
    const [t] = await chrome.tabs.query({ active: true,
                                          currentWindow: true });
    tab = t;
  } catch (e) { /* cannot happen; the fall-through says so */ }
  if (!tab || typeof tab.id !== "number") {
    setState("off", "no active tab");
    return;
  }
  let r;
  try {
    r = await chrome.tabs.sendMessage(tab.id, { op: "measure" });
  } catch (e) {
    setState("off", "this site has no companion watcher");
    $("note").textContent =
      "the content script only lives on the sites listed in the " +
      "manifest - the extension is quiet everywhere else.";
    return;
  }
  if (!r || !r.rect) {
    setState("none", "no video on this page");
    return;
  }
  setState(r.paused ? "paused" : "playing",
           r.paused ? "PAUSED" : "PLAYING");
  const R = r.rect;
  row("video box", Math.round(R.left) + ", " + Math.round(R.top) +
      "  " + Math.round(R.width) + "x" + Math.round(R.height) + " px");
  row("dpr", String(r.dpr));
  row("viewport", (r.view || []).map(Math.round).join(" x ") + " px");
  row("scroll", (r.scroll || []).map(Math.round).join(", "));
  row("window origin", (r.origin || []).map(Math.round).join(", ") +
      " (page report)");
  const btn = $("veil");
  btn.disabled = false;
  btn.onclick = async () => {
    btn.disabled = true;
    btn.textContent = "sending...";
    try {
      const ans = await chrome.runtime.sendMessage({ op: "veil_now" });
      btn.textContent = ans && ans.word === "veil"
        ? "sent - the desk should frame it"
        : "the click said: " + ((ans && ans.word) || "?");
    } catch (e) {
      btn.textContent = "background unreachable";
    }
    btn.disabled = false;
  };
}

refresh();
