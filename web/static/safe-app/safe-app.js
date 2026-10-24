// Second Sig as a Safe App: the Sepolia Safe's queue, as Safe{Wallet} shows it, with the judge's
// verdict on each proposal. Renders what the server sends; computes nothing; holds no key.
// Notes, names and decoded methods are attacker-authorable, so text goes in via textContent only.

import {
  $, el, short, tidy, skeleton, fill, link, PILL, LABEL, resetStepper, renderStepper, onStage, listen,
  stopListening, renderFloor, renderForward, renderBackward, renderVerdict, renderStamp, showError,
} from "/static/render.js";

const STATUS = {
  judging: ["neutral", "Checking…"],
  waiting: ["neutral", "Waiting"],
  refused: ["danger", "Refused"],
  needs_description: ["warning", "No description"],
  error: ["danger", "Unavailable"],
};

let state = null;
let rows = [];
let selected = null;   // safeTxHash
let streaming = null;  // job id being streamed into the cards
let busy = false;

const live = () => $("live").checked;

// --------------------------------------------------------------------------- summary

async function loadState() {
  try {
    const r = await fetch("/sepolia/api/state");
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    state = await r.json();
    $("bal-eth").textContent = state.balances.ETH.replace(" ETH", "");
    $("bal-usdc").textContent = state.balances.USDC.replace(" USDC", "");
    $("safe-label").textContent = `Safe v${state.safe_version} · ${state.threshold} of ${state.owners.length}`;
    const a = $("safe-addr");
    a.replaceChildren(link(state.links.safe_etherscan, short(state.safe)));
    a.title = `${state.safe}\nGuard ${state.guard || "none"}\nJudge ${state.judge}\nNonce ${state.nonce}`;
    $("open-wallet").href = state.links.safe_wallet;
    $("head").textContent = `block ${state.head_block.toLocaleString()}`;
    const g = $("guard-pill");
    if (!state.fork_ok) { g.className = "pill danger"; g.textContent = "Fork offline"; }
    else if (state.guard) { g.className = "pill success"; g.textContent = "Guard active"; }
    else { g.className = "pill warning"; g.textContent = "No guard set"; }
    $("answer-owner").replaceChildren(...state.owners.map((o, i) => el("option", { value: o }, `Owner ${i + 1} ${short(o)}`)));
    $("hint-book").replaceChildren(`Address book: ${state.address_book.join(", ") || "empty"}`,
      state.address_book_ignored.length
        ? el("div", {}, el("span", { class: "pill warning" }, "Label ignored"),
          ` not a plain name, shown raw: ${state.address_book_ignored.map(short).join(", ")}`)
        : null);
  } catch (e) {
    $("guard-pill").className = "pill danger";
    $("guard-pill").textContent = "Offline";
    $("safe-addr").textContent = e.message;
  }
}

// --------------------------------------------------------------------------- queue

function statusPill(row) {
  const e = row.entry;
  if (row.job_id || (e && e.status === "judging")) return el("span", { class: "pill neutral" }, "Checking…");
  if (!e) return el("span", { class: "pill neutral" }, row.current ? "Not checked" : "Queued");
  if (e.status === "judged") return el("span", { class: `pill ${PILL[e.decision]}` }, LABEL[e.decision]);
  const [cls, text] = STATUS[e.status] || ["neutral", e.status];
  return el("span", { class: `pill ${cls}` }, text);
}

function stampCell(row) {
  const e = row.entry;
  if (!e || !e.attest_tx) return el("span", { class: "muted" }, e && e.decision === "MATCH" ? "not attested" : "no stamp");
  if (e.blocks_left !== null && e.blocks_left <= 0) return el("span", { class: "pill warning" }, "Stamp expired");
  return el("span", { class: "pill success", title: `valid for ${e.blocks_left} more blocks` }, `Stamped · ${e.blocks_left} blocks`);
}

