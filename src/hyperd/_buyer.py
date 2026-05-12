"""
x402 buyer flow — sign + retry pattern for paid endpoints.

This is the internal implementation. Most users should use the high-level
``HyperD`` class in ``client.py`` instead of touching these functions directly.

The flow:
1. Send the request unauthenticated.
2. If server returns 402 Payment Required, decode the `payment-required` header.
3. Sign an EIP-3009 ``transferWithAuthorization`` for the requested USDC amount.
4. Resend with the signed payment in the ``X-Payment`` (and ``PAYMENT-SIGNATURE``)
   headers.
5. Server settles via Coinbase's x402 facilitator (~2s on Base) and returns 200.

References:
    * x402 V2 specification: https://github.com/x402-foundation/x402/blob/main/specs/x402-specification-v2.md
    * EIP-3009 transferWithAuthorization: https://eips.ethereum.org/EIPS/eip-3009
    * Cap-enforcement rationale + #2207 thread context: see CHANGELOG.md
"""

from __future__ import annotations

import base64
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

import requests
from eth_account import Account


class HyperdError(RuntimeError):
    """Base class for all SDK errors."""


class HyperdHttpError(HyperdError):
    """Server returned a non-2xx status after the payment retry."""

    def __init__(self, message: str, status: int, body: Any) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class HyperdPaymentRefused(HyperdError):
    """Server requested more USDC than the per-call cap allowed."""


@dataclass
class PaymentRequirement:
    """Parsed fields from a 402 challenge's chosen payment option."""

    scheme: str
    network: str
    amount: str  # atomic units (6 decimals on USDC)
    asset: str
    pay_to: str
    max_timeout_seconds: int
    extra: dict[str, Any]


def parse_payment_required(
    headers: dict[str, str],
) -> tuple[PaymentRequirement, dict[str, Any], Any, Any]:
    """Decode the ``payment-required`` header from a 402 response.

    Returns (PaymentRequirement, raw-requirement-dict, resource-obj, extensions).
    The raw dict and the resource/extensions fields must be echoed back into
    the v2 PaymentPayload — see ``sign_payment_authorization`` for details.

    Raises HyperdError if the header is missing, malformed, or carries no
    supported (scheme, network) combination.
    """
    raw = headers.get("payment-required") or headers.get("PAYMENT-REQUIRED")
    if not raw:
        raise HyperdError(
            "Server returned 402 but no payment-required header was set. "
            "The API may be misconfigured."
        )
    try:
        decoded = json.loads(base64.b64decode(raw).decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as err:
        raise HyperdError(f"payment-required header is not valid base64+JSON: {err}") from err
    accepts = decoded.get("accepts") or []
    if not accepts:
        raise HyperdError("payment-required challenge has an empty accepts list.")
    resource_obj = decoded.get("resource")
    extensions = decoded.get("extensions")
    for opt in accepts:
        if opt.get("scheme") == "exact" and opt.get("network", "").startswith("eip155:"):
            try:
                req = PaymentRequirement(
                    scheme=opt["scheme"],
                    network=opt["network"],
                    amount=str(opt["amount"]),
                    asset=opt["asset"],
                    pay_to=opt["payTo"],
                    max_timeout_seconds=int(opt.get("maxTimeoutSeconds", 300)),
                    extra=opt.get("extra") or {},
                )
            except (KeyError, ValueError, TypeError) as err:
                raise HyperdError(
                    f"Malformed payment requirement in 402 challenge: {err}"
                ) from err
            return req, opt, resource_obj, extensions
    raise HyperdError(
        f"No supported payment option in 402 challenge. This SDK handles 'exact' "
        f"scheme on eip155:* networks. Got: {[(a.get('scheme'), a.get('network')) for a in accepts]}"
    )


def sign_payment_authorization(
    account: Account,
    req: PaymentRequirement,
    raw_requirement: dict[str, Any],
    resource_obj: Any,
    extensions: Any,
) -> dict[str, Any]:
    """Sign an EIP-3009 transferWithAuthorization for the 402 challenge.

    Returns a v2 PaymentPayload envelope ready to base64-encode into the
    ``X-Payment`` / ``PAYMENT-SIGNATURE`` header.

    The three echo fields (accepted / resource / extensions) are required by
    the v2 spec for CDP Bazaar's facilitator to attribute the settlement
    correctly. Omitting `extensions` is the famous "7th cause" bug from
    coinbase/x402 issue #2207 — settlements succeed on-chain but never
    surface in /discovery/merchant.
    """
    chain_id = int(req.network.split(":", 1)[1])
    valid_after = max(0, int(time.time()) - 600)
    valid_before = int(time.time()) + req.max_timeout_seconds
    nonce_bytes = secrets.token_bytes(32)
    nonce_hex = "0x" + nonce_bytes.hex()

    name = req.extra.get("name")
    version = req.extra.get("version")
    if not name or not version:
        raise HyperdError(
            f"402 challenge missing required extra.name / extra.version for the "
            f"EIP-712 domain (got extra={req.extra!r}). Server should include these "
            f"per the x402 specification."
        )

    typed_data = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": name,
            "version": version,
            "chainId": chain_id,
            "verifyingContract": req.asset,
        },
        "message": {
            "from": account.address,
            "to": req.pay_to,
            "value": int(req.amount),
            "validAfter": valid_after,
            "validBefore": valid_before,
            "nonce": nonce_bytes,
        },
    }
    signed = account.sign_typed_data(full_message=typed_data)
    signature_hex = signed.signature.hex()
    if not signature_hex.startswith("0x"):
        signature_hex = "0x" + signature_hex

    payload: dict[str, Any] = {
        "x402Version": 2,
        "scheme": req.scheme,
        "network": req.network,
        "accepted": raw_requirement,
        "payload": {
            "signature": signature_hex,
            "authorization": {
                "from": account.address,
                "to": req.pay_to,
                "value": req.amount,
                "validAfter": str(valid_after),
                "validBefore": str(valid_before),
                "nonce": nonce_hex,
            },
        },
    }
    if resource_obj is not None:
        payload["resource"] = resource_obj
    if extensions is not None:
        payload["extensions"] = extensions
    return payload


