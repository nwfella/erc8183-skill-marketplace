"""Skill registry — maps skill IDs to their ERC-8183 task handlers."""

from .liquidity_depth import analyze_pair_handler
from .rug_risk import rug_risk_handler

# Registry: skill_id -> (handler_fn, service_price_in_wei, description)
# handler_fn(job_description: str) -> tuple[str, dict]  (result_string, metadata)
SKILL_REGISTRY = {
    "liquidity-depth": {
        "handler": analyze_pair_handler,
        "price_wei": 500_000_000_000_000_000,  # 0.5 U
        "description": "Analyze a PancakeSwap V2 pair's liquidity depth, price impact, and optimal trade size. Input: {\"pair\": \"0x...\"}",
        "tags": ["defi", "liquidity", "bsc", "pancakeswap"],
    },
    "rug-risk": {
        "handler": rug_risk_handler,
        "price_wei": 1_000_000_000_000_000_000,  # 1.0 U
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