async function loadQueue() {
  let q;
  try {
    const r = await fetch("/sepolia/api/queue");
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    q = await r.json();
  } catch (e) {
    $("queue").replaceChildren(el("div", { class: "empty" }, `Queue unavailable: ${e.message}`));
    return;
  }
  rows = q.rows;
  $("queue-title").textContent = `Queue · nonce ${q.nonce}`;
  $("queue-meta").textContent = `${rows.length} pending in Safe{Wallet}`;
  if (!rows.length) {
    $("queue").replaceChildren(el("div", { class: "empty" }, "Nothing queued. Propose a transaction in Safe{Wallet} and write its description in the note."));
  } else {
    $("queue").replaceChildren(...rows.map((row) => el("button", {
      class: `qrow${row.safe_tx_hash === selected ? " active" : ""}${row.current ? "" : " later"}`,
      onclick: () => select(row.safe_tx_hash),
    },
      el("span", { class: "qnonce mono" }, `#${row.nonce}`),
      el("span", { class: "qmain" },
        el("span", { class: "qnote" }, row.note ? tidy(row.note) : "(no note)"),
        el("span", { class: "qsum mono" }, tidy(row.summary))),
      el("span", { class: "qconf" }, `${row.confirmations}/${row.required ?? "?"} signed`),
      el("span", { class: "qstatus" }, statusPill(row)),
      el("span", { class: "qstamp" }, stampCell(row)),
    )));
  }
  if (!selected && rows.length) select(rows[0].safe_tx_hash);
  else if (selected) refreshSelected();
}

// --------------------------------------------------------------------------- the selected proposal

function selectedRow() { return rows.find((r) => r.safe_tx_hash === selected); }

function showProposal(row) {
  $("proposal").classList.remove("hidden");
  $("stepper").classList.remove("hidden");
  $("cards").classList.remove("hidden");
  $("proposal-eyebrow").textContent = `Proposal · nonce ${row.nonce} · ${short(row.safe_tx_hash)}`;
  $("description").textContent = row.note || "(no note: the proposer wrote no description)";
  $("bytes-summary").textContent = tidy(row.summary);
  $("confirmations").textContent = `${row.confirmations} of ${row.required ?? "?"}`;
  $("tx-link").replaceChildren(link(row.links.tx_safe_wallet, "Open transaction ↗"));
  $("judge").disabled = busy || !row.current;
  $("judge").textContent = row.entry ? "Re-check" : "Check";
}

function clearCards() {
  for (const id of ["told", "does", "verdict"]) fill($(id), el("div", { class: "empty" }, "—"));
  $("floor").replaceChildren();
  $("stamp").replaceChildren();
  $("result").replaceChildren(); $("result").className = "result";
  $("answer-box").classList.add("hidden");
  $("mode-tag").textContent = "";
  resetStepper();
}

async function select(h) {
  if (h !== selected) { stopListening(); streaming = null; busy = false; }
  selected = h;
  document.querySelectorAll(".qrow").forEach((b, i) => b.classList.toggle("active", rows[i] && rows[i].safe_tx_hash === h));
  const row = selectedRow();
  if (!row) return;
  showProposal(row);
  clearCards();
  if (row.job_id) { attach(row.job_id); return; }
  if (row.has_result) { await showResult(h); return; }
  showStatus(row);
}

function refreshSelected() {
  const row = selectedRow();
  if (!row) { selected = null; return; }
  showProposal(row);
  if (row.job_id && row.job_id !== streaming) { clearCards(); attach(row.job_id); }
  else if (!row.job_id && !streaming && row.entry) updateStampLine(row.entry);
}

function showStatus(row) {
  const e = row.entry;
  if (!e) {
    fill($("verdict"), el("div", { class: "empty" }, row.current
      ? "Not checked yet. It is checked automatically within a few seconds, or press Check."
      : "Queued behind an earlier nonce: it can only be checked once that one executes."));
    return;
  }
  const [cls, text] = e.status === "judged" ? [PILL[e.decision], LABEL[e.decision]] : STATUS[e.status] || ["neutral", e.status];
  fill($("verdict"),
    el("div", { class: "verdict-head" }, el("span", { class: `pill ${cls} verdict-pill` }, text)),
    el("div", { class: "note" }, tidy(e.headline || e.detail || "")),
    e.status === "judged" ? el("div", { class: "footer-note" }, "Judged before the server restarted; re-check to see the full comparison.") : null);
  if (e.status === "needs_description" || e.decision === "ASK") $("answer-box").classList.remove("hidden");
  updateStampLine(e);
}

