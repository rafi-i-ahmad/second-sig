"""Verified source and ABIs from Etherscan, cached under fixtures/sources/<address>.json.

Each cache file holds Etherscan's getsourcecode result for one address, unchanged except for
an added ``fetched_at``. The API key is read from .env and never written anywhere. A proxy
(Etherscan ``Proxy == "1"``) is followed to its ``Implementation``, which gets its own file.

Everything in a verified source, including contract, function and parameter names, is
attacker-authorable (CLAUDE.md invariant 7). Callers must spotlight it before a model sees it.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from eth_utils import to_checksum_address

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = REPO_ROOT / "fixtures" / "sources"
ETHERSCAN_URL = "https://api.etherscan.io/v2/api"
UNVERIFIED_ABI = "Contract source code not verified"


class SourceUnavailable(Exception):
    """Etherscan could not be asked (no key, network error, API error)."""


@dataclass
class Contract:
    """Verified source and ABI for one address, if Etherscan has them."""

    address: str
    verified: bool
    name: str = ""
    compiler: str = ""
    abi: list[dict[str, Any]] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    implementation: str | None = None


def _fetch(address: str, chain_id: int) -> dict[str, Any]:
    load_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("ETHERSCAN_API_KEY")
    if not key:
        raise SourceUnavailable(f"ETHERSCAN_API_KEY is not set and {address} is not cached")
    params = {"chainid": chain_id, "module": "contract", "action": "getsourcecode",
              "address": address, "apikey": key}
    for attempt in range(3):
        try:
            r = httpx.get(ETHERSCAN_URL, params=params, timeout=30)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceUnavailable(f"getsourcecode {address}: {type(exc).__name__}") from exc
        body = r.json()
        if body.get("status") == "1":
            return body["result"][0]
        if "rate limit" in str(body.get("result", "")).lower() and attempt < 2:
            time.sleep(1.0)
            continue
        raise SourceUnavailable(f"getsourcecode {address}: {body.get('message')}: {body.get('result')}")
    raise AssertionError("unreachable")


def _cache_path(address: str, chain_id: int) -> Path:
    """Mainnet at the top level, as always; any other chain in its own folder, so an address that
    exists on two chains never borrows the other chain's verification."""
    folder = CACHE_DIR if chain_id == 1 else CACHE_DIR / str(chain_id)
    return folder / f"{address.lower()}.json"


def _cached(address: str, chain_id: int) -> dict[str, Any]:
    path = _cache_path(address, chain_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    raw = _fetch(address, chain_id)
    raw["fetched_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, indent=1) + "\n", encoding="utf-8", newline="\n")
    return raw


def _source_files(raw: dict[str, Any]) -> dict[str, str]:
    """Etherscan returns a flat file, a {path: {content}} map, or standard JSON in double braces."""
    src = raw.get("SourceCode") or ""
    if not src:
        return {}
    if src.startswith("{{"):
        return {p: f["content"] for p, f in json.loads(src[1:-1])["sources"].items()}
    if src.startswith("{"):
        parsed = json.loads(src)
        files = parsed.get("sources", parsed)
        return {p: f["content"] for p, f in files.items()}
    return {f"{raw.get('ContractName') or 'Contract'}.sol": src}


def load(address: str, chain_id: int = 1) -> Contract:
    """Verified source for one address. Does not follow proxies; see ``load_with_impl``."""
    address = to_checksum_address(address)
    raw = _cached(address, chain_id)
    if raw.get("ABI") in (None, "", UNVERIFIED_ABI):
        return Contract(address=address, verified=False)
    impl = raw.get("Implementation") if raw.get("Proxy") == "1" else None
    return Contract(
        address=address,
        verified=True,
        name=raw.get("ContractName", ""),
        compiler=raw.get("CompilerVersion", ""),
        abi=json.loads(raw["ABI"]),
        files=_source_files(raw),
        implementation=to_checksum_address(impl) if impl else None,
    )


def load_with_impl(addresses: list[str], chain_id: int = 1) -> dict[str, Contract]:
    """Source for every address, plus the implementation behind any verified proxy."""
    out: dict[str, Contract] = {}
    queue = [to_checksum_address(a) for a in addresses]
    while queue:
        addr = queue.pop(0)
        if addr in out:
            continue
        out[addr] = load(addr, chain_id)
        if out[addr].implementation and out[addr].implementation not in out:
            queue.append(out[addr].implementation)
    return out
