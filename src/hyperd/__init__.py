"""
hyperd — Python SDK for pay-per-call DeFi APIs over x402.

Quick start:

    pip install hyperd-ai

    from hyperd import HyperD

    client = HyperD(private_key="0x...")  # or HYPERD_WALLET_PRIVATE_KEY env

    risk = client.wallet_risk("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    print(risk["sanctioned"], risk["risk_tier"])

LangChain integration:

    pip install 'hyperd-ai[langchain]'

    from hyperd.langchain import get_tools

    tools = get_tools(private_key="0x...")
    # Pass `tools` to a LangChain agent

See https://hyperd.ai for the full endpoint catalog and live API.
"""

from .client import (
    HyperD,
    HyperdError,
    HyperdHttpError,
    HyperdPaymentRefused,
)

__version__ = "0.1.0"

__all__ = [
    "HyperD",
    "HyperdError",
    "HyperdHttpError",
    "HyperdPaymentRefused",
    "__version__",
]