async function showResult(h) {
  const r = await fetch(`/sepolia/api/result/${h}`);
  if (!r.ok) return;
  const out = await r.json();
  if (!out.verdict) { showStatus(selectedRow()); return; }
  renderFloor(out.floor);
  if (out.forward) renderForward(out.forward);
  if (out.backward) renderBackward(out.backward);
  renderVerdict(out.verdict);
  renderAmendments(out.amendments || []);
  onStage("done");
  if (out.entry) {
    $("mode-tag").textContent = out.entry.live ? "Live" : "Replay";
    updateStampLine(out.entry);
  }
}

function updateStampLine(e) {
  if (e.attest_tx && state) {
    renderStamp({ judge: state.judge, fork_block: e.fork_block, attest_tx: e.attest_tx, attest_block: e.attest_block, attest_link: e.attest_link });
    const left = e.blocks_left;
    $("result").className = left > 0 ? "result ok" : "result bad";
    $("result").replaceChildren(
      el("strong", {}, left > 0 ? "Stamp on Sepolia: execute in Safe{Wallet}" : "Stamp expired: re-check to stamp again"),
      el("span", { class: "sub" }, left > 0 ? `The guard accepts it for ${left} more blocks (about ${Math.ceil(left * 12 / 60)} min).` : "Stamps last 100 blocks."));
  } else if (e.decision && e.decision !== "MATCH") {
    $("result").className = "result bad";
    $("result").replaceChildren(
      el("strong", {}, "No stamp"),
      el("span", { class: "sub" }, "Safe{Wallet} will warn that execution fails; the guard reverts it with SecondSig__NoStamp."));
  } else if (e.decision === "MATCH" && e.detail) {
    $("result").className = "result bad";
    $("result").replaceChildren(el("strong", {}, "Not stamped"), el("span", { class: "sub" }, e.detail));
  }
}

function renderAmendments(list) {
  const row = selectedRow();
  if (!row || !list.length) return;
  $("description").replaceChildren(row.note || "(no note)",
    ...list.map((a) => el("div", { class: "amend" }, `Owner ${short(a.owner)}: ${a.text}`)));
}

// --------------------------------------------------------------------------- streaming a run

function attach(jobId) {
  streaming = jobId;
  busy = true;
  $("judge").disabled = true;
  fill($("told"), skeleton()); fill($("does"), skeleton()); fill($("verdict"), skeleton());
  listen(jobId, {
    mode: (m) => { $("mode-tag").textContent = m.live ? "Live" : "Replay"; renderStepper(null); },
    stage: (s) => onStage(s.name),
    floor: renderFloor,
    forward: renderForward,
    backward: renderBackward,
    amendments: renderAmendments,
    verdict: renderVerdict,
    stamp: (s) => { renderStamp(s); },
    notice: (n) => {
      const [cls, text] = STATUS[n.status] || ["neutral", n.status];
      fill($("verdict"), el("div", { class: "verdict-head" }, el("span", { class: `pill ${cls} verdict-pill` }, text)),
        el("div", { class: "note" }, tidy(n.message)));
      if (n.status === "needs_description") $("answer-box").classList.remove("hidden");
    },
    error: (e) => showError(e),
    end: async () => {
      streaming = null; busy = false;
      await loadQueue();
      const row = selectedRow();
      if (row && row.entry) updateStampLine(row.entry);
    },
  });
}

async function post(url, body) {
  if (busy || !selected) return;
  busy = true;
  clearCards();
  try {
    const r = await fetch(`${url}?live=${live()}`, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const out = await r.json();
    if (!r.ok) throw new Error(out.detail || r.statusText);
    attach(out.job_id);
  } catch (e) {
    busy = false;
    showError({ message: e.message });
  }
}

function sendAnswer() {
  const text = $("answer-text").value.trim();
  if (!text) return;
  post(`/sepolia/api/answer/${selected}`, { owner: $("answer-owner").value, text });
  $("answer-text").value = "";
}

$("judge").onclick = () => post(`/sepolia/api/judge/${selected}`);
$("live").onchange = () => { $("mode-label").textContent = live() ? "Live" : "Replay"; };
$("answer-send").onclick = sendAnswer;
$("answer-text").addEventListener("keydown", (e) => { if (e.key === "Enter") sendAnswer(); });

(async () => {
  await loadState();
  await loadQueue();
  setInterval(loadQueue, 6000);
  setInterval(loadState, 20000);
})();
