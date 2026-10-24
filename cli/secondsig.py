"""Second Sig CLI.

    uv run secondsig judge fixtures/cases/demo/demo_aave.json --replay           # verdict from recorded forms
    uv run secondsig judge fixtures/cases/demo/demo_aave.json --replay --chain   # + stamp, attest, execute on anvil
    uv run secondsig answer fixtures/cases/demo/demo_auditor.json --owner 1 "Yes, the auditor invoices monthly"
    uv run secondsig demo aave|auditor|bybit [--live]                             # the three scenarios, on the chain
    uv run secondsig execute fixtures/cases/demo/demo_bybit.json                  # try the bytes against the guard

--replay uses the forms recorded in fixtures/outputs/ and makes no model call (invariant 11:
say so). Without it the passes run live. --chain talks to anvil: signs the stamp on MATCH,
attests it, then sends the real execTransaction with two owner signatures and reports what the
guard did. For ASK and REJECT the execution is attempted too, so the revert is on the record.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

# Windows consoles and pipes default to cp1252, which cannot show the view's glyphs or the
# fixtures' "…". Force UTF-8 on the streams before rich binds to them.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from judge import pipeline
from judge.schemas import Decision

app = typer.Typer(help="Second Sig: an extra signer for Safe multisigs.", no_args_is_help=True)
DEMOS = {"bybit": "demo_bybit", "aave": "demo_aave", "auditor": "demo_auditor"}


def _case(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fork():
    from contracts.setup import OWNERS, connect, ensure_guard, ensure_safe
    w3 = connect()
    safe = ensure_safe(w3, quiet=True)
    guard = ensure_guard(w3, safe)
    return w3, safe, guard, OWNERS


def _bundle(case: dict, replay: bool, w3=None):
    if replay:
        b = pipeline.recorded_bundle(case["id"])
        if b is None:
            raise typer.BadParameter(f"no recorded bundle for {case['id']}; rehearse it first or drop --replay")
        return b
    if w3 is None:
        w3, *_ = _fork()
    return pipeline.rehearse(case, w3)


def _run_chain(res: pipeline.JudgeResult) -> None:
    from cli import view
    w3, safe, guard, owners = _fork()
    if res.verdict.decision == Decision.MATCH:
        sig = pipeline.sign_stamp(res, w3, guard.address)
        view.show_chain("stamp", f"signed by the judge key: {sig[:14]}…")
        rcpt = pipeline.attest(res, w3, guard, owners[2].address)
        view.show_chain("attest", f"guard {guard.address[:10]}… recorded the stamp in block {rcpt['blockNumber']}")
    else:
        view.show_chain("stamp", "none: the verdict was not MATCH", ok=False)
    out = pipeline.execute(res, w3, safe, owners[0].address)
    if out["executed"]:
        view.show_chain("execTransaction", f"two owner signatures, block {out['block']}: "
                        f"{'ExecutionSuccess' if out['execution_success'] else 'ExecutionFailure'}")
    else:
        err = out["error"]
        what = "SecondSig__NoStamp: the guard refused" if "66d21dae" in err or "NoStamp" in err else err[:160]
        view.show_chain("execTransaction", f"two owner signatures, reverted. {what}", ok=False)


@app.command()
def judge(
    case_path: Path = typer.Argument(..., help="A case file under fixtures/cases/."),
    replay: bool = typer.Option(False, "--replay", help="Recorded forms, no model call."),
    chain: bool = typer.Option(False, "--chain", help="Stamp, attest and execute on anvil."),
) -> None:
    """Judge a proposal: rehearse, floor, forward and backward, compare, decide."""
    from cli import view
    case = _case(case_path)
    proposal = pipeline.Proposal.load_or_create(case)
    bundle = _bundle(case, replay)
    res = pipeline.judge(proposal, bundle, replay=replay)
    proposal.save()
    if replay:
        view.console.print("[dim]replay: forms from fixtures/outputs/, no model call[/]")
    view.show(res)
    if chain:
        _run_chain(res)


@app.command()
def answer(
    case_path: Path = typer.Argument(...),
    text: str = typer.Argument(..., help="The owner's answer to the question."),
    owner: int = typer.Option(..., "--owner", help="Which test owner answers: 0, 1 or 2."),
    chain: bool = typer.Option(False, "--chain"),
) -> None:
    """An owner answers an ASK. The answer amends the description; the judge runs again on the same bytes."""
    from cli import view
    from contracts.setup import OWNERS
    case = _case(case_path)
    proposal = pipeline.Proposal.load_or_create(case)
    bundle = pipeline.recorded_bundle(case["id"])
    w3 = None
    try:
        from contracts.setup import connect
        w3 = connect()
    except SystemExit:
        view.console.print("[yellow]no fork reachable: owner check skipped, using the test owner list[/]")
    res = pipeline.answer(proposal, OWNERS[owner].address, text, bundle, w3,
                          backward_form=pipeline.recorded_backward(case["id"]), replay=True)
    view.show(res)
    if chain:
        _run_chain(res)


@app.command()
def execute(case_path: Path = typer.Argument(...)) -> None:
    """Send the case's bytes through the real Safe with two owner signatures and report what the guard did."""
    from cli import view
    case = _case(case_path)
    bundle = pipeline.recorded_bundle(case["id"])
    res = pipeline.JudgeResult(proposal=pipeline.Proposal.from_case(case), bundle=bundle, forward=None, backward=None,
                               verdict=pipeline.verdicting.decide(bundle))
    w3, safe, guard, owners = _fork()
    out = pipeline.execute(res, w3, safe, owners[0].address)
    view.console.print(out)


@app.command()
def demo(
    scenario: str = typer.Argument(..., help="bybit, aave or auditor"),
    live: bool = typer.Option(False, "--live", help="Call the models instead of replaying recorded forms."),
) -> None:
    """One demo scenario, start to finish, on the fork."""
    from cli import view
    if scenario not in DEMOS:
        raise typer.BadParameter(f"scenario must be one of {', '.join(DEMOS)}")
    (path,) = (pipeline.FIXTURES / "cases").glob(f"*/{DEMOS[scenario]}.json")
    case = _case(path)
    proposal = pipeline.Proposal.from_case(case)  # a fresh run: no earlier amendments
    bundle = _bundle(case, replay=not live)
    res = pipeline.judge(proposal, bundle, replay=not live)
    view.console.print(f"[dim]{'live model calls' if live else 'replay: recorded forms, no model call'}[/]")
    view.show(res)
    _run_chain(res)


@app.command()
def reset() -> None:
    """Rewind anvil to the fork block and rebuild the Safe and the guard. Clears proposal records."""
    from contracts.setup import FORK_BLOCK, connect, ensure_guard, ensure_safe, rpc
    import os
    w3 = connect()
    url = os.environ.get("MAINNET_RPC") or "https://eth.drpc.org"
    rpc(w3, "anvil_reset", [{"forking": {"jsonRpcUrl": url, "blockNumber": FORK_BLOCK}}])
    safe = ensure_safe(w3)
    ensure_guard(w3, safe)
    for p in pipeline.PROPOSALS.glob("*.json"):
        p.unlink()


@app.command()
def eval(table: bool = typer.Option(False, "--table")) -> None:
    """The eval table lives in scripts/compare_benign.py for now."""
    typer.echo("run: uv run python scripts/compare_benign.py --include-reject")


if __name__ == "__main__":
    app()
