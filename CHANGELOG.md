# Changelog

## 0.1.0 — 2026-05-12

Initial release.

- `HyperD` client with sync methods for all 20 paid endpoints + 2 free meta endpoints
- Full x402 V2 buyer flow (EIP-3009 signing, payment retry, payload echo per spec §5.2 including the `extensions` field — the "7th cause" fix from coinbase/x402#2207)
- Per-call USDC cap enforcement via `max_usdc_per_call` (default $0.25). Raises `HyperdPaymentRefused` before signing if the server's 402 challenge requests more than the cap — protects against wallet-drain attacks.
- Optional LangChain Tool wrappers via `pip install 'hyperd-ai[langchain]'`
- 14+ unit tests covering construction, key validation, 402-header parsing, and public API surface

Targets the Python-native agent ecosystem (Almanak quants, LangChain agents, custom Python orchestrators) — sibling to:
- `@hyperd-ai/plugin-hyperd@0.1.1` on npm (ElizaOS / TypeScript agents)
- `hyperd-mcp@1.0.3` on npm (MCP server for Claude Desktop, Cursor, Cline, Zed)
