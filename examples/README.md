# hyperd-ai — examples

Two runnable examples showing how to call hyperD from Python.

## 01_basic_usage.py — direct SDK

Calls 3 paid endpoints (`wallet_risk`, `token_security`, `dex_quote`) plus 1 free endpoint (`health`). No LLM. Prints raw output. Cost: ~$0.17 USDC per run.

```bash
pip install hyperd-ai
export HYPERD_WALLET_PRIVATE_KEY=0x...
python examples/01_basic_usage.py
```

## 02_langchain_agent.py — LangChain ReAct agent

A real LangChain agent that picks hyperD tools to answer natural-language questions about wallets, tokens, and trades. The LLM (gpt-4o-mini by default) reads the tool descriptions, decides which to call, signs the x402 payment per call, and synthesizes a plain-English answer.

```bash
pip install 'hyperd-ai[langchain]' langchain langchain-openai
export HYPERD_WALLET_PRIVATE_KEY=0x...
export OPENAI_API_KEY=sk-...

# Default question (risk-checks Vitalik's address + asks for a swap quote)
python examples/02_langchain_agent.py

# Or pass your own
python examples/02_langchain_agent.py "Is 0x... a scam token on Base?"
```

Typical run:
- 1-3 paid hyperD calls ($0.02 - $0.30 USDC total)
- A handful of LLM calls to gpt-4o-mini (~$0.001)
- ~5-10 seconds end-to-end

## What both examples demonstrate

- **Zero account setup on hyperD.** No API key, no signup, no rate-limit form. The signed x402 USDC payment is the auth.
- **Cap enforcement.** The SDK refuses calls priced above `max_usdc_per_call` (default $0.25) BEFORE signing. Drop-in protection against a compromised or misbehaving server draining your wallet.
- **Standard LangChain tool interface.** `get_tools()` returns plain `StructuredTool` instances — drop them into any LangChain agent, LangGraph node, or CrewAI workflow.

## Funding the test wallet

The wallet at `HYPERD_WALLET_PRIVATE_KEY` needs USDC on Base. ~$5 of USDC is plenty for hundreds of test runs.

- Buy USDC on Base directly via [Coinbase](https://www.coinbase.com) / Coinbase Wallet
- Bridge from Ethereum via [Across](https://across.to) or [Hop](https://hop.exchange)
- Generate a throwaway wallet with any Ethereum wallet generator — don't use your primary

## Production catalog

Live API: [api.hyperd.ai/api/catalog](https://api.hyperd.ai/api/catalog) — full machine-readable list of all 20 paid endpoints + current pricing.
