"""
Example 1 — Direct HyperD client usage.

The simplest possible demo: instantiate HyperD, hit a paid endpoint, print the
result. No LangChain, no LLM, just the SDK against the live API.

Requires:
    pip install hyperd-ai
    export HYPERD_WALLET_PRIVATE_KEY=0x...   # a Base wallet with >= $0.50 USDC

Run:
    python examples/01_basic_usage.py
"""

from __future__ import annotations

import json
import sys

from hyperd import HyperD, HyperdError, HyperdHttpError, HyperdPaymentRefused


# A famous EVM address with rich on-chain history — perfect for demos.
VITALIK = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


def main() -> int:
    try:
        client = HyperD()
    except HyperdError as err:
        print(f"Setup error: {err}", file=sys.stderr)
        print("Set HYPERD_WALLET_PRIVATE_KEY in your environment first.", file=sys.stderr)
        return 1

    print(f"Calling as buyer: {client.address}")
    print(f"API:    {client.api_base}")
    print(f"Cap:    ${client.max_usdc_per_call:.4f} USDC per call")
    print("─" * 64)

    # ── Call 1: wallet risk ($0.10) ─────────────────────────────────────────
    print(f"\n[1] wallet_risk({VITALIK[:10]}…) — costs $0.10")
    try:
        risk = client.wallet_risk(VITALIK)
        print(f"    sanctioned: {risk.get('sanctioned')}")
        print(f"    risk_tier:  {risk.get('risk_tier')}")
        print(f"    categories: {risk.get('categories') or '[]'}")
    except HyperdPaymentRefused as err:
        print(f"    PAYMENT REFUSED: {err}")
    except HyperdHttpError as err:
        print(f"    HTTP {err.status}: {err.body}")

    # ── Call 2: token security ($0.05) ──────────────────────────────────────
    # WETH on Base — a known-good token, should score very high.
    weth_base = "0x4200000000000000000000000000000000000006"
    print(f"\n[2] token_security({weth_base[:10]}…) — costs $0.05")
    try:
        sec = client.token_security(weth_base, chain="base")
        print(f"    security_score:  {sec.get('security_score')}/100")
        print(f"    honeypot:        {sec.get('honeypot')}")
        print(f"    owner_can_mint:  {sec.get('owner_can_mint')}")
    except HyperdHttpError as err:
        print(f"    HTTP {err.status}: {err.body}")

    # ── Call 3: dex_quote ($0.02) ───────────────────────────────────────────
    print(f"\n[3] dex_quote(100 USDC → WETH on base) — costs $0.02")
    try:
        quote = client.dex_quote("USDC", "WETH", "100", chain="base")
        best = quote.get("best", {})
        print(f"    source:      {best.get('source')}")
        print(f"    amount_out:  {best.get('amount_out')} WETH")
        print(f"    slippage:    {best.get('slippage_pct'):.2f}%")
    except HyperdHttpError as err:
        print(f"    HTTP {err.status}: {err.body}")

    # ── Free endpoint (no payment) ──────────────────────────────────────────
    print("\n[free] health() — no charge")
    health = client.health()
    print(f"    status:  {health.get('status')}")
    print(f"    version: {health.get('version')}")

    print("\n" + "─" * 64)
    print(f"Total spent: $0.17 USDC (3 paid calls). Wallet: {client.address}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
