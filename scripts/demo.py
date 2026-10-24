"""Start the whole demo: the mainnet fork, the Sepolia fork, the Safe and guard, and the web page.

    uv run python scripts/demo.py [--reset] [--no-sepolia] [--port 8000]

1. anvil forking mainnet at FORK_BLOCK on 8545 (MAINNET_RPC from .env, else dRPC's public endpoint);
2. anvil forking the Sepolia head on 8546, if SEPOLIA_RPC is set (the Safe{Wallet} panel needs it);
3. ``forge build`` and ``contracts/setup.py --guard``: the test Safe and SecondSigGuard, idempotent;
4. the web server in the foreground, http://localhost:8000 and the Safe App at /safe-app.

An anvil already answering on a port with the right chain id is reused and left running on exit;
the ones this script started are stopped on Ctrl-C. ``--reset`` rewinds a reused mainnet fork to
the fork block first (as ``secondsig reset`` does), for when a Bybit run or an executed MATCH has
moved it on. Anvil's output goes to logs/anvil-*.log with the RPC URLs redacted, since they carry
the provider's API key.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
FORK_BLOCK = 21895238  # contracts/setup.py FORK_BLOCK; not imported, so ANVIL_RPC can be set first
MAINNET_FALLBACK = "https://eth.drpc.org"
SEPOLIA_CHAIN = 11155111
URL = re.compile(r"(?:https?|wss?)://\S+")


def tool(name: str) -> str:
    """anvil and forge live in ~/.foundry/bin, which is not always on PATH."""
    found = shutil.which(name) or shutil.which(name, path=str(Path.home() / ".foundry" / "bin"))
    if not found:
        raise SystemExit(f"{name} not found on PATH or in ~/.foundry/bin; install Foundry (foundryup)")
    return found


def chain_id(port: int) -> int | None:
    try:
        r = httpx.post(f"http://127.0.0.1:{port}",
                       json={"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}, timeout=2)
        return int(r.json()["result"], 16)
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def tail(path: Path, n: int = 20) -> str:
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])


class Anvil:
    """One anvil fork. Started only if nothing on the port answers with the expected chain id.

    ``fork`` is a public URL or an [rpc_endpoints] alias from contracts/foundry.toml, which anvil
    resolves from ``env`` when run in contracts/: a keyed URL then never appears in ``ps``.
    """

    def __init__(self, name: str, port: int, chain: int, fork: str, extra: list[str],
                 env: dict[str, str], secrets: list[str]) -> None:
        self.name, self.port, self.chain = name, port, chain
        self.fork, self.extra, self.env = fork, extra, env
        self.secrets = [s for s in secrets if s]
        self.log = LOGS / f"anvil-{name}.log"
        self.proc: subprocess.Popen[str] | None = None

    @property
    def rpc(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        running = chain_id(self.port)
        if running == self.chain:
            print(f"[{self.name}] reusing the anvil already on {self.rpc}")
            return
        if running is not None:
            raise SystemExit(f"[{self.name}] port {self.port} answers with chain {running}, expected {self.chain}")
        cmd = [tool("anvil"), "--fork-url", self.fork, "--steps-tracing", "--port", str(self.port), *self.extra]
        self.proc = subprocess.Popen(cmd, cwd=ROOT / "contracts", env=self.env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        threading.Thread(target=self._copy_log, daemon=True).start()
        print(f"[{self.name}] starting anvil on {self.rpc} (log: {self.log.relative_to(ROOT)})", end="", flush=True)
        deadline = time.monotonic() + 120
        while chain_id(self.port) != self.chain:
            if self.proc.poll() is not None:
                print()
                raise SystemExit(f"[{self.name}] anvil exited with {self.proc.returncode}:\n{tail(self.log)}")
            if time.monotonic() > deadline:
                print()
                raise SystemExit(f"[{self.name}] anvil not ready after 120 s:\n{tail(self.log)}")
            print(".", end="", flush=True)
            time.sleep(1)
        print(" ready")

    def _copy_log(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        with self.log.open("w", encoding="utf-8") as out:
            for line in self.proc.stdout:
                for s in self.secrets:
                    line = line.replace(s, "<rpc url>")
                out.write(URL.sub("<rpc url>", line))
                out.flush()

    def stop(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        print(f"[{self.name}] stopped")


def run(cmd: list[str], what: str, env: dict[str, str], cwd: Path = ROOT, quiet: bool = False) -> None:
    print(f"[setup] {what}")
    out = subprocess.run(cmd, cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace",
                         capture_output=quiet)
    if out.returncode != 0:
        if quiet:
            print(out.stdout + out.stderr)
        raise SystemExit(f"[setup] {what} failed ({out.returncode})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8000, help="web server port")
    ap.add_argument("--mainnet-port", type=int, default=8545)
    ap.add_argument("--sepolia-port", type=int, default=8546)
    ap.add_argument("--no-sepolia", action="store_true", help="skip the Sepolia fork (no Safe{Wallet} panel)")
    ap.add_argument("--reset", action="store_true", help="rewind a reused mainnet fork to the fork block first")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # keep our lines in order with the children's

    dotenv = dotenv_values(ROOT / ".env")
    secret = lambda k: os.environ.get(k) or dotenv.get(k) or ""  # noqa: E731
    LOGS.mkdir(exist_ok=True)
    # anvil alone gets .env in its environment, to resolve the foundry.toml aliases
    anvil_env = {**{k: v for k, v in dotenv.items() if v is not None}, **os.environ}
    rpcs = [secret("MAINNET_RPC"), secret("SEPOLIA_RPC")]

    # The children read these instead of their defaults; os.environ wins over .env in load_dotenv.
    env = dict(os.environ)
    env["ANVIL_RPC"] = f"http://127.0.0.1:{args.mainnet_port}"
    env["SEPOLIA_FORK_RPC"] = f"http://127.0.0.1:{args.sepolia_port}"
    env["PYTHONUNBUFFERED"] = "1"

    if not secret("MAINNET_RPC"):
        print(f"[mainnet] MAINNET_RPC not set; forking through {MAINNET_FALLBACK} (may rate-limit)")
    if not secret("JUDGE_PRIVATE_KEY"):
        print("[setup] JUDGE_PRIVATE_KEY not set in .env: a MATCH cannot be stamped (NOTES.md, 'Judge key')")

    forks = [Anvil("mainnet", args.mainnet_port, 1, "mainnet" if secret("MAINNET_RPC") else MAINNET_FALLBACK,
                   ["--fork-block-number", str(FORK_BLOCK)], anvil_env, rpcs)]
    if args.no_sepolia:
        pass
    elif secret("SEPOLIA_RPC"):
        forks.append(Anvil("sepolia", args.sepolia_port, SEPOLIA_CHAIN, "sepolia", [], anvil_env, rpcs))
    else:
        print("[sepolia] SEPOLIA_RPC not set; skipping the Sepolia fork (the Safe{Wallet} panel will say so)")

    web: subprocess.Popen[bytes] | None = None
    try:
        for fork in forks:
            fork.start()
        mainnet = forks[0]
        if args.reset and mainnet.proc is None:
            run([sys.executable, "-m", "cli.secondsig", "reset"], "rewinding the mainnet fork (secondsig reset)", env)
        run([tool("forge"), "build"], "forge build", env, cwd=ROOT / "contracts", quiet=True)
        run([sys.executable, "contracts/setup.py", "--guard"], "test Safe and guard (contracts/setup.py --guard)", env)

        print(f"\n  demo page   http://localhost:{args.port}")
        if len(forks) > 1:
            print(f"  Safe App    http://localhost:{args.port}/safe-app  (Safe{{Wallet}} -> Apps -> Add custom app)")
        print("  Ctrl-C stops the server and the anvils this script started\n")
        web = subprocess.Popen([sys.executable, "-m", "uvicorn", "web.server:app", "--port", str(args.port)],
                               cwd=ROOT, env=env)
        return web.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if web is not None and web.poll() is None:
            web.terminate()
            try:
                web.wait(timeout=10)
            except subprocess.TimeoutExpired:
                web.kill()
        for fork in reversed(forks):
            fork.stop()


if __name__ == "__main__":
    sys.exit(main())
