"""
LangChain Tool wrappers for hyperD's marquee endpoints.

Optional submodule — only imported when ``langchain-core`` is installed:

    pip install 'hyperd-ai[langchain]'

Usage:

    from hyperd.langchain import get_tools

    tools = get_tools(private_key="0x...")

    # Pass to a LangChain agent (or LangGraph node, or CrewAI, etc.)
    from langchain.agents import create_react_agent
    agent = create_react_agent(llm, tools)

Each tool wraps one paid endpoint with:
    * A schema describing the input parameters (so the LLM knows how to call it)
    * A name + description tuned for tool-selection prompts
    * The actual call into ``HyperD`` which signs the x402 payment

The five v0.1 tools cover the agent decision loop:
    1. ``hyperd_wallet_risk``: $0.10 — sanctions + risk-tier
    2. ``hyperd_token_security``: $0.05 — GoPlus scam scan
    3. ``hyperd_liquidation_risk``: $0.10 — cross-protocol health
    4. ``hyperd_wallet_pnl``: $0.05 — realized + unrealized
    5. ``hyperd_dex_quote``: $0.02 — Paraswap + 0x route aggregator

Full decision cycle: $0.32 USDC.
"""

from __future__ import annotations

from typing import Any

try:
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field
except ImportError as err:  # pragma: no cover
    raise ImportError(
        "hyperd.langchain requires the optional `langchain` extra. "
        "Install it with: pip install 'hyperd-ai[langchain]'"
    ) from err

from .client import HyperD


# ---- Pydantic input schemas (the LLM gets these as the tool args spec) ----


class _AddressOnly(BaseModel):
    address: str = Field(..., description="0x-prefixed 20-byte EVM address to query.")


class _AddressChain(BaseModel):
    address: str = Field(..., description="0x-prefixed 20-byte EVM address.")
    chain: str = Field(
        "base",
        description="Chain slug — one of: base, ethereum, polygon, arbitrum, optimism, avalanche, bnb. Use 'all' to fan out.",
    )


class _ContractChain(BaseModel):
    contract: str = Field(..., description="0x-prefixed ERC-20 contract address.")
    chain: str = Field("base", description="Chain slug; defaults to base.")


class _DexQuoteInput(BaseModel):
    from_token: str = Field(..., description="Source token symbol (e.g. 'USDC') or contract.")
    to_token: str = Field(..., description="Destination token symbol or contract.")
    amount: str = Field(
        ..., description="Amount of from_token to swap, as a string (e.g. '100' or '0.5')."
    )
    chain: str = Field("base", description="Chain slug; defaults to base.")


# ---- Tool factories ----


def _wallet_risk_tool(client: HyperD) -> StructuredTool:
    def run(address: str) -> dict[str, Any]:
        return client.wallet_risk(address)

    return StructuredTool.from_function(
        func=run,
        name="hyperd_wallet_risk",
        description=(
            "Score an EVM wallet for OFAC sanctions and behavioural risk using "
            "Chainalysis Sanctions Oracle + GoPlus heuristics. Cost: $0.10 USDC. "
            "Use this BEFORE interacting with any unknown counterparty wallet."
        ),
        args_schema=_AddressOnly,
    )


def _token_security_tool(client: HyperD) -> StructuredTool:
    def run(contract: str, chain: str = "base") -> dict[str, Any]:
        return client.token_security(contract, chain=chain)

    return StructuredTool.from_function(
        func=run,
        name="hyperd_token_security",
        description=(
            "Run a GoPlus security scan on an ERC-20 token contract. Returns a "
            "0-100 score plus honeypot/taxes/permissions flags. Cost: $0.05 USDC. "
            "Use this BEFORE buying or interacting with an unknown token."
        ),
        args_schema=_ContractChain,
    )


def _liquidation_risk_tool(client: HyperD) -> StructuredTool:
    def run(address: str, chain: str = "base") -> dict[str, Any]:
        return client.liquidation_risk(address, chain=chain)

    return StructuredTool.from_function(
        func=run,
        name="hyperd_liquidation_risk",
        description=(
            "Compute composite liquidation health for a wallet across Aave V3, "
            "Compound v3, Spark, and Morpho. Cost: $0.10 USDC. Use when the user "
            "asks 'am I about to get liquidated', wants to check health factor, "
            "or asks about margin-call exposure."
        ),
        args_schema=_AddressChain,
    )


def _wallet_pnl_tool(client: HyperD) -> StructuredTool:
    def run(address: str, chain: str = "base") -> dict[str, Any]:
        return client.wallet_pnl(address, chain=chain)

    return StructuredTool.from_function(
        func=run,
        name="hyperd_wallet_pnl",
        description=(
            "Compute realized + unrealized P&L for an EVM wallet. Cost: $0.05 USDC. "
            "Returns total, realized, unrealized, and per-token breakdown with mark-to-market."
        ),
        args_schema=_AddressChain,
    )


def _dex_quote_tool(client: HyperD) -> StructuredTool:
    def run(
        from_token: str, to_token: str, amount: str, chain: str = "base"
    ) -> dict[str, Any]:
        return client.dex_quote(from_token, to_token, amount, chain=chain)

    return StructuredTool.from_function(
        func=run,
        name="hyperd_dex_quote",
        description=(
            "Get the best swap route across Paraswap + 0x aggregators. Cost: $0.02 USDC. "
            "Returns the highest-output route plus gas estimate and slippage. Use BEFORE "
            "submitting a swap to find the best price."
        ),
        args_schema=_DexQuoteInput,
    )


def get_tools(
    private_key: str | None = None,
    *,
    api_base: str | None = None,
    max_usdc_per_call: float = 0.25,
    client: HyperD | None = None,
) -> list[StructuredTool]:
    """Return the 5 marquee hyperD endpoints as LangChain tools.

    Parameters
    ----------
    private_key:
        0x-prefixed EVM private key. If None, reads from ``HYPERD_WALLET_PRIVATE_KEY``.
    api_base:
        Override the API base URL.
    max_usdc_per_call:
        Per-call USDC cap. Defaults to 0.25.
    client:
        Pass an existing ``HyperD`` instance to reuse it instead of building a new one.

    Returns a list of 5 ``StructuredTool`` ready to drop into a LangChain agent.
    """
    c = client or HyperD(
        private_key=private_key, api_base=api_base, max_usdc_per_call=max_usdc_per_call
    )
    return [
        _wallet_risk_tool(c),
        _token_security_tool(c),
        _liquidation_risk_tool(c),
        _wallet_pnl_tool(c),
        _dex_quote_tool(c),
    ]


__all__ = ["get_tools"]
