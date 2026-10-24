// Shared by the fork page (app.js) and the Safe{Wallet} panel (safe-app.js): the three cards, the
// stepper and the job stream. Renders what the server sends; computes nothing.
// Every string from the server may carry attacker-authored text, so it goes in via textContent only.

export const $ = (id) => document.getElementById(id);

export function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "onclick") n.onclick = v;
    else n.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return n;
}

export const short = (a) => (a && a.length > 12 ? `${a.slice(0, 6)}…${a.slice(-4)}` : a || "");
export const tidy = (t) => String(t).replace(/0x[0-9a-fA-F]{40}\b/g, (a) => short(a)).replaceAll(" -> ", " → ");
export const dot = (cls) => el("span", { class: `dot ${cls}` });
export const skeleton = () => [el("div", { class: "skeleton" }), el("div", { class: "skeleton" }), el("div", { class: "skeleton" })];
export const PILL = { MATCH: "success", ASK: "warning", REJECT: "danger" };
const KIND = { move: "Transfer", allow: "Approval", config: "Config" };
export const LABEL = { MATCH: "Match", ASK: "Needs answer", REJECT: "Rejected" };
// A link the server built from a fixed prefix and a hash or address; opens outside the Safe{Wallet} frame
export const link = (href, text) => el("a", { href, target: "_blank", rel: "noopener noreferrer" }, text);

export function fill(node, ...children) {
  node.replaceChildren(...children.flat().filter((c) => c != null));
  node.classList.remove("fade"); void node.offsetWidth; node.classList.add("fade");
}

// --------------------------------------------------------------------------- stepper

const STEPS = [
  ["rehearsing", "Simulation"], ["floor", "Policy"], ["forward", "Intent"], ["backward", "Effects"],
  ["source", "Source check"], ["verdict", "Decision"], ["stamping", "Stamp"],
];
let reached = -1;

export function resetStepper() { reached = -1; renderStepper(null); }

export function renderStepper(active, finished = false) {
  const parts = [];
  STEPS.forEach(([key, label], i) => {
    let cls = "step";
    if (i < reached || (finished && i === reached)) cls += " done";
    else if (i === reached && active) cls += " active";
    if (i > 0) parts.push(el("span", { class: "step-line" }));
    parts.push(el("span", { class: cls }, el("span", { class: "ring" }), label));
  });
  $("stepper").replaceChildren(...parts);
}

export function onStage(name) {
  if (name === "done") { renderStepper(null, true); return; }
  const i = STEPS.findIndex(([k]) => k === name);
  if (i >= 0) { reached = i; renderStepper(name); }
}

// --------------------------------------------------------------------------- the stream

let source = null;

// Attach to a job's event stream. handlers: { name: fn(payload) }, plus end().
export function listen(jobId, handlers) {
  if (source) source.close();
  source = new EventSource(`/api/jobs/${jobId}/events`);
  for (const [name, fn] of Object.entries(handlers)) {
    if (name === "end") continue;
    source.addEventListener(name, (ev) => fn(JSON.parse(ev.data)));
  }
  source.addEventListener("end", () => {
    source.close(); source = null;
    if (handlers.end) handlers.end();
  });
}

export function stopListening() { if (source) { source.close(); source = null; } }

// --------------------------------------------------------------------------- cards

export function renderFloor(hits) {
  if (!hits.length) {
    $("floor").replaceChildren(el("div", { class: "ok" }, el("span", { class: "pill success" }, "Policy passed")));
    return;
  }
  $("floor").replaceChildren(
    el("div", { class: "floor-title" }, el("span", { class: "pill danger" }, `${hits.length} policy violations`)),
    ...hits.map((h) => el("div", { class: "hit" }, tidy(h.reason))),
  );
  fill($("told"), el("div", { class: "empty" }, "—"));
  fill($("does"), el("div", { class: "empty" }, "—"));
}

export function renderForward(f) {
  const rows = f.rows.length
    ? f.rows.map((r) => el("div", { class: "row" }, el("span", { class: "kind" }, KIND[r.kind] || r.kind), el("span", { class: "text" }, tidy(r.text))))
    : [el("div", { class: "empty" }, "No effects")];
  const extra = [];
  for (const q of f.questions) extra.push(el("div", { class: "footer-note" }, q));
  fill($("told"), rows, extra);
}

export function renderBackward(b) {
  const rows = b.effects.map((e) => {
    const raw = el("pre", { class: "raw hidden" }, JSON.stringify(e.raw, null, 2));
    const toggle = el("button", { class: "raw-toggle", onclick: () => raw.classList.toggle("hidden") }, "Details");
    return el("div", {},
      el("div", { class: "row" }, dot(e.severity),
        el("span", { class: "text" }, e.severity === "critical" ? el("span", { class: "pill danger" }, "Critical") : null,
          e.severity === "critical" ? " " : null, tidy(e.sentence)),
        toggle),
      raw);
  });
  fill($("does"), rows);
}

export function renderVerdict(v) {
  const note = el("div", { class: "note clamp" }, tidy(v.headline));
  const more = el("button", { class: "link", onclick: () => { note.classList.toggle("clamp"); more.textContent = note.classList.contains("clamp") ? "Show more" : "Show less"; } }, "Show more");
  const parts = [
    el("div", { class: "verdict-head" }, el("span", { class: `pill ${PILL[v.decision]} verdict-pill` }, LABEL[v.decision])),
    note,
  ];
  parts.push(more);
  if (v.rows.length) {
    parts.push(el("div", { class: "section-label" }, "Reconciliation"));
    for (const r of v.rows) {
      parts.push(el("div", { class: "row", title: r.detail }, dot(r.state),
        el("span", { class: "text" }, tidy(r.text))));
    }
  }
  const s = v.source;
  if (s.explained.length) {
    parts.push(el("div", { class: "source" }, `${s.explained.length} state changes verified against source`));
  }
  if (s.unlabelled.length && v.decision !== "REJECT") {
    parts.push(el("div", { class: "source" }, `${s.unlabelled.length} unverified state changes`));
  }
  fill($("verdict"), parts);
  if (note.scrollHeight <= note.clientHeight) more.remove();
  $("stamp").replaceChildren();
  const ex = $("execute");
  if (ex) ex.disabled = false;
  if (v.decision === "ASK") $("answer-box").classList.remove("hidden");
}

export function renderStamp(s) {
  const attest = `${short(s.attest_tx)} · block ${s.attest_block.toLocaleString()}`;
  $("stamp").replaceChildren(
    el("dt", {}, "Stamp"), el("dd", {}, el("span", { class: "pill success" }, "Signed"), ` by ${short(s.judge)}`),
    el("dt", {}, "Fork block"), el("dd", {}, s.fork_block.toLocaleString()),
    el("dt", {}, "Attestation"), el("dd", { title: s.attest_tx }, s.attest_link ? link(s.attest_link, attest) : attest),
  );
}

// onReplay: optional; offered when the server has recorded forms to fall back on
export function showError(e, onReplay) {
  const parts = [
    el("div", { class: "verdict-head" }, el("span", { class: "pill danger verdict-pill" }, "Unavailable")),
    el("div", { class: "note" }, e.message),
  ];
  if (e.replay_available && onReplay) {
    parts.push(el("button", { class: "link", onclick: onReplay }, "Replay from log"));
  }
  fill($("verdict"), parts);
}
