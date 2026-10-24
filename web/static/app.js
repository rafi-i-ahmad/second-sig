// Second Sig demo page. Renders what the server sends; computes nothing.
// Every string from the server may carry attacker-authored text, so it goes in via textContent only.

const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, ...children) {
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

const short = (a) => (a && a.length > 12 ? `${a.slice(0, 6)}…${a.slice(-4)}` : a || "");
const tidy = (t) => String(t).replace(/0x[0-9a-fA-F]{40}\b/g, (a) => short(a)).replaceAll(" -> ", " → ");
const dot = (cls) => el("span", { class: `dot ${cls}` });
const skeleton = () => [el("div", { class: "skeleton" }), el("div", { class: "skeleton" }), el("div", { class: "skeleton" })];
const PILL = { MATCH: "success", ASK: "warning", REJECT: "danger" };
const KIND = { move: "Transfer", allow: "Approval", config: "Config" };
const LABEL = { MATCH: "Match", ASK: "Needs answer", REJECT: "Rejected" };
function fill(node, ...children) {
  node.replaceChildren(...children.flat().filter((c) => c != null));
  node.classList.remove("fade"); void node.offsetWidth; node.classList.add("fade");
}

let scenarios = [];
let current = null;
let state = null;
let source = null;
let busy = false;

// --------------------------------------------------------------------------- summary

async function loadState() {
  try {
    const r = await fetch("/api/state");
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    state = await r.json();
    $("bal-eth").textContent = state.balances.ETH.replace(" ETH", "");
    $("bal-usdc").textContent = state.balances.USDC.replace(" USDC", "");
    $("bal-ausdc").textContent = state.balances.aEthUSDC.replace(" aEthUSDC", "");
    const a = $("safe-addr");
    a.textContent = short(state.safe);
    a.title = `${state.safe}\nGuard ${state.guard}\nJudge ${state.judge}\nNonce ${state.nonce} · fork block ${state.fork_block.toLocaleString()}`;
    $("guard-pill").className = "pill success";
    $("guard-pill").textContent = "Guard active";
  } catch (e) {
    $("guard-pill").className = "pill danger";
    $("guard-pill").textContent = "Fork offline";
    $("safe-addr").textContent = e.message;
  }
}

function renderSigners() {
  if (!state) return;
  $("signers").replaceChildren(
    ...state.owners.map((o, i) => el("span", { class: `sig ${i < state.threshold ? "on" : "off"}`, title: o }, String(i))),
    el("span", { class: "muted" }, ` ${state.threshold} of ${state.owners.length}`));
  $("answer-owner").replaceChildren(...state.owners.map((o, i) => el("option", { value: i }, `Owner ${i}`)));
}

// --------------------------------------------------------------------------- scenario

async function loadScenarios() {
  scenarios = await (await fetch("/api/scenarios")).json();
  $("tabs").replaceChildren(...scenarios.map((s) =>
    el("button", { class: "seg", "data-id": s.id, onclick: () => selectScenario(s.id, true) }, s.title)));
  selectScenario(scenarios[0].id, false);
}

async function selectScenario(id, reset) {
  if (busy) return;
  current = scenarios.find((s) => s.id === id);
  document.querySelectorAll(".seg").forEach((t) => t.classList.toggle("active", t.dataset.id === id));
  $("description").textContent = current.description;
  $("bytes-summary").textContent = current.calls.length
    ? current.calls.map((c) => `${(c.function || "call").split("(")[0]} → ${c.to}`).join(", ")
    : `${current.operation === 1 ? "delegatecall" : "call"} → ${short(current.to)}`;
  clearCards();
  if (reset) await doReset();
}

function clearCards() {
  fill($("told"), el("div", { class: "empty" }, "—"));
  fill($("does"), el("div", { class: "empty" }, "—"));
  fill($("verdict"), el("div", { class: "empty" }, "—"));
  $("floor").replaceChildren();
  $("stamp").replaceChildren();
  $("result").replaceChildren(); $("result").className = "result";
  $("answer-box").classList.add("hidden");
  $("execute").disabled = true;
  $("judge").disabled = false;
  renderStepper(null);
}

// --------------------------------------------------------------------------- stepper

const STEPS = [
  ["rehearsing", "Simulation"], ["floor", "Policy"], ["forward", "Intent"], ["backward", "Effects"],
  ["source", "Source check"], ["verdict", "Decision"], ["stamping", "Stamp"],
];
let reached = -1;
let mode = null;

function renderStepper(active, finished = false) {
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

function onStage(name) {
  if (name === "done") { renderStepper(null, true); return; }
  const i = STEPS.findIndex(([k]) => k === name);
  if (i >= 0) { reached = i; renderStepper(name); }
}

// --------------------------------------------------------------------------- the stream

function startJob(url, body) {
  if (busy) return;
  busy = true;
  reached = -1; mode = null;
  const live = $("live").checked;
  $("judge").disabled = true;
  $("execute").disabled = true;
  $("result").replaceChildren(); $("result").className = "result";
  $("stamp").replaceChildren();
  $("answer-box").classList.add("hidden");
  if (!body) { fill($("told"), skeleton()); fill($("does"), skeleton()); $("floor").replaceChildren(); }
  fill($("verdict"), skeleton());
  fetch(`${url}?live=${live}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
    .then(async (r) => {
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
      return r.json();
    })
    .then(({ job_id }) => listen(job_id))
    .catch((e) => { busy = false; $("judge").disabled = false; showError({ message: e.message }); });
}

function listen(jobId) {
  if (source) source.close();
  source = new EventSource(`/api/jobs/${jobId}/events`);
  const on = (name, fn) => source.addEventListener(name, (ev) => fn(JSON.parse(ev.data)));
  on("mode", (m) => { mode = m; renderStepper(null); });
  on("stage", (s) => onStage(s.name));
  on("floor", renderFloor);
  on("forward", renderForward);
  on("backward", renderBackward);
  on("amendments", renderAmendments);
  on("verdict", renderVerdict);
  on("stamp", renderStamp);
  on("error", showError);
  on("end", () => {
    source.close(); source = null; busy = false;
    $("judge").disabled = false;
    loadState();
  });
}

// --------------------------------------------------------------------------- cards

function renderFloor(hits) {
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

function renderForward(f) {
  const rows = f.rows.length
    ? f.rows.map((r) => el("div", { class: "row" }, el("span", { class: "kind" }, KIND[r.kind] || r.kind), el("span", { class: "text" }, tidy(r.text))))
    : [el("div", { class: "empty" }, "No effects")];
  const extra = [];
  for (const q of f.questions) extra.push(el("div", { class: "footer-note" }, q));
  fill($("told"), rows, extra);
}

function renderBackward(b) {
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

function renderAmendments(list) {
  $("description").replaceChildren(current.description,
    ...list.map((a) => el("div", { class: "amend" }, `Owner ${short(a.owner)}: ${a.text}`)));
}

function renderVerdict(v) {
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
  $("execute").disabled = false;
  if (v.decision === "ASK") $("answer-box").classList.remove("hidden");
}

function renderStamp(s) {
  $("stamp").replaceChildren(
    el("dt", {}, "Stamp"), el("dd", {}, el("span", { class: "pill success" }, "Signed"), ` by ${short(s.judge)}`),
    el("dt", {}, "Fork block"), el("dd", {}, s.fork_block.toLocaleString()),
    el("dt", {}, "Attestation"), el("dd", { title: s.attest_tx }, `${short(s.attest_tx)} · block ${s.attest_block.toLocaleString()}`),
  );
}

function showError(e) {
  const parts = [
    el("div", { class: "verdict-head" }, el("span", { class: "pill danger verdict-pill" }, "Unavailable")),
    el("div", { class: "note" }, e.message),
  ];
  if (e.replay_available) {
    parts.push(el("button", { class: "link", onclick: () => { $("live").checked = false; judge(); } }, "Replay from log"));
  }
  fill($("verdict"), parts);
}

// --------------------------------------------------------------------------- actions

function judge() { startJob(`/api/judge/${current.id}`); }

async function execute() {
  $("execute").disabled = true;
  $("result").className = "result pending";
  $("result").textContent = "Submitting…";
  try {
    const r = await fetch(`/api/execute/${current.id}`, { method: "POST" });
    const out = await r.json();
    if (!r.ok) throw new Error(out.detail || r.statusText);
    if (out.executed) {
      $("result").className = out.execution_success ? "result ok" : "result bad";
      $("result").replaceChildren(
        el("strong", {}, out.execution_success ? "Executed" : "Failed"),
        el("span", { class: "sub" }, `${short(out.tx)} · block ${out.block.toLocaleString()}`));
    } else {
      $("result").className = "result bad";
      $("result").replaceChildren(
        el("strong", {}, "Blocked by guard"),
        el("span", { class: "sub mono", title: out.error.why }, out.error.name));
    }
    loadState();
  } catch (e) {
    $("result").className = "result bad";
    $("result").textContent = `Execute failed: ${e.message}`;
    $("execute").disabled = false;
  }
}

async function doReset() {
  $("reset").disabled = true;
  try {
    const r = await fetch("/api/reset", { method: "POST" });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
  } catch (e) {
    $("guard-pill").className = "pill danger";
    $("guard-pill").textContent = `Reset failed`;
    $("guard-pill").title = e.message;
  } finally {
    $("reset").disabled = false;
  }
  clearCards();
  $("description").textContent = current.description;
  await loadState();
}

function sendAnswer() {
  const text = $("answer-text").value.trim();
  if (!text) return;
  startJob(`/api/answer/${current.id}`, { owner: Number($("answer-owner").value), text });
  $("answer-text").value = "";
}

$("judge").onclick = judge;
$("live").onchange = () => { $("mode-label").textContent = $("live").checked ? "Live" : "Replay"; };
$("execute").onclick = execute;
$("reset").onclick = () => { if (!busy) doReset(); };
$("answer-send").onclick = sendAnswer;
$("answer-text").addEventListener("keydown", (e) => { if (e.key === "Enter") sendAnswer(); });

(async () => {
  await loadState();
  renderSigners();
  await loadScenarios();
})();
