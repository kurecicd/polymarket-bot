#!/usr/bin/env python3
"""
Thin wrappers around Polymarket's REST APIs and The Graph subgraph.
Authentication uses py-clob-client (EIP-712 signing via Ethereum private key).
"""
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, PartialCreateOrderOptions

CLOB_BASE = "https://clob.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"
SUBGRAPH_URL = "https://api.thegraph.com/subgraphs/name/polymarket/polymarket-orderbook-v2"

# Polygon USDC contract — used to classify BUY vs SELL in subgraph events
USDC_ADDRESS = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "polymarket-whale-bot/1.0"


def _get(url: str, params: dict | None = None, retries: int = 2) -> Any:
    for attempt in range(retries):
        try:
            resp = _SESSION.get(url, params=params, timeout=8)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"GET {url} failed: {exc}") from exc
            time.sleep(1)


def _post_json(url: str, payload: dict, retries: int = 2) -> Any:
    for attempt in range(retries):
        try:
            resp = _SESSION.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"POST {url} failed: {exc}") from exc
            time.sleep(1)


class PolymarketClient:
    def __init__(self, private_key: str, chain_id: int = 137):
        self._private_key = private_key
        self._chain_id = chain_id
        self._clob = ClobClient(
            host=CLOB_BASE,
            chain_id=chain_id,
            key=private_key,
        )
        self.address: str = self._clob.get_address()

    # ── Auth ──────────────────────────────────────────────────────────────────

    def derive_api_key(self) -> dict[str, str]:
        """Call once, store returned key/secret/passphrase in .env."""
        resp = self._clob.derive_api_key()
        return {
            "api_key": resp.api_key,
            "api_secret": resp.api_secret,
            "api_passphrase": resp.api_passphrase,
        }

    def set_api_credentials(self, api_key: str, api_secret: str, api_passphrase: str) -> None:
        from py_clob_client.clob_types import ApiCreds
        self._clob.set_api_creds(ApiCreds(
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
        ))

    # ── Account ───────────────────────────────────────────────────────────────

    def get_usdc_balance(self) -> float:
        """Returns USDC balance available for trading (in USD, not wei)."""
        try:
            from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
            data = self._clob.get_balance_allowance(
                params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )
        except (ImportError, TypeError):
            # Fallback for different py_clob_client versions
            data = self._clob.get_balance_allowance()
        return float(data.get("balance", 0)) / 1e6

    # ── Market data ───────────────────────────────────────────────────────────

    def get_market(self, condition_id: str) -> dict[str, Any]:
        """Full market info from CLOB including tokens, liquidity, end_date_iso."""
        return _get(f"{CLOB_BASE}/markets/{condition_id}")

    def get_book(self, token_id: str) -> dict[str, Any]:
        """Order book for a token (bids/asks with price + size)."""
        return _get(f"{CLOB_BASE}/book", params={"token_id": token_id})

    def get_last_trade_price(self, token_id: str) -> float:
        data = _get(f"{CLOB_BASE}/last-trade-price", params={"token_id": token_id})
        return float(data.get("price", 0))

    def get_markets_gamma(
        self,
        limit: int = 500,
        offset: int = 0,
        min_liquidity: float = 10_000,
    ) -> list[dict[str, Any]]:
        """Fetch active markets from Gamma API filtered by minimum liquidity."""
        return _get(
            f"{GAMMA_BASE}/markets",
            params={
                "limit": limit,
                "offset": offset,
                "liquidity_min": int(min_liquidity),
                "active": "true",
                "closed": "false",
            },
        ) or []

    def get_market_gamma(self, condition_id: str) -> dict[str, Any]:
        results = _get(f"{GAMMA_BASE}/markets", params={"condition_ids": condition_id}) or []
        return results[0] if results else {}

    # ── Wallet trade history ──────────────────────────────────────────────────

    def get_trades(
        self,
        maker_address: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> list[dict[str, Any]]:
        """Recent trades for a wallet via public data-api (no auth needed)."""
        # data-api is public and works for any wallet address
        data = _get("https://data-api.polymarket.com/trades",
                    params={"user": maker_address, "limit": limit})
        if not isinstance(data, list):
            return []
        # Normalize to the field names monitor.py expects
        result = []
        for t in data:
            result.append({
                "id": t.get("transactionHash", "") + t.get("asset", ""),
                "side": t.get("side", ""),
                "asset_id": t.get("asset", ""),
                "market": t.get("conditionId", ""),
                "price": str(t.get("price", 0)),
                "size": str(t.get("size", 0)),
                "timestamp": str(t.get("timestamp", 0)),
                "title": t.get("title", ""),
            })
        return result

    # ── Subgraph (bulk historical) ────────────────────────────────────────────

    def query_subgraph(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        return _post_json(SUBGRAPH_URL, {"query": query, "variables": variables})

    def fetch_trades_batch(self, min_block: int, batch_size: int = 1000) -> list[dict[str, Any]]:
        """Fetch one page of OrderFilledEvents from the subgraph."""
        query = """
        query FetchTrades($first: Int!, $minBlock: Int!) {
          orderFilledEvents(
            first: $first
            orderBy: blockNumber
            orderDirection: asc
            where: { blockNumber_gte: $minBlock }
          ) {
            id
            timestamp
            blockNumber
            maker
            taker
            makerAssetId
            takerAssetId
            makerAmountFilled
            takerAmountFilled
            market {
              id
              conditionId
              question
              endTimestamp
            }
          }
        }
        """
        result = self.query_subgraph(query, {"first": batch_size, "minBlock": min_block})
        return (result.get("data") or {}).get("orderFilledEvents", [])

    # ── Orders ────────────────────────────────────────────────────────────────

    def get_open_orders(self) -> list[dict[str, Any]]:
        return self._clob.get_orders(maker_address=self.address) or []

    def place_limit_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size_usdc: float,
    ) -> dict[str, Any]:
        """
        Place a limit order.
        side: "BUY" or "SELL"
        price: 0-1 (cents per share)
        size_usdc: USD notional to spend (BUY) or shares * price (SELL)
        Returns the order response dict.
        """
        size_shares = round(size_usdc / price, 4) if side == "BUY" else size_usdc

        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size_shares,
            side=side,
        )
        signed_order = self._clob.create_order(order_args)
        resp = self._clob.post_order(signed_order, OrderType.GTC)
        return resp if isinstance(resp, dict) else {"order_id": str(resp)}

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._clob.cancel(order_id=order_id) or {}

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def classify_subgraph_trade(row: dict[str, Any]) -> tuple[str, str, float, float]:
        """
        Returns (side, token_id, price, size_shares) from a raw subgraph event.
        BUY  = maker spent USDC to receive outcome token
        SELL = maker gave outcome token to receive USDC
        """
        maker_asset = (row.get("makerAssetId") or "").lower()
        if maker_asset == USDC_ADDRESS.lower():
            usdc_amount = int(row["makerAmountFilled"]) / 1e6
            shares = int(row["takerAmountFilled"]) / 1e6
            token_id = row["takerAssetId"]
            side = "BUY"
        else:
            shares = int(row["makerAmountFilled"]) / 1e6
            usdc_amount = int(row["takerAmountFilled"]) / 1e6
            token_id = row["makerAssetId"]
            side = "SELL"
        price = usdc_amount / shares if shares > 0 else 0.0
        return side, token_id, price, float(shares)

    @staticmethod
    def hours_until_end(end_date_iso: str) -> float:
        end_dt = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
        # Make offset-naive datetimes UTC-aware
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        return (end_dt - datetime.now(timezone.utc)).total_seconds() / 3600
