"""
EIP-712 order signing for Polymarket CLOB.
Chain ID: 137 (Polygon Mainnet)
Domain: ClobAuthDomain v1
Skeleton — disabled in v1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CHAIN_ID = 137
DOMAIN_NAME = "ClobAuthDomain"
DOMAIN_VERSION = "1"


@dataclass
class EIP712Domain:
    name: str = DOMAIN_NAME
    version: str = DOMAIN_VERSION
    chain_id: int = CHAIN_ID


@dataclass
class OrderMessage:
    market_id: str
    side: str          # 'BUY' | 'SELL'
    token_id: str
    price: int         # scaled integer (e.g. 0.65 → 65000000)
    size: int          # scaled integer
    nonce: int
    fee_rate_bps: int = 0
    taker_amount: int = 0
    maker_amount: int = 0


class EIP712Signer:
    """Signs Polymarket orders using EIP-712 structured data."""

    ORDER_TYPE = [
        {"name": "market", "type": "address"},
        {"name": "side", "type": "uint8"},
        {"name": "tokenId", "type": "uint256"},
        {"name": "price", "type": "uint256"},
        {"name": "size", "type": "uint256"},
        {"name": "nonce", "type": "uint256"},
        {"name": "feeRateBps", "type": "uint256"},
        {"name": "takerAmount", "type": "uint256"},
        {"name": "makerAmount", "type": "uint256"},
    ]

    def __init__(self, wallet: Any) -> None:
        self.wallet = wallet
        self.domain = EIP712Domain()

    def sign_order(self, order: OrderMessage) -> str:
        """Return hex signature for a CLOB order. Requires loaded wallet."""
        if not self.wallet.is_loaded:
            raise RuntimeError("EIP-712 signing requires a loaded wallet (live mode only)")
        try:
            from eth_account.structured_data.hashing import hash_message  # type: ignore
            from eth_account import Account  # type: ignore
        except ImportError as e:
            raise RuntimeError(f"eth_account not available: {e}") from e

        structured = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                ],
                "Order": self.ORDER_TYPE,
            },
            "domain": {
                "name": self.domain.name,
                "version": self.domain.version,
                "chainId": self.domain.chain_id,
            },
            "primaryType": "Order",
            "message": {
                "market": order.market_id,
                "side": 0 if order.side == "BUY" else 1,
                "tokenId": order.token_id,
                "price": order.price,
                "size": order.size,
                "nonce": order.nonce,
                "feeRateBps": order.fee_rate_bps,
                "takerAmount": order.taker_amount,
                "makerAmount": order.maker_amount,
            },
        }
        msg_hash = hash_message(structured)
        return self.wallet.sign_message(msg_hash)
