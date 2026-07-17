"""
Wallet Profiler — Skill #3 for the Marketplace (v4 - Batched RPC).

Uses Multicall3 via manually crafted eth_call for speed.
"""

from __future__ import annotations
import json, logging, time
from dataclasses import dataclass, asdict
from typing import Any
from web3 import Web3

logger = logging.getLogger(__name__)

MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
BALANCE_OF_SELECTOR = "70a08231"  # balanceOf(address)

# ── Token prices (USD) ──
TOKEN_PRICES: dict[str, float] = {
    "WBNB": 580, "BNB": 580, "CAKE": 2.15,
    "USDT": 1.00, "USDC": 1.00, "BUSD": 1.00, "FDUSD": 1.00,
    "BTCB": 67500, "ETH": 3450,
    "XRP": 0.52, "ADA": 0.38, "DOT": 5.20, "SOL": 145,
    "DOGE": 0.12, "MATIC": 0.52, "AVAX": 25.50,
    "UNI": 7.80, "LINK": 14.20, "TWT": 1.05, "1INCH": 0.38,
    "FIL": 4.20, "LTC": 72.00, "BETH": 3450,
    "APT": 8.50, "ARB": 0.72, "BSW": 0.15,
    "BANANA": 1.20, "SUSHI": 0.65, "PENDLE": 4.50,
    "ALPACA": 0.35, "BIFI": 320, "WOO": 0.25,
    "XVS": 8.20, "FLOKI": 0.00018, "INJ": 22.50,
    "STG": 0.55, "SFP": 0.45, "ACE": 3.40,
    "SHIB": 0.000023, "PEPE": 0.000012, "OP": 2.10,
    "ARB": 0.72, "APE": 1.20, "GMT": 0.18,
    "SAND": 0.35, "MANA": 0.42, "CHZ": 0.078,
    "CRV": 0.42, "AAVE": 140, "COMP": 52,
    "MKR": 1450, "SNX": 1.85, "YFI": 6200,
    "LDO": 1.60, "FXS": 2.40, "BAL": 2.80,
    "ROSE": 0.065, "CELO": 0.72, "KLAY": 0.18,
    "AXS": 6.50, "SLP": 0.0035, "ILV": 55,
    "ALICE": 1.20, "RACA": 0.00045, "TLM": 0.012,
    "ALPACA": 0.35,
}

