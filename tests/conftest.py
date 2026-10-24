import os

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()

ANVIL_RPC = os.environ.get("ANVIL_RPC", "http://127.0.0.1:8545")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run tests that call the Gemini API (needs GEMINI_API_KEY).",
    )
    parser.addoption(
        "--fork",
        action="store_true",
        default=False,
        help="Run tests that need anvil forking mainnet at ANVIL_RPC (see NOTES.md).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: calls the real Gemini API")
    config.addinivalue_line("markers", "fork: needs anvil on the mainnet fork; run with --fork")


def _anvil_reachable() -> bool:
    try:
        r = httpx.post(ANVIL_RPC, json={"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}, timeout=2)
        return r.json().get("result") == "0x1"
    except Exception:  # noqa: BLE001 - any failure means no fork to test against
        return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    run_live = config.getoption("--live") and bool(os.environ.get("GEMINI_API_KEY"))
    run_fork = config.getoption("--fork") and _anvil_reachable()
    skip_live = pytest.mark.skip(reason="live tests need --live and GEMINI_API_KEY")
    skip_fork = pytest.mark.skip(reason=f"fork tests need --fork and anvil on the mainnet fork at {ANVIL_RPC}")
    for item in items:
        if "live" in item.keywords and not run_live:
            item.add_marker(skip_live)
        if "fork" in item.keywords and not run_fork:
            item.add_marker(skip_fork)
