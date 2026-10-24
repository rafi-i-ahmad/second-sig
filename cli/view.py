"""Three-panel terminal view (rich): the words, the bytes, the verdict."""

from __future__ import annotations

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from judge.canon import Resolver, from_backward, from_forward, render_config, render_movement, render_permission
from judge.pipeline import JudgeResult
from judge.schemas import Decision

console = Console()
COLOUR = {Decision.MATCH: "green", Decision.ASK: "yellow", Decision.REJECT: "red"}


def _lists(c) -> Table:
    t = Table.grid(padding=(0, 1))
    for m in c.movements:
        t.add_row("move", render_movement(m))
    for p in c.permissions:
        t.add_row("allow", render_permission(p))
    for x in c.configs:
        t.add_row("config", render_config(x))
    if not (c.movements or c.permissions or c.configs):
        t.add_row("", "(nothing)")
    return t


def show(res: JudgeResult) -> None:
    b, p, v = res.bundle, res.proposal, res.verdict
    r = Resolver(b, p.address_book)

    words = Text(p.description, style="bold")
    for a in p.amendments:
        words.append(f"\n+ Owner {a.owner[:6]}…{a.owner[-4:]}: {a.text}", style="cyan")
    forward_lists = _lists(from_forward(res.forward, b.description, r)) if res.forward else Text("(no forward form)")
    console.print(Panel(Group(words, Text(""), forward_lists), title="The words (forward pass)", border_style="blue"))

    if res.backward:
        obs = from_backward(res.backward, r)
        effects = Table.grid(padding=(0, 1))
        for e in obs.effects:
            effects.add_row(f"[{ {'info': 'dim', 'notable': 'yellow', 'critical': 'red'}[e.severity] }]{e.severity}[/]",
                            e.sentence, f"[dim]{', '.join(e.cites)}[/]")
        body = Group(_lists(obs), Text(""), effects)
    else:
        body = Text("(no backward form)")
    floor = ""
    if v.floor_hits:
        floor = "\n".join(f"[red]FLOOR {h.rule}[/]: {h.reason}" for h in v.floor_hits)
    console.print(Panel(Group(body, Text(""), Text.from_markup(floor)) if floor else body,
                        title=f"The bytes (backward pass) · safeTxHash {b.safe_tx_hash[:10]}… · block {b.fork_block}",
                        border_style="magenta"))

    colour = COLOUR[v.decision]
    lines = [Text(v.decision.value, style=f"bold {colour}")]
    if v.compare:
        t = Table.grid(padding=(0, 1))
        for m in v.compare.matched:
            t.add_row("[green]✓[/]", m.observed, f"[dim]{m.tier}[/]")
        for u in v.compare.observed_unexplained:
            t.add_row("[red]?[/]", u.item, f"[dim]{u.severity}; {', '.join(u.cites)}[/]")
        for x in v.compare.expected_unobserved:
            t.add_row("[yellow]∅[/]", x, "[dim]promised, not seen[/]")
        lines.append(t)
    lines.append(Text(""))
    lines.append(Text(res.note))
    if res.stamp:
        lines.append(Text(""))
        lines.append(Text(f"stamp: forkBlock {res.stamp.forkBlock}, judgeVersion {res.stamp.judgeVersion[:10]}…"
                          + (f", signed {res.stamp_signature[:12]}…" if res.stamp_signature else ", unsigned"),
                          style="green"))
    if res.calls:
        lines.append(Text("model calls: " + "; ".join(res.calls), style="dim"))
    console.print(Panel(Group(*lines), title="The verdict (code)", border_style=colour))


def show_chain(step: str, detail: str, ok: bool = True) -> None:
    console.print(f"[{'green' if ok else 'red'}]{'●' if ok else '○'}[/] [bold]{step}[/]  {detail}")
