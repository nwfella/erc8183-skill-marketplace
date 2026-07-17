"""Skill registry — maps skill IDs to their ERC-8183 task handlers."""

from .liquidity_depth import analyze_pair_handler
from .rug_risk import rug_risk_handler
from .wallet_profiler import wallet_profiler_handler

# Registry: skill_id -> (handler_fn, service_price_in_wei, description)
# handler_fn(job_description: str) -> tuple[str, dict]  (result_string, metadata)
SKILL_REGISTRY = {
    "wallet-profiler": {
        "handler": wallet_profiler_handler,
        "price_wei": 30_000_000_000_000_000,  # 0.03 U (~$0.03)
        "description": "Profile a BSC wallet address: holdings, net worth estimate, behavioral classification, and risk flags. Input: {\"address\": \"0x...\"}",
        "tags": ["analytics", "wallet", "portfolio", "bsc", "classification"],
    },
    "liquidity-depth": {
        "handler": analyze_pair_handler,
        "price_wei": 50_000_000_000_000_000,  # 0.05 U (~$0.05)
        "description": "Analyze a PancakeSwap V2 pair's liquidity depth, price impact, and optimal trade size. Input: {\"pair\": \"0x...\"}",
        "tags": ["defi", "liquidity", "bsc", "pancakeswap"],
    },
    "rug-risk": {
        "handler": rug_risk_handler,
        "price_wei": 80_000_000_000_000_000,  # 0.08 U (~$0.08)
        "description": "Check a BSC token for rug-pull risk factors: honeypot, liquidity lock, mint authority, holder concentration. Input: {\"token\": \"0x...\"}",
        "tags": ["security", "token", "risk", "bsc"],
    },
}


def get_skill(skill_id: str) -> dict | None:
    """Look up a skill by ID."""
    return SKILL_REGISTRY.get(skill_id)


def list_skills() -> list[dict]:
    """Return all available skills as a list of card entries."""
    return [
        {"id": sid, **info}
        for sid, info in SKILL_REGISTRY.items()
    ]
