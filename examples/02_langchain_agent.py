"""
Example 2 — LangChain ReAct agent using the 5 hyperD marquee tools.

The agent receives a natural-language question and uses hyperD's pay-per-call
DeFi tools to answer it. The full payment flow happens transparently: agent
picks a tool, tool signs an EIP-3009 USDC authorization, server settles,
agent gets the result, LLM synthesizes the final answer.

This is the canonical "agent that pays its own way" demo.

Requires:
    pip install 'hyperd-ai[langchain]' langchain langchain-openai
    export HYPERD_WALLET_PRIVATE_KEY=0x...   # Base wallet with >= $0.50 USDC
    export OPENAI_API_KEY=sk-...

Run:
    python examples/02_langchain_agent.py "Is 0xd8dA…6045 safe to send 1 ETH to?"

Or with no args, runs a default risk-check on Vitalik's address.
"""

from __future__ import annotations

import os
import sys

# The LangChain integration is an optional extra — fail fast with a useful
# message if it isn't installed.
try:
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI
except ImportError as err:
    print(
        "Missing LangChain deps. Install with:\n"
        "    pip install 'hyperd-ai[langchain]' langchain langchain-openai",
        file=sys.stderr,
    )
    raise SystemExit(1) from err

from hyperd.langchain import get_tools


DEFAULT_QUESTION = (
    "I'm thinking of sending 1 ETH to 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045. "
    "Is the destination safe? Is this address sanctioned? "
    "Also, what's the current best swap quote for 1 WETH → USDC on Base?"
)


def main() -> int:
    if not os.environ.get("HYPERD_WALLET_PRIVATE_KEY"):
        print(
            "Set HYPERD_WALLET_PRIVATE_KEY in your environment "
            "(a Base wallet holding >= $0.50 USDC).",
            file=sys.stderr,
        )
        return 1
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY in your environment.", file=sys.stderr)
        return 1

    # 1. Build the 5 hyperD tools (auto-reads HYPERD_WALLET_PRIVATE_KEY)
    tools = get_tools()

    # 2. Build a ReAct-style agent. The LLM picks tools based on description.
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a careful DeFi assistant. When the user asks about a wallet, "
                "token, or trade, use the hyperD tools to gather data BEFORE answering. "
                "Each tool call costs a small amount of USDC ($0.02-$0.10 typical). "
                "Prefer cheaper tools when they'll do (e.g. dex_quote over a full chain "
                "of look-ups). Synthesize a concise plain-English answer at the end.",
            ),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=8)

    # 3. Run
    question = " ".join(sys.argv[1:]) or DEFAULT_QUESTION
    print(f"\nQuestion: {question}\n" + "═" * 64)
    result = executor.invoke({"input": question})
    print("\n" + "═" * 64)
    print("Final answer:\n")
    print(result["output"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
