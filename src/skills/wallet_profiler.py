"""
Wallet Profiler — Skill #3 for the Marketplace.

Given a wallet address on BSC, returns a comprehensive profile:

  - BNB balance + estimated USD value
  - Major token holdings (balanceOf on ~40 top BSC tokens)
  - Estimated net worth from detected holdings
  - Account metadata (EOA vs contract, nonce/tx count proxy)
  - DeFi protocol footprint (which known protocols used)
  - PancakeSwap LP positions
  - Behavioral classification (Whale / Trader / Bot / Degen / Newbie)
  - Risk indicators

Input:
    {"address": "0x...", "rpc_url": "..."}

Output:
    Full wallet profile as JSON.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any

from web3 import Web3

logger = logging.getLogger(__name__)

# ── BSC RPC ──
BSC_RPC = "https://bsc-dataseed.binance.org/"

# ── Known major tokens on BSC (address → symbol, decimals) ──
# These are the most commonly held / traded tokens. We check balanceOf
# on each to build a picture of the wallet's holdings.
MAJOR_TOKENS: dict[str, tuple[str, int]] = {
    "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c": ("WBNB", 18),
    "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82": ("CAKE", 18),
    "0x55d398326f99059fF775485246999027B3197955": ("USDT", 18),
    "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d": ("USDC", 18),
    "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56": ("BUSD", 18),
    "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c": ("BTCB", 18),
    "0x2170Ed0880ac9A755fd29B2688956BD959F933F8": ("ETH", 18),
    "0x1D2F0da169ceB9fC7B3144628dB156f3F6c60dBE": ("XRP", 18),
    "0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47": ("ADA", 18),
    "0x7083609fCE4d1d8Dc0C979AAb8c869Ea2C873402": ("DOT", 18),
    "0x570A5D26f7765Ecb712C0924E4De545B89fD43dF": ("SOL", 18),
    "0xba2aE424d960c26247Dd6c32edC70B295c744C43": ("DOGE", 18),
    "0xCC42724C6683B7E57334c4E856f4c9965ED682bD": ("MATIC", 18),
    "0x1CE0c2827e2eF14D5C4f29a091d735A204794041": ("AVAX", 18),
    "0xBf5140A22578168FD562DCcF235E5D43A02ce9B1": ("UNI", 18),
    "0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD": ("LINK", 18),
    "0x4B0F1812e5Df2A09796481Ff14017e600dA56550": ("TWT", 18),
    "0x111111111117dC0aa78b770fA6A738034120C302": ("1INCH", 18),
    "0x0D8Ce2A99Bb6e3B7Db580eD848240e4a0F78aEfD": ("FIL", 18),
    "0x4338665CBB7B2485A8855A139b75D5e34AB0DB94": ("LTC", 18),
    "0x250632378E573c6Be1AC2f97Fcdf00515d0Aa91B": ("BETH", 18),
    "0x2B90Bf2c58e0cC35b7cbE5c126bC162503a89F59": ("APT", 18),
    "0xa2E3356610840271A5618Bc545F6E6bfb9dC92cA": ("ARB", 18),
    "0x965F527D9159dCe6288a2219DB51fc6Eef120dD1": ("BSW", 18),
    "0x603c7f932ED1fc6575303D8Fb018fDCBb0f39a95": ("BANANA", 18),
    "0x947950BcC74888a40Ffa2593C5798F11Fc9124C4": ("SUSHI", 18),
    "0x2b3C34dC6800C49b6Af8Fd5F2905122F34271cEE": ("ACH", 18),
    "0xa184088a740c695E156F91f5cC086a06bb78b827": ("AUTO", 18),
    "0x6fd7c98458a943f469E1Cf4eA85B173f5Cd342F4": ("BHC", 8),
    "0x4BA0057f784858a48fe351445C672FF2a3d43515": ("KALM", 18),
    "0xAD6cAEb32CD2c308980a548bD0Bc5AA4306c6c18": ("BAND", 18),
    "0xF9CeC8d50f6c8ad3Fb6dcCEC577e05aA32B224FE": ("CHR", 18),
    "0x715D400F88C167884bbCc41C5FeA407ed4D2f8A0": ("AXS", 18),
    "0x3B78458981eB7260d1f781cb8be2CaAC7027DbE2": ("TLM", 4),
    "0x16939ef78624453A6243E8bD9708f8b5ca7f30bC": ("BNX", 18),
    "0x12f31B73D812C6Bb0d735a218c086d44D5fe5f89": ("ACE", 18),
}

# ── Known DeFi protocols on BSC ──
PROTOCOLS: dict[str, tuple[str, str]] = {
    "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73": ("PancakeSwap", "Factory V2"),
    "0x10ED43C718714eb63d5aA57B78B54704E256024E": ("PancakeSwap", "Router V2"),
    "0x1b96B92314C44b159149f7E030351784fB95444a": ("PancakeSwap", "Factory V3"),
    "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4": ("PancakeSwap", "Router V3"),
    "0xfD5840Cd36d94D7229439859C0112a4185BC0255": ("Venus", "Comptroller"),
    "0x95c78222B3D6e262426483D42CfA53685A67Ab9D": ("Venus", "VBNB"),
    "0x0b53E608bD058Bb54748C35148484fD627E6dc0A": ("PancakeSwap", "MasterChef V2"),
    "0x73feaa1eE314F8c655E354234017bE2193C9E24E": ("PancakeSwap", "MasterChef V3"),
    "0x05498574BD0Fa99eeCB01e1241661E7eE58F8a85": ("Radiant", "Lending"),
    "0x8CA9B5E11D1CB7B3E9Efc2F2ba94F9Fa92ddDee3": ("Ethereum", "BSC Bridge"),
    "0x3a6d8cA21D1CF76F653A67577FA0D274Bd50c067": ("Binance", "Staking"),
    "0x8894E0a0c962CB723c1976a4421c95949bE2D4E3": ("PancakeSwap", "Auto CAKE"),
    "0xa5f8C5Dbd5F286960b9d90548680aE5ebFf07652": ("PancakeSwap", "Syrup Pool"),
    "0x45f54279208f2c25c1f7e6cD5E026d9C8B0e7B69": ("Alpaca", "Lending"),
    "0x158Da805682BdC8bB32C6C68E4A0877d9f4f05D0": ("Biswap", "Router"),
    "0x2cA3a3a4Ff4137bE9b5C81B6Ca6f5E6Ac5Ef96b6": ("BabySwap", "Router"),
    "0xD4aB6384641F1717116388501836607985E58455": ("Wombat", "Exchange"),
    "0x4693bB151151CceDeA6CdFb2A1dCB1B92f779b4f": ("Thena", "Router"),
    "0x091d9F2d2E40b8C2eE0eB44AE2cE1336D48BBAD8": ("Stargate", "Bridge"),
    "0xB0D502E938ed5f4df2E681fE6E419ff29631d62b": ("Alpaca", "Vault"),
}

# ── PancakeSwap V2 known pair addresses (top pairs to check for LP) ──
# We'll also check the factory to find any pair involving this wallet.
PANCAKE_FACTORY_V2 = Web3.to_checksum_address("0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73")
WBNB = Web3.to_checksum_address("0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")

# ── Minimal ABIs ──
ERC20_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"}]')
FACTORY_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"","type":"address"},{"internalType":"address","name":"","type":"address"}],"name":"getPair","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}]')
PAIR_ABI = json.loads('[{"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"reserve0","type":"uint112"},{"internalType":"uint112","name":"reserve1","type":"uint112"},{"internalType":"uint32","name":"blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"token0","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"token1","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]')

BNB_PRICE_USD = 580  # rough fallback; updated estimate


# ── Data Model ──

@dataclass
class TokenHolding:
    symbol: str
    address: str
    balance_raw: int
    balance_formatted: float
    usd_value_estimate: float
    is_flagged: bool = False
    flag_reason: str = ""


@dataclass
class ProtocolFootprint:
    name: str
    product: str
    address: str
    interaction_type: str  # "has_balance", "likely_used"


@dataclass
class LPPosition:
    pair_address: str
    token0_symbol: str
    token1_symbol: str
    lp_balance: float
    share_of_pool_pct: float
    estimated_usd: float


@dataclass
class WalletProfile:
    address: str
    is_contract: bool
    contract_name: str | None
    bnb_balance: float
    bnb_usd_value: float
    nonce: int  # proxy for transaction count

    # Holdings
    token_count: int
    tokens_held: list[TokenHolding]
    top_holdings: list[dict]  # top 5 by value
    estimated_net_worth_usd: float

    # Protocol usage
    protocols_used: list[ProtocolFootprint]

    # LP positions
    lp_positions: list[LPPosition]

    # Profile
    classification: str  # Whale / Trader / Bot / Degen / Newbie / Unknown
    classification_reasons: list[str]
    risk_flags: list[str]
    risk_score: int  # 0-100

    # Metadata
    scanned_tokens: int
    scan_time_ms: float


# ── Helper Functions ──

def _get_web3() -> Web3:
    import os
    rpc = os.getenv("BSC_RPC_URL", BSC_RPC)
    return Web3(Web3.HTTPProvider(rpc))


def _checksum(addr: str) -> str:
    """Safely checksum an address, returning lowercase if it fails."""
    try:
        return Web3.to_checksum_address(addr)
    except (ValueError, TypeError):
        return addr.lower()


def _fetch_bnb_price() -> float:
    """Get a rough BNB/USD price estimate. Returns cached/mocked for now."""
    # Could add a real oracle lookup here in production
    return BNB_PRICE_USD


def _get_token_price_usd(symbol: str) -> float:
    """Rough USD price estimates for known tokens (static lookup for MVP)."""
    prices = {
        "WBNB": BNB_PRICE_USD,
        "BNB": BNB_PRICE_USD,
        "CAKE": 2.15,
        "USDT": 1.00,
        "USDC": 1.00,
        "BUSD": 1.00,
        "BTCB": 67500,
        "ETH": 3450,
        "XRP": 0.52,
        "ADA": 0.38,
        "DOT": 5.20,
        "SOL": 145,
        "DOGE": 0.12,
        "MATIC": 0.52,
        "AVAX": 25.50,
        "UNI": 7.80,
        "LINK": 14.20,
        "TWT": 1.05,
        "1INCH": 0.38,
        "FIL": 4.20,
        "LTC": 72.00,
        "BETH": 3450,
        "APT": 8.50,
        "ARB": 0.72,
        "BSW": 0.15,
        "BANANA": 1.20,
        "SUSHI": 0.65,
        "ACH": 0.028,
        "AUTO": 12.00,
        "BHC": 0.85,
        "KALM": 0.018,
        "BAND": 1.20,
        "CHR": 0.22,
        "AXS": 6.50,
        "TLM": 0.012,
        "BNX": 1.80,
        "ACE": 3.40,
    }
    return prices.get(symbol, 0.0)


def _classify_wallet(
    bnb_usd: float,
    token_holdings: list[TokenHolding],
    nonce: int,
    is_contract: bool,
    lp_positions: list,
    protocol_count: int,
    flagged_token_count: int,
) -> tuple[str, list[str], list[str], int]:
    """Classify a wallet based on its profile.

    Uses a priority system: once a high-specificity classification is set,
    lower-priority checks only overwrite if the current value is less specific.
    Priority (highest first): Contract > Whale > Flagged/Degen > Bot > Trader > LP > Newbie > Default
    """
    total_value = bnb_usd + sum(t.usd_value_estimate for t in token_holdings)
    total_value += sum(lp.estimated_usd for lp in lp_positions)

    def _set_classification(cls: str, *new_reasons: str):
        nonlocal classification
        """Only overwrite classification if the new one has higher priority.
        Priority list: Bot/Contract (10) > Degen / High Risk (9) > Whale (8) > Pro Trader (7) >
                        Bot (6) > Active Trader (5) > Degen (4) > LP Provider (3) > Newbie (2) > default
        """
        priority = {
            "Bot/Contract": 10,
            "Degen / High Risk": 9,
            "Whale": 8,
            "Pro Trader": 7,
            "Bot": 6,
            "Active Trader": 5,
            "Degen": 4,
            "LP Provider": 3,
            "Newbie": 2,
        }
        new_p = priority.get(cls, 0)
        old_p = priority.get(classification, 0)
        if new_p >= old_p:
            classification = cls
        for r in new_reasons:
            reasons.append(r)

    classification = "Unknown"
    reasons: list[str] = []
    risk_flags: list[str] = []

    # Net worth tiers
    if total_value > 100_000:
        reasons.append(f"Estimated net worth ${total_value:,.0f} — significant holdings")
    elif total_value > 10_000:
        reasons.append(f"Estimated net worth ${total_value:,.0f} — moderate holdings")

    # ── Bot/Contract (highest priority) ──
    if is_contract:
        _set_classification("Bot/Contract", "Wallet is a smart contract")

    # ── Whale ──
    if total_value > 500_000:
        _set_classification("Whale", "Holdings exceed $500k")
    elif total_value > 100_000 and nonce < 1000:
        _set_classification("Whale", "Holdings exceed $100k with moderate activity")

    # ── Flagged tokens → Degen / High Risk ──
    if flagged_token_count > 2:
        _set_classification("Degen / High Risk",
                            f"Multiple flagged/suspicious tokens held ({flagged_token_count})")
        risk_flags.append("Portfolio contains multiple suspicious tokens")

    # ── Bot (high nonce, low value) ──
    if nonce > 5000 and total_value < 5000:
        _set_classification("Bot",
                            f"High transaction count ({nonce}) with low balance — automated activity")

    # ── Active / Pro Trader ──
    if nonce > 2000:
        if total_value > 50_000:
            _set_classification("Pro Trader", "High value + high activity")
        else:
            _set_classification("Active Trader",
                                f"High transaction count ({nonce}) — frequent trading activity")

    # ── Degen (many small-cap tokens, low total value) ──
    if len(token_holdings) > 10 and total_value < 5000:
        _set_classification("Degen",
                            f"Holds {len(token_holdings)} tokens with low total value — diversified small-cap gambling")

    # ── LP Provider ──
    if lp_positions:
        lp_value = sum(lp.estimated_usd for lp in lp_positions)
        reasons.append(f"LP provider in {len(lp_positions)} pool(s) worth ~${lp_value:,.0f}")
        if classification in ("Unknown", "Newbie"):
            classification = "LP Provider"

    # ── Newbie (lowest specific classification) ──
    if nonce < 10 and total_value < 1000:
        _set_classification("Newbie",
                            f"Low activity ({nonce} txns) and small balance — likely new wallet")
    elif nonce < 50 and total_value < 100:
        _set_classification("Newbie",
                            "Very low activity and near-zero balance")

    # ── Protocol usage info (supplemental, not classification-defining) ──
    if protocol_count > 3:
        reasons.append(f"Used {protocol_count} different DeFi protocols")

    # ── Risk flags ──
    if total_value > 100_000 and nonce < 5:
        risk_flags.append("High value but near-zero activity — possible cold wallet or dormant whale")
    if is_contract:
        risk_flags.append("Address is a contract, not an EOA — might be a router, aggregator, or malicious contract")

    # ── Fallback ──
    if classification == "Unknown":
        if total_value > 1000:
            classification = "Regular User"
            reasons.append(f"Typical retail wallet with ${total_value:,.0f} in assets")
        elif total_value > 0:
            classification = "Small Wallet"
            reasons.append(f"Small balance (${total_value:,.0f})")
        else:
            classification = "Empty / Inactive"
            reasons.append("No detectable BNB or token balances")

    # Overall risk score based on flags
    risk_score = len(risk_flags) * 15
    risk_score = min(risk_score, 100)

    return classification, reasons, risk_flags, risk_score


# ── Main Profiler Function ──

def profile_wallet(address: str, rpc_url: str | None = None) -> dict[str, Any]:
    """Build a comprehensive profile of a BSC wallet address.

    Args:
        address: Wallet address to profile.
        rpc_url: Optional custom RPC URL.

    Returns:
        dict with full wallet profile.
    """
    import time
    start = time.time()

    w3 = _get_web3() if rpc_url is None else Web3(Web3.HTTPProvider(rpc_url))
    addr = _checksum(address)
    bnb_price = _fetch_bnb_price()

    # ── 1. Basic metadata ──
    is_contract = False
    contract_name = None
    try:
        code = w3.eth.get_code(addr)
        is_contract = code.hex() != "0x"
        if is_contract:
            # Try to get a name
            try:
                name_contract = w3.eth.contract(address=addr, abi=ERC20_ABI)
                contract_name = name_contract.functions.name().call()
            except Exception:
                contract_name = "Unknown Contract"
    except Exception:
        pass

    try:
        bnb_wei = w3.eth.get_balance(addr)
        bnb_balance = bnb_wei / 1e18
    except Exception:
        bnb_balance = 0.0

    try:
        nonce = w3.eth.get_transaction_count(addr)
    except Exception:
        nonce = 0

    bnb_usd = bnb_balance * bnb_price

    # ── 2. Token holdings (check against major tokens list) ──
    tokens_held: list[TokenHolding] = []
    flagged_tokens: set[str] = set()

    for token_addr, (symbol, decimals) in MAJOR_TOKENS.items():
        try:
            contract = w3.eth.contract(address=_checksum(token_addr), abi=ERC20_ABI)
            balance = contract.functions.balanceOf(addr).call()
            if balance > 0:
                formatted = balance / (10 ** decimals)
                price = _get_token_price_usd(symbol)
                usd_value = formatted * price

                # Flag suspicious tokens (dust or scam tokens)
                is_flagged = False
                flag_reason = ""
                if symbol in ("BHC", "KALM", "TLM"):
                    # Small-cap / higher risk tokens
                    if formatted > 0 and usd_value < 0.50:
                        is_flagged = True
                        flag_reason = "Low-value small-cap token"
                        flagged_tokens.add(symbol)

                tokens_held.append(TokenHolding(
                    symbol=symbol,
                    address=token_addr,
                    balance_raw=balance,
                    balance_formatted=round(formatted, 6),
                    usd_value_estimate=round(usd_value, 2),
                    is_flagged=is_flagged,
                    flag_reason=flag_reason,
                ))
        except Exception:
            # Token contract might not exist at this address or RPC error — skip silently
            continue

    # Sort by USD value descending
    tokens_held.sort(key=lambda t: t.usd_value_estimate, reverse=True)

    # Top 5
    top_holdings = [
        {
            "symbol": t.symbol,
            "balance": t.balance_formatted,
            "usd_value": t.usd_value_estimate,
        }
        for t in tokens_held[:5]
    ]

    # ── 3. Protocol footprint ──
    protocols_used: list[ProtocolFootprint] = []
    for proto_addr, (name, product) in PROTOCOLS.items():
        try:
            p_addr = _checksum(proto_addr)
            # Check if wallet has a balance at this contract (LP tokens, deposits, etc.)
            contract = w3.eth.contract(address=p_addr, abi=ERC20_ABI)
            try:
                balance = contract.functions.balanceOf(addr).call()
                if balance > 0:
                    protocols_used.append(ProtocolFootprint(
                        name=name,
                        product=product,
                        address=proto_addr,
                        interaction_type="has_balance" if balance > 0 else "likely_used",
                    ))
                    continue
            except Exception:
                pass

            # Also check if this wallet is a known protocol address itself
            if addr.lower() == proto_addr.lower():
                protocols_used.append(ProtocolFootprint(
                    name=name,
                    product=product,
                    address=proto_addr,
                    interaction_type="is_protocol",
                ))
        except Exception:
            continue

    # ── 4. LP position detection ──
    lp_positions: list[LPPosition] = []

    # For each major token we found the wallet holds, check if there's a
    # PancakeSwap V2 pair and if this wallet has LP tokens in it
    for holding in tokens_held:
        try:
            factory = w3.eth.contract(address=PANCAKE_FACTORY_V2, abi=FACTORY_ABI)
            pair_addr = factory.functions.getPair(
                _checksum(holding.address),
                WBNB,
            ).call()
            if pair_addr and pair_addr != "0x0000000000000000000000000000000000000000":
                pair_addr_checksummed = _checksum(pair_addr)
                pair_contract = w3.eth.contract(address=pair_addr_checksummed, abi=PAIR_ABI)

                # Check if this wallet has LP tokens
                try:
                    lp_balance = pair_contract.functions.balanceOf(addr).call()
                    if lp_balance > 0:
                        # Get pair info
                        token0 = pair_contract.functions.token0().call()
                        token1 = pair_contract.functions.token1().call()
                        t0_sym, _ = MAJOR_TOKENS.get(token0.lower(), ("???", 18))
                        t1_sym, _ = MAJOR_TOKENS.get(token1.lower(), ("???", 18))
                        pair_total = pair_contract.functions.totalSupply().call()
                        share_pct = (lp_balance / pair_total * 100) if pair_total > 0 else 0

                        # Estimate USD value of LP position
                        reserves = pair_contract.functions.getReserves().call()
                        reserve0, reserve1 = reserves[0], reserves[1]
                        if pair_total > 0:
                            # LP's share of the pool
                            lp_share = lp_balance / pair_total
                            lp_share_usd = lp_share * (
                                (reserve0 / 1e18) * bnb_price +
                                (reserve1 / 1e18) * bnb_price
                            )
                        else:
                            lp_share_usd = 0

                        lp_positions.append(LPPosition(
                            pair_address=pair_addr,
                            token0_symbol=t0_sym,
                            token1_symbol=t1_sym,
                            lp_balance=lp_balance / 1e18,
                            share_of_pool_pct=round(share_pct, 4),
                            estimated_usd=round(lp_share_usd, 2),
                        ))
                except Exception:
                    continue
        except Exception:
            continue

    # ── 5. Classification ──
    classification, reasons, risk_flags, risk_score = _classify_wallet(
        bnb_usd=bnb_usd,
        token_holdings=tokens_held,
        nonce=nonce,
        is_contract=is_contract,
        lp_positions=lp_positions,
        protocol_count=len(protocols_used),
        flagged_token_count=len(flagged_tokens),
    )

    # ── 6. Net worth calculation ──
    token_value = sum(t.usd_value_estimate for t in tokens_held)
    lp_value = sum(lp.estimated_usd for lp in lp_positions)
    estimated_net_worth = bnb_usd + token_value + lp_value

    elapsed_ms = round((time.time() - start) * 1000, 1)

    profile = WalletProfile(
        address=address,
        is_contract=is_contract,
        contract_name=contract_name,
        bnb_balance=round(bnb_balance, 6),
        bnb_usd_value=round(bnb_usd, 2),
        nonce=nonce,
        token_count=len(tokens_held),
        tokens_held=tokens_held,
        top_holdings=top_holdings,
        estimated_net_worth_usd=round(estimated_net_worth, 2),
        protocols_used=protocols_used,
        lp_positions=lp_positions,
        classification=classification,
        classification_reasons=reasons,
        risk_flags=risk_flags,
        risk_score=risk_score,
        scanned_tokens=len(MAJOR_TOKENS),
        scan_time_ms=elapsed_ms,
    )

    result = asdict(profile)
    # Strip verbose raw data from the output for readability
    logger.info(
        "Wallet profiled: %s | %s | net worth $%.2f | %d tokens in %.0fms",
        address, classification, estimated_net_worth, len(tokens_held), elapsed_ms,
    )
    return result


# ── ERC-8183 Handler ──

def wallet_profiler_handler(job_description: str) -> tuple[str, dict]:
    """ERC-8183 task handler for the wallet profiler skill.

    Args:
        job_description: JSON string with {"address": "0x...", "rpc_url": "..."}
                        or just a raw address string.

    Returns:
        (result_string, metadata_dict) suitable for ERC-8183 submit_result.
    """
    try:
        params = json.loads(job_description)
    except (json.JSONDecodeError, TypeError):
        params = {"address": job_description.strip()}

    address = params.get("address", "").strip()
    if not address or not address.startswith("0x"):
        return json.dumps({"error": "Missing or invalid 'address' — provide a BSC wallet address (0x...)"}), {
            "skill": "wallet-profiler", "status": "error"
        }

    try:
        result = profile_wallet(address, rpc_url=params.get("rpc_url"))
        return json.dumps(result, indent=2), {
            "skill": "wallet-profiler",
            "address": address,
            "classification": result.get("classification", "unknown"),
            "status": "ok",
        }
    except Exception as e:
        logger.exception("Wallet profile failed for %s", address)
        return json.dumps({"error": str(e)}), {"skill": "wallet-profiler", "status": "error"}
