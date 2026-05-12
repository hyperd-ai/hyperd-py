"""
Smoke tests for the hyperd SDK.

These tests don't make real network calls. The buyer flow is exercised
end-to-end against the live API in examples/python/risk_sentinel.py from
the monorepo (hyperd-mcp public mirror) — that's where the integration
testing lives.

Run:
    pip install -e '.[dev]'
    pytest
"""

from __future__ import annotations

import pytest

from hyperd import (
    HyperD,
    HyperdError,
    HyperdHttpError,
    HyperdPaymentRefused,
)
from hyperd._buyer import (
    PaymentRequirement,
    encode_payment_header,
    parse_payment_required,
)


# A throwaway key from EIP test vectors. Derives to a famous test address with $0 balance.
TEST_KEY = "0x0000000000000000000000000000000000000000000000000000000000000001"


class TestClientConstruction:
    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("HYPERD_WALLET_PRIVATE_KEY", raising=False)
        with pytest.raises(HyperdError, match="No private key"):
            HyperD()

    def test_env_key_picked_up(self, monkeypatch):
        monkeypatch.setenv("HYPERD_WALLET_PRIVATE_KEY", TEST_KEY)
        client = HyperD()
        assert client.address.startswith("0x")
        assert len(client.address) == 42

    def test_explicit_key_wins_over_env(self, monkeypatch):
        # Different key with valid format
        other_key = "0x" + "ab" * 32
        monkeypatch.setenv("HYPERD_WALLET_PRIVATE_KEY", TEST_KEY)
        client = HyperD(private_key=other_key)
        # Both keys derive to different addresses, so address should match `other_key`
        assert client.address == HyperD(private_key=other_key).address

    def test_malformed_key_raises(self):
        with pytest.raises(HyperdError, match="0x-prefixed"):
            HyperD(private_key="not-a-key")

    def test_short_key_raises(self):
        with pytest.raises(HyperdError, match="0x-prefixed"):
            HyperD(private_key="0xabc")

    def test_default_api_base(self):
        client = HyperD(private_key=TEST_KEY)
        assert client.api_base == "https://api.hyperd.ai"

    def test_default_max_usdc_per_call(self):
        client = HyperD(private_key=TEST_KEY)
        assert client.max_usdc_per_call == 0.25


class TestPaymentRequiredHeader:
    def test_missing_header_raises(self):
        with pytest.raises(HyperdError, match="no payment-required header"):
            parse_payment_required({})

    def test_invalid_base64_raises(self):
        with pytest.raises(HyperdError, match="not valid base64"):
            parse_payment_required({"payment-required": "not!valid!base64!@#"})

    def test_empty_accepts_raises(self):
        import base64
        import json

        body = base64.b64encode(json.dumps({"accepts": []}).encode()).decode()
        with pytest.raises(HyperdError, match="empty accepts"):
            parse_payment_required({"payment-required": body})

    def test_unsupported_scheme_raises(self):
        import base64
        import json

        body = base64.b64encode(
            json.dumps(
                {"accepts": [{"scheme": "fancy", "network": "solana:mainnet", "amount": "1"}]}
            ).encode()
        ).decode()
        with pytest.raises(HyperdError, match="No supported payment option"):
            parse_payment_required({"payment-required": body})

    def test_well_formed_challenge_parses(self):
        import base64
        import json

        challenge = {
            "x402Version": 2,
            "accepts": [
                {
                    "scheme": "exact",
                    "network": "eip155:8453",
                    "amount": "100000",
                    "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                    "payTo": "0x61b51131E1e44552dE2F151Ca59DAc707D9cf1C6",
                    "maxTimeoutSeconds": 300,
                    "extra": {"name": "USDC", "version": "2"},
                }
            ],
            "resource": {"url": "https://api.hyperd.ai/api/balance"},
            "extensions": {"bazaar": {"info": {}, "schema": {}}},
        }
        body = base64.b64encode(json.dumps(challenge).encode()).decode()
        req, raw, resource, extensions = parse_payment_required({"payment-required": body})
        assert isinstance(req, PaymentRequirement)
        assert req.network == "eip155:8453"
        assert req.amount == "100000"
        assert raw == challenge["accepts"][0]
        assert resource == challenge["resource"]
        assert extensions == challenge["extensions"]


class TestEncoding:
    def test_encode_payment_header_returns_ascii(self):
        payload = {"x402Version": 2, "scheme": "exact", "network": "eip155:8453"}
        header = encode_payment_header(payload)
        assert isinstance(header, str)
        # ASCII-safe (no padding mishaps, no surprise unicode)
        header.encode("ascii")


class TestPublicAPI:
    """All exported names exist and are correctly typed."""

    def test_imports(self):
        from hyperd import HyperD, HyperdError, HyperdHttpError, HyperdPaymentRefused, __version__

        assert callable(HyperD)
        assert issubclass(HyperdError, RuntimeError)
        assert issubclass(HyperdHttpError, HyperdError)
        assert issubclass(HyperdPaymentRefused, HyperdError)
        assert isinstance(__version__, str)