# ── Top tokens on BSC (expanded to ~100 for broad coverage) ──
TOP_TOKENS: list[dict] = [
    # Stables + Wrapped
    {"addr": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "sym": "WBNB", "dec": 18},
    {"addr": "0x55d398326f99059fF775485246999027B3197955", "sym": "USDT", "dec": 18},
    {"addr": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", "sym": "USDC", "dec": 18},
    {"addr": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56", "sym": "BUSD", "dec": 18},
    {"addr": "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3", "sym": "DAI", "dec": 18},
    {"addr": "0xc5f0f7b66764F6ec8C8Dff7BA683102295E16409", "sym": "FDUSD", "dec": 18},
    # Blue chip assets
    {"addr": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c", "sym": "BTCB", "dec": 18},
    {"addr": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8", "sym": "ETH", "dec": 18},
    {"addr": "0x1D2F0da169ceB9fC7B3144628dB156f3F6c60dBE", "sym": "XRP", "dec": 18},
    {"addr": "0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47", "sym": "ADA", "dec": 18},
    {"addr": "0x7083609fCE4d1d8Dc0C979AAb8c869Ea2C873402", "sym": "DOT", "dec": 18},
    {"addr": "0x570A5D26f7765Ecb712C0924E4De545B89fD43dF", "sym": "SOL", "dec": 18},
    {"addr": "0xba2aE424d960c26247Dd6c32edC70B295c744C43", "sym": "DOGE", "dec": 18},
    {"addr": "0xCC42724C6683B7E57334c4E856f4c9965ED682bD", "sym": "MATIC", "dec": 18},
    {"addr": "0x1CE0c2827e2eF14D5C4f29a091d735A204794041", "sym": "AVAX", "dec": 18},
    # DeFi tokens
    {"addr": "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82", "sym": "CAKE", "dec": 18},
    {"addr": "0xcF6BB5389c92Bdda8a3747Ddb454cB7a64626C63", "sym": "XVS", "dec": 18},
    {"addr": "0xCa3F508B8e4Dd382eE878A314789373D80A5190A", "sym": "BIFI", "dec": 18},
    {"addr": "0x965F527D9159dCe6288a2219DB51fc6Eef120dD1", "sym": "BSW", "dec": 18},
    {"addr": "0x603c7f932ED1fc6575303D8Fb018fDCBb0f39a95", "sym": "BANANA", "dec": 18},
    {"addr": "0x947950BcC74888a40Ffa2593C5798F11Fc9124C4", "sym": "SUSHI", "dec": 18},
    {"addr": "0x4691937a7508860F876c9c0a2a617E7d9E945D4B", "sym": "WOO", "dec": 18},
    {"addr": "0xB0D502E938ed5f4df2E681fE6E419ff29631d62b", "sym": "STG", "dec": 18},
    {"addr": "0xF4C8E32EaDEC4BFe97E0F595AdD0f4450a863a11", "sym": "THE", "dec": 18},
    {"addr": "0x8db1D125B1E9a43E2E24c0Bd9E19E675C2Ca50bC", "sym": "YIELD", "dec": 18},
    {"addr": "0x8f0528ce5ef7b51152a59745be31ddce5b5e8c2", "sym": "ALPACA", "dec": 18},
    # Governance + Oracle
    {"addr": "0xBf5140A22578168FD562DCcF235E5D43A02ce9B1", "sym": "UNI", "dec": 18},
    {"addr": "0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD", "sym": "LINK", "dec": 18},
    {"addr": "0x111111111117dC0aa78b770fA6A738034120C302", "sym": "1INCH", "dec": 18},
    {"addr": "0x4B0F1812e5Df2A09796481Ff14017E600dA56550", "sym": "TWT", "dec": 18},
    {"addr": "0xAD6cAEb32CD2c308980a548bD0Bc5AA4306c6c18", "sym": "BAND", "dec": 18},
    {"addr": "0xF9CeC8d50f6c8ad3Fb6dcCEC577e05aA32B224FE", "sym": "CHR", "dec": 18},
    # Meme tokens
    {"addr": "0xfb5B838b6cfEEdC2873aB27866079AC55363D37E", "sym": "FLOKI", "dec": 9},
    {"addr": "0x2859e4544C4bB03966803b044A93563Bd2D0DD4D", "sym": "SHIB", "dec": 18},
    {"addr": "0x6985884C4392D348587B19cb9eAAf157F13eD1D8", "sym": "PEPE", "dec": 18},
    {"addr": "0xbf1D6B3EfC17CbE0586E0DdAe715C0BD2a1cB8af", "sym": "ELON", "dec": 18},
    # Gaming + Metaverse
    {"addr": "0x16939ef78624453A6243E8bD9708f8b5ca7f30bC", "sym": "BNX", "dec": 18},
    {"addr": "0x12f31B73D812C6Bb0d735a218c086d44D5fe5f89", "sym": "ACE", "dec": 18},
    {"addr": "0x715D400F88C167884bbCc41C5FeA407ed4D2f8A0", "sym": "AXS", "dec": 18},
    {"addr": "0x3019BF2a2eF8040C2b3c2e7Dc02A0574E9B2bC15", "sym": "GMT", "dec": 18},
    {"addr": "0x3B78458981eB7260d1f781cb8be2CaAC7027DbE2", "sym": "TLM", "dec": 4},
    {"addr": "0x3b6041173B80E77F038f3F2C0f9744f04837185e", "sym": "RACA", "dec": 18},
    {"addr": "0x935a544Bf5816E3A7C13DB2EFE3009Ffda0aCdE2", "sym": "ALICE", "dec": 18},
    # L2 / Cross-chain
    {"addr": "0xa2E3356610840271A5618Bc545F6E6bfb9dC92cA", "sym": "ARB", "dec": 18},
    {"addr": "0x2B90Bf2c58e0cC35b7cbE5c126bC162503a89F59", "sym": "APT", "dec": 18},
    {"addr": "0xa2B726B1145A4773F68593CF171187d8EBe4d495", "sym": "INJ", "dec": 18},
    {"addr": "0x0D8Ce2A99Bb6e3B7Db580eD848240e4a0F78aEfD", "sym": "FIL", "dec": 18},
    {"addr": "0x4338665CBB7B2485A8855A139b75D5e34AB0DB94", "sym": "LTC", "dec": 18},
    {"addr": "0x250632378E573c6Be1AC2f97Fcdf00515d0Aa91B", "sym": "BETH", "dec": 18},
    {"addr": "0x6fd7c98458a943f469E1Cf4eA85B173f5Cd342F4", "sym": "BHC", "dec": 8},
    # DeFi blue chips (on BSC)
    {"addr": "0xfFbF1EeF5E0e8Dc609bfE404C4877F33abF2511c", "sym": "PENDLE", "dec": 18},
    {"addr": "0x2dFF88A56767223A5529eA5960Da7A3F5f766406", "sym": "ID", "dec": 18},
    {"addr": "0x7c67Dccb04b67d4666fd97B2BcC0A2b3137B2Dfa", "sym": "SHELL", "dec": 18},
    {"addr": "0x502b0F7B4eE251df37957d207ba3fE62b0E64F7f", "sym": "FLUX", "dec": 18},
    {"addr": "0xd17479997F34dd9156Deef8F95A52D81D265be9c", "sym": "USDD", "dec": 18},
    {"addr": "0x3F56e0c36B2F1c74E0E7F8F2c39b6c0CbC80cC1F", "sym": "QNT", "dec": 18},
    # More ecosystem tokens
    {"addr": "0x3CD2531C1C7D2dC23E095b28D0da95C4e99c9000", "sym": "TRX", "dec": 6},
    {"addr": "0x0782b6d8c4551B9760e74c0545a9bCD90bdc41E5", "sym": "HAY", "dec": 18},
    {"addr": "0x5B1fC1191e4cCE611F6ee2AbC5589c1081F5F399", "sym": "ONT", "dec": 18},
    {"addr": "0x5E21c8E75F84CbF2b3A2cF1A5a61838Dc6549D66", "sym": "VET", "dec": 18},
    {"addr": "0x32dF7e8C8BDfDeFd52a19EbE23Dc1dF6D525B7DB", "sym": "NEAR", "dec": 18},
    {"addr": "0x1B877AF01C559DF1A7f4dBb1c9cDbC7711AFd7FE", "sym": "FTM", "dec": 18},
    {"addr": "0xbfBEe3dAc982148aC793161f736234492b3C3E7d", "sym": "EGLD", "dec": 18},
    {"addr": "0x464863745ED3aF8b9f8871F1082211C55f8f9bCc", "sym": "CEL", "dec": 4},
    {"addr": "0xf790B5B1ef940462c3E16dFC8e5EF1d001D1497A", "sym": "HIGH", "dec": 18},
    {"addr": "0x66B303d5CEdB9F17cDc28B5C1E78D10e5dc9Ae28", "sym": "DODO", "dec": 18},
    {"addr": "0xAF24e047F10DA179A8bA18D4AE5F1Ba22f26c574", "sym": "OLE", "dec": 18},
    {"addr": "0x6f769E65c14EBD8Cb6d5e7b8B0b0e11d4E9b5d0E", "sym": "ARP", "dec": 18},
    {"addr": "0x6f1690B4f3b4A8B6Ce8f7E1B2D6eDBe1B01b8B7a", "sym": "SNFTS", "dec": 18},
    # Additional popular tokens
    {"addr": "0x2b3C34dC6800C49b6Af8Fd5F2905122F34271cEE", "sym": "ACH", "dec": 18},
    {"addr": "0xa184088a740c695E156F91f5cC086a06bb78b827", "sym": "AUTO", "dec": 18},
    {"addr": "0x4BA0057f784858a48fe351445C672FF2a3d43515", "sym": "KALM", "dec": 18},
    {"addr": "0x715D400F88C167884bbCc41C5FeA407ed4D2f8A0", "sym": "AXS", "dec": 18},
    {"addr": "0xfb5B838b6cfEEdC2873aB27866079AC55363D37E", "sym": "FLOKI", "dec": 9},
    {"addr": "0x154A9F9cbd3449AD22FDaE23044319D6eF2a1Fab", "sym": "SKILL", "dec": 18},
    {"addr": "0xeDaC6D6483a69bB212a9bC8f2c5C3dDe502f1f31", "sym": "HI", "dec": 18},
    {"addr": "0x9e26c50B29b5eDb7735f0E856f0fC53DbCC1Df43", "sym": "INV", "dec": 18},
    {"addr": "0x5Bf7e5d2E47f9D0D7D1C0e7C6a7d9c3C9d8D7f6e", "sym": "VISION", "dec": 18},
]

# ── Data Models ──

@dataclass
class TokenHolding:
    symbol: str
    address: str
    decimals: int
    balance_raw: int
    balance_formatted: float
    usd_value_estimate: float

@dataclass
class WalletProfile:
    address: str
    is_contract: bool
    bnb_balance: float
    bnb_usd_value: float
    nonce: int
    token_count: int
    tokens_held: list[TokenHolding]
    top_holdings: list[dict]
    total_token_value_usd: float
    estimated_net_worth_usd: float
    classification: str
    classification_reasons: list[str]
    risk_flags: list[str]
    risk_score: int
    scan_time_ms: float


# ── Helpers ──

def _checksum(addr: str) -> str:
    try:
        return Web3.to_checksum_address(addr)
    except (ValueError, TypeError):
        return addr.lower()


def _get_web3(rpc_url: str | None = None) -> Web3:
    import os
    rpc = rpc_url or os.getenv("BSC_RPC_URL", "https://bsc-dataseed1.binance.org")
    return Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 15}))


def _get_token_price(symbol: str) -> float:
    return TOKEN_PRICES.get(symbol.upper(), 0.0)


def _multicall_balance_of(w3: Web3, owner: str, tokens: list[dict]) -> dict[str, int]:
    """Query balanceOf for all tokens in one batched eth_call via Multicall3."""
    from web3 import Web3 as _W3
    
    padded_owner = owner[2:].lower().zfill(64)
    balance_of_data = bytes.fromhex(BALANCE_OF_SELECTOR + padded_owner)
    
    # Build calls list: [(address, bytes), ...]
    calls = []
    for t in tokens:
        target = _W3.to_bytes(hexstr=t["addr"])
        if len(target) != 20:
            target = bytes.fromhex(t["addr"][2:].zfill(40))
        calls.append((target, balance_of_data))
    
    multicall_addr = _W3.to_checksum_address(MULTICALL3)
    try:
        # ABI encode tryAggregate(bool, (address,bytes)[])
        from eth_abi import encode as _enc
        params = _enc(["bool", "(address,bytes)[]"], [False, calls])
        # Prepend function selector (keccak of "tryAggregate(bool,(address,bytes)[])")
        selector = bytes.fromhex("bce38bd7")
        encoded = selector + params
        raw = w3.eth.call({"to": multicall_addr, "data": encoded})
    except Exception as e:
        logger.warning("Multicall eth_call failed: %s", e)
        return {}
    
    # Decode the return: (bool success, bytes returnData)[]
    from eth_abi import decode as _dec
    try:
        decoded = _dec(["(bool,bytes)[]"], raw)
    except Exception as e:
        logger.warning("Multicall decode failed: %s", e)
        return {}
    
    results = decoded[0] if decoded else []
    balances: dict[str, int] = {}
    for i, (success, return_data) in enumerate(results):
        if success and len(return_data) >= 32 and i < len(tokens):
            val = int.from_bytes(return_data[:32], 'big')
            if val > 0:
                balances[tokens[i]["addr"].lower()] = val
    return balances


# ── Classification ──

def _classify_wallet(bnb_usd: float, token_usd_total: float, nonce: int,
                     is_contract: bool, token_count: int) -> tuple[str, list[str], list[str], int]:
    total_value = bnb_usd + token_usd_total
    classification = "Unknown"
    reasons: list[str] = []
    risk_flags: list[str] = []

    def _set(cls: str, *args: str):
        nonlocal classification
        prio = {"Bot/Contract": 10, "Whale": 8, "Pro Trader": 7, "Bot": 6,
                "Active Trader": 5, "Degen": 4, "Newbie": 2}
        if prio.get(cls, 0) >= prio.get(classification, 0):
            classification = cls
        for a in args:
            reasons.append(a)

    if total_value > 100_000:
        reasons.append(f"Net worth ${total_value:,.0f} — significant holdings")
    elif total_value > 10_000:
        reasons.append(f"Net worth ${total_value:,.0f} — moderate holdings")

    if is_contract:
        _set("Bot/Contract", "Wallet is a smart contract")
    if total_value > 500_000:
        _set("Whale", "Holdings exceed $500k")
    elif total_value > 100_000 and nonce < 1000:
        _set("Whale", "Holdings exceed $100k with moderate activity")
    if nonce > 5000 and total_value < 5000:
        _set("Bot", f"High tx count ({nonce}) with low balance")
    if nonce > 500:
        _set("Pro Trader" if total_value > 50000 else "Active Trader",
             "High value + high activity" if total_value > 50000 else f"Active wallet ({nonce} txns)")
    if token_count > 20 and total_value < 5000:
        _set("Degen", f"Holds {token_count} tokens, low total value")
    if nonce < 10 and total_value < 1000:
        _set("Newbie", f"Low activity ({nonce} txns), small balance")
    elif nonce < 50 and total_value < 100:
        _set("Newbie", "Very low activity, near-zero balance")
    if classification == "Unknown":
        _set("Regular User" if total_value > 1000 else "Small Wallet" if total_value > 0 else "Empty / Inactive")

    risk_score = min(len(risk_flags) * 15, 100)
    return classification, reasons, risk_flags, risk_score


# ── Main Profiler ──

def profile_wallet(address: str, rpc_url: str | None = None) -> dict[str, Any]:
    start = time.time()
    addr = _checksum(address)
    w3 = _get_web3(rpc_url)

    is_contract = False
    try:
        code = w3.eth.get_code(addr)
        is_contract = len(code) > 0
    except Exception:
        pass

    try:
        bnb_balance = w3.eth.get_balance(addr) / 1e18
    except Exception:
        bnb_balance = 0.0
    try:
        nonce = w3.eth.get_transaction_count(addr)
    except Exception:
        nonce = 0

    bnb_usd = bnb_balance * _get_token_price("WBNB")

    # Batched token balances (1 RPC call for ALL tokens!)
    raw_balances = _multicall_balance_of(w3, addr, TOP_TOKENS)

    tokens_held: list[TokenHolding] = []
    for t in TOP_TOKENS:
        bal = raw_balances.get(t["addr"].lower(), 0)
        if bal > 0:
            formatted = bal / (10 ** t["dec"])
            price = _get_token_price(t["sym"])
            tokens_held.append(TokenHolding(
                symbol=t["sym"], address=t["addr"], decimals=t["dec"],
                balance_raw=bal, balance_formatted=round(formatted, 6),
                usd_value_estimate=round(formatted * price, 2),
            ))

    tokens_held.sort(key=lambda t: t.usd_value_estimate, reverse=True)
    token_value = sum(t.usd_value_estimate for t in tokens_held)
    top_holdings = [{"symbol": t.symbol, "balance": t.balance_formatted, "usd_value": t.usd_value_estimate}
                    for t in tokens_held[:10] if t.usd_value_estimate > 0]

    cls, reasons, flags, score = _classify_wallet(bnb_usd, token_value, nonce, is_contract, len(tokens_held))

    profile = WalletProfile(
        address=address, is_contract=is_contract,
        bnb_balance=round(bnb_balance, 6), bnb_usd_value=round(bnb_usd, 2), nonce=nonce,
        token_count=len(tokens_held), tokens_held=tokens_held, top_holdings=top_holdings,
        total_token_value_usd=round(token_value, 2),
        estimated_net_worth_usd=round(bnb_usd + token_value, 2),
        classification=cls, classification_reasons=reasons,
        risk_flags=flags, risk_score=score,
        scan_time_ms=round((time.time() - start) * 1000, 1),
    )
    return asdict(profile)


def wallet_profiler_handler(job_description: str) -> tuple[str, dict]:
    try:
        params = json.loads(job_description)
    except (json.JSONDecodeError, TypeError):
        params = {"address": job_description.strip()}

    address = params.get("address", "").strip()
    if not address or not address.startswith("0x"):
        return json.dumps({"error": "Missing or invalid 'address'"}), {"skill": "wallet-profiler", "status": "error"}

    try:
        result = profile_wallet(address, rpc_url=params.get("rpc_url"))
        return json.dumps(result, indent=2), {
            "skill": "wallet-profiler", "address": address,
            "classification": result.get("classification", "unknown"), "status": "ok",
        }
    except Exception as e:
        logger.exception("Wallet profile failed for %s", address)
        return json.dumps({"error": str(e)}), {"skill": "wallet-profiler", "status": "error"}
