# hyperd-ai — Python SDK

> Pay-per-call DeFi APIs for AI agents on Base. 20 paid x402 endpoints, USDC settlement in ~2s, no API key, no signup. The signed EIP-3009 payment is the auth.

[![PyPI](https://img.shields.io/pypi/v/hyperd-ai.svg)](https://pypi.org/project/hyperd-ai/)
[![Python](https://img.shields.io/pypi/pyversions/hyperd-ai.svg)](https://pypi.org/project/hyperd-ai/)
[![License](https://img.shields.io/pypi/l/hyperd-ai.svg)](./LICENSE)

## Try it free

First 5 calls per IP per 24h are free — no wallet, no signup, no API key. Just curl:

```bash
curl "https://api.hyperd.ai/api/balance?address=0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
```

Lifetime cap: 25 calls per IP. After that (or when daily quota is exhausted), the endpoint returns HTTP 402 — sign a small EIP-3009 USDC payment on Base via the [Python SDK](https://pypi.org/project/hyperd-ai/) or [TypeScript MCP server](https://www.npmjs.com/package/hyperd-mcp).

`/api/wallet/pnl` has a tighter free-tier cap of 1 call/IP/day (heavy upstream).

## Install

```bash
pip install hyperd-ai
```

For LangChain Tool wrappers:

```bash
pip install 'hyperd-ai[langchain]'
```

## Quick start

```python
from hyperd import HyperD

# private_key can be passed explicitly or read from HYPERD_WALLET_PRIVATE_KEY env
client = HyperD(private_key="0x...")

# Cost: $0.10 USDC — auto-signed and settled
risk = client.wallet_risk("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
print(risk["sanctioned"], risk["risk_tier"], risk["categories"])

# Cost: $0.05
pnl = client.wallet_pnl("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", chain="base")
print(f"Total P&L: ${pnl['total_pnl_usd']:.2f}")
```

## Fund the wallet

The wallet at `private_key` must hold USDC on Base. Typical agent runs cost a few cents — **~$5 of USDC is enough for hundreds of decision cycles.**

- Buy USDC directly on Base via Coinbase / Coinbase Wallet
- Bridge from Ethereum via [Across](https://across.to) or [Hop](https://hop.exchange)
- Get a test wallet at any Ethereum wallet generator (don't use your primary)

## Endpoints

### Marquee (the agent decision loop — $0.32 total)

| Method | Cost | What it answers |
|---|---|---|
| `client.wallet_risk(address)` | $0.10 | Is this address OFAC-sanctioned or otherwise risky? |
| `client.token_security(contract, chain)` | $0.05 | Is this token a scam? (GoPlus 0-100 score) |
| `client.liquidation_risk(address, chain)` | $0.10 | Cross-protocol health across Aave V3 / Compound v3 / Spark / Morpho |
| `client.wallet_pnl(address, chain)` | $0.05 | Realized + unrealized P&L, per-token breakdown |
| `client.dex_quote(from_token, to_token, amount, chain)` | $0.02 | Best swap route (Paraswap + 0x) |

### Secondary

| Method | Cost |
|---|---|
| `client.balance(address, chain)` | $0.01 |
| `client.token_info(query)` | $0.01 |
| `client.yield_recommend(amount, risk)` | $0.05 |
| `client.protocol_tvl(slug)` | $0.01 |
| `client.gas_estimate(chain)` | $0.005 |
| `client.wallet_persona(address)` | $0.10 |
| `client.contract_audit(contract, chain)` | $0.10 |
| `client.governance_summarize(proposal_url)` | $0.10 |
| `client.sentiment_token(token, window)` | $0.05 |
| `client.wallet_anomaly(address, chain, window)` | $0.10 |
| `client.budget_guardian(address)` | $0.01 |
| `client.bundle(calls)` | $0.20 fixed (up to 10 calls bundled) |

### Free (no payment)

| Method | What |
|---|---|
| `client.health()` | Liveness + version |
| `client.catalog()` | Full machine-readable catalog of every endpoint + price |

## LangChain

```python
from hyperd.langchain import get_tools
from langchain.agents import create_react_agent
from langchain_openai import ChatOpenAI

tools = get_tools(private_key="0x...")  # 5 marquee endpoints as StructuredTools
llm = ChatOpenAI(model="gpt-4o-mini")
agent = create_react_agent(llm, tools)

result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": "Is 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 safe to send funds to?",
    }],
})
```

The agent will pick `hyperd_wallet_risk` from the tool list, sign + settle the payment, and return the result to the LLM for synthesis.

## Safety: the per-call USDC cap

Every paid method respects `max_usdc_per_call` (default $0.25). If the server's 402 challenge requests more than that, the SDK throws `HyperdPaymentRefused` BEFORE signing — your wallet can't be drained even by a misbehaving or compromised server.

To raise the cap (e.g. for the $3 watch.create endpoint):

```python
client = HyperD(private_key="0x...", max_usdc_per_call=5.0)
```

## How the x402 payment works

1. The SDK makes a normal HTTP GET to the paid endpoint.
2. The server responds with HTTP 402 Payment Required and a machine-readable payment-required header.
3. The SDK decodes the header, signs an EIP-3009 USDC transfer authorization on Base, and retries with the signed payment in the `X-Payment` header.
4. Coinbase's x402 facilitator verifies the signature, submits the transfer on-chain, and unblocks the response. ~2 seconds end-to-end.

There's no key store to rotate, no rate-limit form to fill out, no signup. The signature is the auth.

## Errors

| Exception | When |
|---|---|
| `HyperdPaymentRefused` | Server requested more USDC than `max_usdc_per_call` |
| `HyperdHttpError` | Server returned a non-2xx after the payment retry |
| `HyperdError` | Malformed 402 challenge, missing EIP-712 domain fields, or signing error |

All three inherit from `HyperdError` so you can catch the umbrella class.

## Remote MCP-over-HTTPS (for non-Python agents)

hyperD's tool catalog is also exposed as a remote MCP server at `https://api.hyperd.ai/mcp`. The Python SDK is the right choice for Python agents; the remote MCP is the right choice for:

- Agents in other languages that already speak MCP (TypeScript, Go via mcp-go, etc.)
- Hosted agent platforms that pull tools from MCP URLs (Smithery, Cursor's remote MCP roadmap)
- Quick API discovery without installing anything

Same 17 tools, same per-IP free-tier quota, same x402 payment auth.

```
POST https://api.hyperd.ai/mcp
{"jsonrpc":"2.0","id":1,"method":"tools/list"}
```

## Production integrators

Other x402 merchants whose integrator docs reference this SDK's [`_buyer.py`](src/hyperd/_buyer.py) (~210 LOC, `requests` + `eth-account` only) as a canonical non-TypeScript buyer implementation:

- **AgentOracle** ([@TKCollective](https://github.com/TKCollective)) — pay-per-call oracle aggregation on x402
- **x402-market** ([@AsaiShota](https://github.com/AsaiShota)) — x402 marketplace + merchant tooling

Coordination context: [x402-foundation/x402#2207](https://github.com/x402-foundation/x402/issues/2207) (the canonical-buyer / Bazaar resource-keying thread).

If you're shipping an x402 service in Go, Rust, JVM, .NET, or any non-TS environment and want a working reference, `_buyer.py` is the smallest faithful implementation of the v2 wire format — copy-adapt freely (MIT).

## Links

- **Production API**: https://api.hyperd.ai
- **Endpoint catalog**: https://api.hyperd.ai/api/catalog
- **ElizaOS plugin**: [`@hyperd-ai/plugin-hyperd`](https://www.npmjs.com/package/@hyperd-ai/plugin-hyperd) (TypeScript)
- **MCP server**: [`hyperd-mcp`](https://www.npmjs.com/package/hyperd-mcp) (stdio for Claude Desktop / Cursor / Cline / Zed)
- **Glama listing**: https://glama.ai/mcp/servers/hyperd-ai/hyperd-mcp
- **x402 protocol**: https://x402.org

## License

MIT. Built for agents that pay their own way.
