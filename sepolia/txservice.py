"""Safe's Transaction Service on Sepolia: the queue Safe{Wallet} shows, read and written over HTTP.

The description of a proposal is Safe{Wallet}'s own note field. Safe{Wallet} stores it as JSON in
the transaction's ``origin`` (``{"note": "...", "url": ..., "name": ...}``, at most 200 characters
in all; see safe-wallet-monorepo features/tx-notes/services/encodeTxNote.ts). Only ``note`` is read.
Everything here, the note above all, is attacker-authorable text (invariant 7).

The API key (``SAFE_API_KEY``) goes in an ``Authorization: Bearer`` header. Without one the
service allows a few exploratory requests, which a 15-second poll exhausts within days.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx
from eth_account.signers.local import LocalAccount
from eth_utils import to_checksum_address
from pydantic import BaseModel, ConfigDict, Field

from contracts.setup import ZERO, sign_safe_tx
from judge.schemas import SafeTx
from sepolia.chain import SHORT_NAME, SepoliaUnavailable, redact

BASE = f"https://api.safe.global/tx-service/{SHORT_NAME}/api"
RETRY_PAUSES_S = (2, 4, 8)


class Confirmation(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    owner: str
    signature: str | None = None
    submission_date: str | None = Field(default=None, alias="submissionDate")


class ServiceTx(BaseModel):
    """One multisig transaction as the service returns it (camelCase on the wire)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    safe: str
    safe_tx_hash: str = Field(alias="safeTxHash")
    to: str
    value: int
    data: str | None = None
    operation: int
    safe_tx_gas: int = Field(default=0, alias="safeTxGas")
    base_gas: int = Field(default=0, alias="baseGas")
    gas_price: int = Field(default=0, alias="gasPrice")
    gas_token: str | None = Field(default=None, alias="gasToken")
    refund_receiver: str | None = Field(default=None, alias="refundReceiver")
    nonce: int
    confirmations: list[Confirmation] = Field(default_factory=list)
    confirmations_required: int | None = Field(default=None, alias="confirmationsRequired")
    origin: Any = None
    is_executed: bool = Field(default=False, alias="isExecuted")
    submission_date: str | None = Field(default=None, alias="submissionDate")
    proposer: str | None = None
    data_decoded: Any = Field(default=None, alias="dataDecoded",
                              description="The service's decoding, for display only; names are untrusted.")

    def safe_tx(self) -> SafeTx:
        """The struct the owners sign. The service sends null for empty data and zero addresses."""
        if self.operation not in (0, 1):
            raise ValueError(f"operation {self.operation} is neither CALL nor DELEGATECALL")
        return SafeTx(
            to=to_checksum_address(self.to), value=self.value, data=self.data or "0x", operation=self.operation,
            safe_tx_gas=self.safe_tx_gas, base_gas=self.base_gas, gas_price=self.gas_price,
            gas_token=to_checksum_address(self.gas_token or ZERO),
            refund_receiver=to_checksum_address(self.refund_receiver or ZERO), nonce=self.nonce,
        )

    def note(self) -> str | None:
        return note(self.origin)


def note(origin: Any) -> str | None:
    """Safe{Wallet}'s note from a transaction's origin, or None. Accepts the JSON string the service
    stores or an already-parsed dict; a plain string origin (a dapp URL) is not a note."""
    if isinstance(origin, str):
        try:
            origin = json.loads(origin)
        except ValueError:
            return None
    if not isinstance(origin, dict):
        return None
    text = origin.get("note")
    if not isinstance(text, str) or not text.strip():
        return None
    return text.strip()


def origin_with_note(text: str) -> str:
    """The origin Safe{Wallet} would write for a note typed in its own form."""
    out = json.dumps({"note": text}, separators=(",", ":"))
    if len(out) > 200:
        raise ValueError("the service caps origin at 200 characters; shorten the note")
    return out


# --------------------------------------------------------------------------- HTTP


def _headers() -> dict[str, str]:
    key = os.environ.get("SAFE_API_KEY", "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


def _request(method: str, path: str, **kw: Any) -> Any:
    url = f"{BASE}{path}"
    for attempt, pause in enumerate((*RETRY_PAUSES_S, None)):
        try:
            r = httpx.request(method, url, headers=_headers(), timeout=30, **kw)
        except httpx.HTTPError as exc:
            raise SepoliaUnavailable(redact(f"Transaction Service {method} {path}: {type(exc).__name__}")) from None
        if r.status_code == 429 and pause is not None:
            time.sleep(pause)
            continue
        if r.status_code >= 400:
            raise SepoliaUnavailable(redact(f"Transaction Service {method} {path}: HTTP {r.status_code} {r.text[:300]}"))
        return r.json() if r.content else None
    raise AssertionError("unreachable")


def pending(safe: str, nonce: int) -> list[ServiceTx]:
    """Every unexecuted proposal at ``nonce`` or later, lowest nonce first, as Safe{Wallet}'s queue."""
    out: list[ServiceTx] = []
    path: str | None = (f"/v1/safes/{to_checksum_address(safe)}/multisig-transactions/"
                        f"?executed=false&nonce__gte={nonce}&ordering=nonce&limit=50")
    while path:
        page = _request("GET", path)
        out += [ServiceTx.model_validate(t) for t in page.get("results", [])]
        nxt = page.get("next")
        path = nxt.split("/api", 1)[1] if nxt else None
    return [t for t in out if not t.is_executed]


def get(safe_tx_hash: str) -> ServiceTx:
    return ServiceTx.model_validate(_request("GET", f"/v1/multisig-transactions/{safe_tx_hash}/"))


def propose(safe: str, tx: SafeTx, safe_tx_hash: str, signer: LocalAccount, origin: str | None) -> None:
    """Put a transaction in the Safe{Wallet} queue with ``signer``'s confirmation, as Safe{Wallet} does."""
    sig = sign_safe_tx(bytes.fromhex(safe_tx_hash.removeprefix("0x")), [signer])
    body = {
        "to": tx.to, "value": str(tx.value), "data": tx.data if tx.data != "0x" else None,
        "operation": tx.operation, "safeTxGas": str(tx.safe_tx_gas), "baseGas": str(tx.base_gas),
        "gasPrice": str(tx.gas_price), "gasToken": tx.gas_token, "refundReceiver": tx.refund_receiver,
        "nonce": tx.nonce, "contractTransactionHash": safe_tx_hash, "sender": signer.address,
        "signature": "0x" + sig.hex(), "origin": origin,
    }
    _request("POST", f"/v1/safes/{to_checksum_address(safe)}/multisig-transactions/", json=body)


def confirm(safe_tx_hash: str, signer: LocalAccount) -> None:
    """Add ``signer``'s confirmation to a queued transaction."""
    sig = sign_safe_tx(bytes.fromhex(safe_tx_hash.removeprefix("0x")), [signer])
    _request("POST", f"/v1/multisig-transactions/{safe_tx_hash}/confirmations/", json={"signature": "0x" + sig.hex()})


def signatures(tx: ServiceTx) -> bytes:
    """The owners' confirmations packed for execTransaction (sorted by owner)."""
    confs = sorted((c for c in tx.confirmations if c.signature), key=lambda c: int(c.owner, 16))
    return b"".join(bytes.fromhex(c.signature.removeprefix("0x")) for c in confs)
