"""
BSC Liquidity Depth Analyzer — Skill #1 for the Marketplace.

Fetches a PancakeSwap V2 pair's on-chain reserves, computes depth curves
at various slippage points, concentration risk, and optimal trade size.

Usage (standalone test):
    python -c "from src.skills.liquidity_depth import analyze_pair; print(analyze_pair('0x...'))"
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from typing import Any

from web3 import Web3

logger = logging.getLogger(__name__)

# ── PancakeSwap V2 on BSC ──
PANCAKE_FACTORY_V2 = Web3.to_checksum_address("0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73")
PANCAKE_ROUTER_V2 = Web3.to_checksum_address("0x10ED43C718714eb63d5aA57B78B54704E256024E")
WBNB = Web3.to_checksum_address("0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")

# ── Minimal ABI for pair inspection ──
FACTORY_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"","type":"address"},{"internalType":"address","name":"","type":"address"}],"name":"getPair","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}]')
PAIR_ABI = json.loads('[{"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"reserve0","type":"uint112"},{"internalType":"uint112","name":"reserve1","type":"uint112"},{"internalType":"uint32","name":"blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"token0","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"token1","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"totalSupply","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]')
ERC20_ABI = json.loads('[{"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"}]')


def _get_web3() -> Web3:
    """Create a Web3 connection to BSC. Falls back to public RPC."""
    import os
    rpc = os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org/")
    return Web3(Web3.HTTPProvider(rpc))


@dataclass
class DepthAnalysis:
    pair_address: str
    token0: str
    token1: str
    token0_symbol: str
    token1_symbol: str
    reserve0: int
    reserve1: int
    price_token0_in_token1: float
    depth_pct_1: dict  # trade size $, price impact %
    depth_pct_5: dict
    depth_pct_10: dict
    optimal_trade_size_tokens: float
    concentration_note: str
    liquidity_usd_estimate: float


def _get_token_info(w3: Web3, address: str) -> tuple[str, int]:
    """Returns (symbol, decimals) for an ERC-20."""
    contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=ERC20_ABI)
    try:
        symbol = contract.functions.symbol().call()
    except Exception:
        symbol = "???"
    try:
        decimals = contract.functions.decimals().call()
    except Exception:
        decimals = 18
    return symbol, decimals


def analyze_pair(pair_address: str, rpc_url: str | None = None) -> dict[str, Any]:
    """Analyze a PancakeSwap V2 pair's liquidity depth.

    Args:
        pair_address: The pair contract address on BSC.
        rpc_url: Optional custom RPC URL.

    Returns:
        dict with depth analysis results, ready for ERC-8183 submission.
    """
    w3 = _get_web3() if rpc_url is None else Web3(Web3.HTTPProvider(rpc_url))
    pair = Web3.to_checksum_address(pair_address)
    pair_contract = w3.eth.contract(address=pair, abi=PAIR_ABI)

    # ── Get reserves ──
    reserve0, reserve1, _ = pair_contract.functions.getReserves().call()
    token0_addr = pair_contract.functions.token0().call()
    token1_addr = pair_contract.functions.token1().call()

    # ── Identify which is WBNB and which is the quote token ──
    sym0, dec0 = _get_token_info(w3, token0_addr)
    sym1, dec1 = _get_token_info(w3, token1_addr)

    # Normalise reserves to decimals
    r0_norm = reserve0 / (10 ** dec0)
    r1_norm = reserve1 / (10 ** dec1)

    # Price: how much token1 per token0 (for V2 constant product)
    if r0_norm > 0 and r1_norm > 0:
        price_t0_in_t1 = r1_norm / r0_norm  # 1 token0 = X token1
    else:
        price_t0_in_t1 = 0.0

    # ── Depth calculation using constant product formula ──
    # k = reserve0 * reserve1 (in raw units)
    # For a sell of dx token0: dx * k / (reserve0 - dx) - reserve1 = dy received
    # Price impact = (1 - (reserve0 / (reserve0 + dx))) * 100

    def _compute_depth_for_sell_pct(sell_pct: float) -> dict:
        """How much of token1 you'd get if you sold sell_pct% of reserve0."""
        dx_raw = int(reserve0 * sell_pct / 100)
        if dx_raw <= 0 or dx_raw >= reserve0:
            return {"trade_size_tokens": 0, "price_impact_pct": 100.0, "usd_value": 0}

        # dy = k / (reserve0 - dx) - reserve1  ... wait no
        # In constant product: x * y = k
        # After selling dx: y' = k / (x + dx)
        # dy = y - y' = y - k/(x+dx)
        # Actually for V2: you send dx, you receive dy where (x+dx)*(y-dy) = k
        # dy = y - k/(x+dx)
        new_reserve0 = reserve0 + dx_raw
        k = reserve0 * reserve1
        new_reserve1 = k // new_reserve0
        dy_raw = reserve1 - new_reserve1

        if dy_raw <= 0:
            return {"trade_size_tokens": 0, "price_impact_pct": 100.0, "usd_value": 0}

        # Compute the effective price
        # Mid price before trade: reserve1 / reserve0
        # Effective price: dy / dx
        mid_price = reserve1 / reserve0
        effective_price = dy_raw / dx_raw
        price_impact_pct = (1 - effective_price / mid_price) * 100 if mid_price > 0 else 0

        # Estimate USD value of the trade (rough: using BNB ~$XXX)
        # We'll report it in token amounts; client can multiply by current price
        return {
            "trade_size_raw": dx_raw,
            "trade_size_token0": round(dx_raw / (10 ** dec0), 4),
            "trade_size_token1_received": round(dy_raw / (10 ** dec1), 4),
            "price_impact_pct": round(price_impact_pct, 4),
        }

    depth_1 = _compute_depth_for_sell_pct(1.0)
    depth_5 = _compute_depth_for_sell_pct(5.0)
    depth_10 = _compute_depth_for_sell_pct(10.0)

    # ── Optimal trade size: find the amount that causes < 2% price impact ──
    optimal_size = 0
    for pct in [x / 100 for x in range(1, 2000)]:  # 0.01% to 20%
        dx_raw = int(reserve0 * pct / 100)
        if dx_raw <= 0:
            continue
        k = reserve0 * reserve1
        new_reserve1 = k // (reserve0 + dx_raw)
        dy_raw = reserve1 - new_reserve1
        if dy_raw <= 0:
            continue
        mid_price = reserve1 / reserve0
        effective_price = dy_raw / dx_raw
        impact = (1 - effective_price / mid_price) * 100 if mid_price > 0 else 0
        if impact < 2.0:
            optimal_size = dx_raw
        else:
            break

    # ── Concentration risk (rough: check totalSupply vs reserves magnitude) ──
    try:
        total_supply = pair_contract.functions.totalSupply().call()
        # If totalSupply is very low relative to reserves, it might be a
        # deprecated/abandoned pool
        concentration_note = "normal"
        if total_supply < 100_000:  # Very low LP supply
            concentration_note = "high — LP token supply is very low, suggesting few LPs"
    except Exception:
        concentration_note = "unknown"

    # ── USD liquidity estimate (crude: assume mid-price * reserve) ──
    # If token1 is WBNB, use a fixed BNB price
    bnb_price_usd = 580  # rough BNB price fallback
    if token0_addr == WBNB or token1_addr == WBNB:
        if token1_addr == WBNB:
            # token1 is WBNB, so we know the USD value of the WBNB reserve
            liquidity_est = round((r1_norm * bnb_price_usd) * 2, 2)  # *2 for both sides
        else:
            liquidity_est = round((r0_norm * bnb_price_usd) * 2, 2)
    else:
        liquidity_est = round((r0_norm + r1_norm) * 0.1, 2)  # wild guess for non-BNB pairs

    result = asdict(DepthAnalysis(
        pair_address=pair_address,
        token0=token0_addr,
        token1=token1_addr,
        token0_symbol=sym0,
        token1_symbol=sym1,
        reserve0=reserve0,
        reserve1=reserve1,
        price_token0_in_token1=round(price_t0_in_t1, 8),
        depth_pct_1=depth_1,
        depth_pct_5=depth_5,
        depth_pct_10=depth_10,
        optimal_trade_size_tokens=round(optimal_size / (10 ** dec0), 4),
        concentration_note=concentration_note,
        liquidity_usd_estimate=liquidity_est,
    ))

    logger.info(
        "Depth analysis: %s | price=%.6f %s/%s | depth_1=%.2f%% impact",
        pair_address, price_t0_in_t1, sym0, sym1,
        depth_1.get("price_impact_pct", 0),
    )
    return result


def analyze_pair_handler(job_description: str) -> tuple[str, dict]:
    """ERC-8183 task handler for the depth analysis skill.

    Args:
        job_description: JSON string with {"pair": "0x...", "rpc_url": "..."}

    Returns:
        (result_string, metadata_dict) suitable for ERC-8183 submit_result.
    """
    import json
    try:
        params = json.loads(job_description)
    except (json.JSONDecodeError, TypeError):
        params = {"pair": job_description.strip()}

    pair = params.get("pair", "").strip()
    if not pair or not pair.startswith("0x"):
        return json.dumps({"error": "Missing or invalid 'pair' address"}), {"skill": "liquidity-depth", "status": "error"}

    try:
        result = analyze_pair(pair, rpc_url=params.get("rpc_url"))
        return json.dumps(result, indent=2), {
            "skill": "liquidity-depth",
            "pair": pair,
            "status": "ok",
        }
    except Exception as e:
        logger.exception("Depth analysis failed for %s", pair)
        return json.dumps({"error": str(e)}), {"skill": "liquidity-depth", "status": "error"}
