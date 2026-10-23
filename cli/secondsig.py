"""Second Sig CLI: propose, judge, sign, execute, override, describe, demo, eval."""

import typer

app = typer.Typer(help="Second Sig: an extra signer for Safe multisigs.", no_args_is_help=True)


@app.command()
def propose() -> None:
    raise NotImplementedError


@app.command()
def judge(safe_tx_hash: str) -> None:
    raise NotImplementedError


@app.command()
def sign(safe_tx_hash: str) -> None:
    raise NotImplementedError


@app.command()
def execute(safe_tx_hash: str) -> None:
    raise NotImplementedError


@app.command()
def override(safe_tx_hash: str) -> None:
    raise NotImplementedError


@app.command()
def describe(safe_tx_hash: str) -> None:
    raise NotImplementedError


@app.command()
def demo(
    scenario: str,
    replay: bool = typer.Option(False, "--replay", help="Rebuild verdicts from logs/, no model call."),
) -> None:
    raise NotImplementedError


@app.command()
def eval(table: bool = typer.Option(False, "--table")) -> None:
    raise NotImplementedError


if __name__ == "__main__":
    app()
