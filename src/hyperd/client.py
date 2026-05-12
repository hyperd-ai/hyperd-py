"""
HyperD — the canonical Python client for hyperD's pay-per-call DeFi API.

Usage:

    from hyperd import HyperD

    client = HyperD(private_key="0x...")  # or HYPERD_WALLET_PRIVATE_KEY env

    risk = client.wallet_risk("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    print(risk["sanctioned"], risk["risk_tier"])

    pnl = client.wallet_pnl("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", chain="base")
    print(pnl["total_pnl_usd"])

All paid methods deduct USDC from the wallet at ``private_key``. The wallet
must hold USDC on Base — typically ~$5 is enough for hundreds of calls.

See https://api.hyperd.ai/api/catalog for the full endpoint list and pricing.
"""

from __future__ import annotations

import os
from typing import Any

from eth_account import Account

from ._buyer import (
    HyperdError,
    HyperdHttpError,
    HyperdPaymentRefused,
    call_with_payment,
)

DEFAULT_API_BASE = "https://api.hyperd.ai"
DEFAULT_MAX_USDC_PER_CALL = 0.25


def _resolve_private_key(private_key: str | None) -> str:
    """Resolve the buyer wallet key from arg → env, validate format."""
    key = private_key or os.environ.get("HYPERD_WALLET_PRIVATE_KEY")
    if not key:
        raise HyperdError(
            "No private key. Pass private_key= or set HYPERD_WALLET_PRIVATE_KEY. "
            "Generate one at https://docs.alchemy.com/docs/how-to-create-a-new-ethereum-address "
            "and fund with USDC on Base."
        )
    if not key.startswith("0x") or len(key) != 66:
        raise HyperdError(
            "Private key must be a 0x-prefixed 64-hex-character (32-byte) string."
        )
    return key


