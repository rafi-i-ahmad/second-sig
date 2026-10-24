// Second Sig demo page (mainnet fork). Renders what the server sends; computes nothing.
// Every string from the server may carry attacker-authored text, so it goes in via textContent only.

import {
  $, el, short, skeleton, fill, resetStepper, renderStepper, onStage, listen,
  renderFloor, renderForward, renderBackward, renderVerdict, renderStamp, showError,
} from "./render.js";

let scenarios = [];
let current = null;
let state = null;
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

// --------------------------------------------------------------------------- the stream

function startJob(url, body) {
  if (busy) return;
  busy = true;
  resetStepper();
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
    .then(({ job_id }) => listen(job_id, {
      mode: () => renderStepper(null),
      stage: (s) => onStage(s.name),
      floor: renderFloor,
      forward: renderForward,
      backward: renderBackward,
      amendments: renderAmendments,
      verdict: renderVerdict,
      stamp: renderStamp,
      error: (e) => showError(e, replay),
      end: () => { busy = false; $("judge").disabled = false; loadState(); },
    }))
    .catch((e) => { busy = false; $("judge").disabled = false; showError({ message: e.message }); });
}

// --------------------------------------------------------------------------- cards

function renderAmendments(list) {
  $("description").replaceChildren(current.description,
    ...list.map((a) => el("div", { class: "amend" }, `Owner ${short(a.owner)}: ${a.text}`)));
}

// --------------------------------------------------------------------------- actions

function judge() { startJob(`/api/judge/${current.id}`); }
function replay() { $("live").checked = false; judge(); }

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