def encode_payment_header(payment: dict[str, Any]) -> str:
    """Base64-encode the signed payment payload for header transport."""
    return base64.b64encode(json.dumps(payment).encode("utf-8")).decode("ascii")


def _safe_json(r: requests.Response) -> Any:
    try:
        return r.json()
    except Exception:
        return {"error": r.text[:500]}


def call_with_payment(
    account: Account,
    api_base: str,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: Any = None,
    max_usdc_per_call: float = 0.25,
    timeout: float = 30.0,
    retry_timeout: float = 60.0,
) -> Any:
    """Execute an x402-paid request. Returns the parsed JSON response on success.

    Raises:
        HyperdPaymentRefused: if the server's 402 challenge requested more USDC
            than max_usdc_per_call permits.
        HyperdHttpError: if the server returns a non-2xx after the payment retry.
        HyperdError: for malformed challenges or signing errors.
    """
    url = f"{api_base.rstrip('/')}{path}"
    request_headers = {"Content-Type": "application/json"} if body is not None else {}
    body_payload = json.dumps(body) if body is not None else None

    first = requests.request(
        method, url, params=params, data=body_payload, headers=request_headers, timeout=timeout
    )
    if first.status_code in (200, 201):
        return first.json()
    if first.status_code != 402:
        raise HyperdHttpError(
            f"Server returned {first.status_code} on first request (expected 200 or 402).",
            first.status_code,
            _safe_json(first),
        )

    requirement, raw_requirement, resource_obj, extensions = parse_payment_required(
        {k.lower(): v for k, v in first.headers.items()}
    )

    # Enforce the per-call USDC cap BEFORE signing. Anything that signs
    # without checking the amount is a wallet-drain footgun — see the
    # security note in CHANGELOG.md and the same fix shipped in
    # @hyperd-ai/plugin-hyperd@0.1.1.
    max_atomic = int(max_usdc_per_call * 1_000_000)  # USDC has 6 decimals
    if int(requirement.amount) > max_atomic:
        usd = int(requirement.amount) / 1_000_000
        raise HyperdPaymentRefused(
            f"Server requested {requirement.amount} atomic units (~${usd:.4f} USDC), "
            f"but max_usdc_per_call is ${max_usdc_per_call:.4f}. Raise the cap or "
            f"refuse the call."
        )

    payment = sign_payment_authorization(
        account, requirement, raw_requirement, resource_obj, extensions
    )
    payment_header = encode_payment_header(payment)
    # Both header names are set for compatibility — PAYMENT-SIGNATURE is the v2
    # canonical, X-Payment is the @x402/express bridged alias.
    request_headers["PAYMENT-SIGNATURE"] = payment_header
    request_headers["X-Payment"] = payment_header

    second = requests.request(
        method, url, params=params, data=body_payload, headers=request_headers, timeout=retry_timeout
    )
    if second.status_code in (200, 201):
        return second.json()
    raise HyperdHttpError(
        f"Server returned {second.status_code} on payment retry. "
        f"Body: {_safe_json(second)}",
        second.status_code,
        _safe_json(second),
    )