class HyperD:
    """High-level client for hyperD's paid DeFi endpoints.

    Each method that hits a paid endpoint signs an EIP-3009 USDC transfer
    authorization on Base for the server-requested amount and submits it via
    the x402 protocol. Coinbase's facilitator settles in ~2s.

    Parameters
    ----------
    private_key:
        0x-prefixed EVM private key holding USDC on Base. If None, read from
        the ``HYPERD_WALLET_PRIVATE_KEY`` environment variable.
    api_base:
        Override the API base URL. Defaults to ``https://api.hyperd.ai``.
    max_usdc_per_call:
        Per-call hard cap on USDC paid out. Refuses calls priced above this.
        Default ``0.25`` (25 cents). Bumping above $1 is generally unwise
        unless you trust the upstream server completely.
    timeout, retry_timeout:
        HTTP timeouts for the initial 402 fetch and the post-signature retry.
        Defaults are 30s and 60s, matching the x402 reference clients.

    Raises
    ------
    HyperdPaymentRefused:
        Server requested more USDC than max_usdc_per_call permits.
    HyperdHttpError:
        Server returned a non-2xx after the payment retry.
    HyperdError:
        Malformed 402 challenge or signing error.
    """

    def __init__(
        self,
        private_key: str | None = None,
        *,
        api_base: str | None = None,
        max_usdc_per_call: float = DEFAULT_MAX_USDC_PER_CALL,
        timeout: float = 30.0,
        retry_timeout: float = 60.0,
    ) -> None:
        key = _resolve_private_key(private_key)
        self._account = Account.from_key(key)
        self.api_base = (api_base or os.environ.get("HYPERD_API_BASE") or DEFAULT_API_BASE).rstrip("/")
        self.max_usdc_per_call = max_usdc_per_call
        self.timeout = timeout
        self.retry_timeout = retry_timeout

    @property
    def address(self) -> str:
        """The 0x address of the buyer wallet (derived from private_key)."""
        return self._account.address

    # ---- Marquee endpoints (v0.1) ----

    def wallet_risk(self, address: str) -> dict[str, Any]:
        """Score an address for sanctions + behavioural risk. Cost: $0.10.

        Returns a dict with at least ``sanctioned``, ``risk_tier``, ``categories``.
        """
        return self._get("/api/risk/wallet", {"address": address})

    def token_security(self, contract: str, chain: str = "base") -> dict[str, Any]:
        """GoPlus security score (0-100) for an ERC-20 contract. Cost: $0.05.

        Honeypot detection, owner permissions, buy/sell taxes, holder concentration.
        """
        return self._get("/api/token/security", {"contract": contract, "chain": chain})

    def liquidation_risk(self, address: str, chain: str = "base") -> dict[str, Any]:
        """Composite health factor across Aave V3, Compound v3, Spark, Morpho. Cost: $0.10.

        Pass chain='all' to fan out across all 7 supported EVM chains.
        """
        return self._get("/api/liquidation/risk", {"address": address, "chain": chain})

    def wallet_pnl(self, address: str, chain: str = "base") -> dict[str, Any]:
        """Realized + unrealized P&L for an address. Cost: $0.05.

        Returns total, realized, unrealized, and per-token breakdown.
        """
        return self._get("/api/wallet/pnl", {"address": address, "chain": chain})

    def dex_quote(
        self,
        from_token: str,
        to_token: str,
        amount: str | float | int,
        chain: str = "base",
    ) -> dict[str, Any]:
        """Best swap route across Paraswap + 0x. Cost: $0.02."""
        return self._get(
            "/api/dex/quote",
            {"from": from_token, "to": to_token, "amount": str(amount), "chain": chain},
        )

    # ---- v0.2 secondary endpoints ----

    def balance(self, address: str, chain: str = "base") -> dict[str, Any]:
        """Multi-chain ERC-20 + native balance. Cost: $0.01.

        Pass chain='all' to fan out in parallel across all supported chains.
        """
        return self._get("/api/balance", {"address": address, "chain": chain})

    def token_info(self, query: str) -> dict[str, Any]:
        """Aggregated metadata across CoinGecko + DefiLlama. Cost: $0.01."""
        return self._get("/api/token/info", {"query": query})

    def yield_recommend(self, amount: float | int, risk: str = "medium") -> dict[str, Any]:
        """DefiLlama yield universe filtered by risk tier. Cost: $0.05."""
        return self._get("/api/yield", {"amount": amount, "risk": risk})

    def protocol_tvl(self, slug: str) -> dict[str, Any]:
        """DefiLlama protocol TVL + audit history. Cost: $0.01.

        Use the DefiLlama slug (e.g., 'aave', 'compound-v3').
        """
        return self._get("/api/protocol/tvl", {"slug": slug})

    def gas_estimate(self, chain: str = "base") -> dict[str, Any]:
        """Gas + tip percentiles for fast/standard/slow inclusion. Cost: $0.005."""
        return self._get("/api/gas/estimate", {"chain": chain})

    def wallet_persona(self, address: str) -> dict[str, Any]:
        """Behavioural classification: Trader/HODLer/MEV bot/Whale/etc. Cost: $0.10."""
        return self._get("/api/wallet/persona", {"address": address})

    def contract_audit(self, contract: str, chain: str = "base") -> dict[str, Any]:
        """Composite audit score (GoPlus + Sourcify + DefiLlama). Cost: $0.10."""
        return self._get("/api/contract/audit", {"contract": contract, "chain": chain})

    def governance_summarize(self, proposal_url: str) -> dict[str, Any]:
        """Snapshot/Tally proposal analysed by Claude or GPT-4o-mini. Cost: $0.10."""
        return self._get("/api/governance/summarize", {"proposal_url": proposal_url})

    def sentiment_token(self, token: str, window: str = "24h") -> dict[str, Any]:
        """Farcaster sentiment 0-100 + volume + trend. Cost: $0.05."""
        return self._get("/api/sentiment/token", {"token": token, "window": window})

    def wallet_anomaly(
        self, address: str, chain: str = "base", window: str = "24h"
    ) -> dict[str, Any]:
        """Behavioural deviation vs the wallet's own 180-day baseline. Cost: $0.10."""
        return self._get(
            "/api/wallet/anomaly", {"address": address, "chain": chain, "window": window}
        )

    def budget_guardian(self, address: str) -> dict[str, Any]:
        """Agent USDC-spend visibility + optional cap check. Cost: $0.01."""
        return self._get("/api/budget/guardian", {"address": address})

    def bundle(self, calls: list[dict[str, Any]]) -> dict[str, Any]:
        """Bundle 1-10 paid GETs into one $0.20 settlement. Cost: $0.20 fixed.

        Each call in `calls` is a dict with keys: id, method, path, query.
        Example:

            client.bundle([
                {"id": "bal", "method": "GET", "path": "/api/balance",
                 "query": {"address": "0x...", "chain": "base"}},
                {"id": "risk", "method": "GET", "path": "/api/risk/wallet",
                 "query": {"address": "0x..."}},
            ])
        """
        return self._post("/api/bundle", {"calls": calls})

    # ---- Free endpoints (no payment) ----

    def health(self) -> dict[str, Any]:
        """Liveness check. No payment, no auth."""
        import requests

        r = requests.get(f"{self.api_base}/api/health", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def catalog(self) -> dict[str, Any]:
        """Full machine-readable catalog of every endpoint + price. Free."""
        import requests

        r = requests.get(f"{self.api_base}/api/catalog", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ---- Internal helpers ----

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        return call_with_payment(
            self._account,
            self.api_base,
            "GET",
            path,
            params=params,
            max_usdc_per_call=self.max_usdc_per_call,
            timeout=self.timeout,
            retry_timeout=self.retry_timeout,
        )

    def _post(self, path: str, body: Any) -> dict[str, Any]:
        return call_with_payment(
            self._account,
            self.api_base,
            "POST",
            path,
            body=body,
            max_usdc_per_call=self.max_usdc_per_call,
            timeout=self.timeout,
            retry_timeout=self.retry_timeout,
        )


__all__ = [
    "HyperD",
    "HyperdError",
    "HyperdHttpError",
    "HyperdPaymentRefused",
]
