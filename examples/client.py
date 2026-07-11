"""
Example Client — how to discover, negotiate, and pay for a skill via ERC-8183.

Shows three ways to interact:
  1. A2A discovery (get agent card)
  2. Negotiate a job (get price quote)
  3. Create + fund + settle an on-chain job

Usage:
    python examples/client.py --skill liquidity-depth --pair 0x...
    python examples/client.py --skill rug-risk --token 0x...

Requires BUYER_PRIVATE_KEY in .env (or use --dry-run to skip on-chain steps).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
import httpx

load_dotenv(Path(__file__).resolve().parent.parent / os.environ.get("ENV_FILE", ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("client-demo")

# ── SDK imports (only for on-chain steps) ──
from bnbagent.erc8183 import ERC8183Client, JobStatus
from bnbagent.wallets import EVMWalletProvider


# ── Discovery via A2A ──

async def discover_skills(agent_url: str) -> dict:
    """Fetch the agent card to see available skills."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{agent_url.rstrip('/')}/.well-known/agent-card.json")
        resp.raise_for_status()
        return resp.json()


async def list_skills(agent_url: str) -> dict:
    """Call the list-skills A2A method."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "role": "user",
                "parts": [{"kind": "data", "data": {"skill": "list-skills"}}],
            }
        },
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{agent_url.rstrip('/')}/a2a", json=payload)
        resp.raise_for_status()
        return resp.json()


async def negotiate_job(agent_url: str, target_skill: str, task_description: str) -> dict:
    """Negotiate a price for a specific skill job."""
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "role": "user",
                "parts": [{
                    "kind": "data",
                    "data": {
                        "skill": "negotiate-erc8183-job",
                        "target_skill": target_skill,
                        "task_description": task_description,
                        "terms": {"deliverables": ["structured_data"]},
                    },
                }],
            }
        },
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{agent_url.rstrip('/')}/a2a", json=payload)
        resp.raise_for_status()
        return resp.json()


# ── On-chain job lifecycle ──

def onchain_create_and_fund(
    private_key: str,
    password: str,
    network: str,
    provider_address: str,
    price_wei: int,
    job_description: str,
) -> int:
    """Create, register, set budget, and fund an ERC-8183 job completely."""
    wallet = EVMWalletProvider(password=password, private_key=private_key)
    erc8183 = ERC8183Client(wallet, network=network)

    # Check our balance
    balance = erc8183.token_balance()
    decimals = erc8183.token_decimals()
    symbol = erc8183.token_symbol()
    logger.info("Buyer balance: %.4f %s", balance / (10 ** decimals), symbol)

    if balance < price_wei:
        logger.error("Insufficient balance: need at least %.4f %s", price_wei / (10 ** decimals), symbol)
        return 0

    expired_at = int(time.time()) + 60 * 60  # 1 hour expiry

    logger.info("Creating job (price: %d wei)...", price_wei)
    res = erc8183.create_job(
        provider=provider_address,
        expired_at=expired_at,
        description=job_description,
    )
    job_id = res["jobId"]
    logger.info("Job %d created (TX: %s)", job_id, res.get("transactionHash", "?"))

    logger.info("Registering job with default policy...")
    erc8183.register_job(job_id)
    logger.info("Job %d registered", job_id)

    logger.info("Setting budget to %d...", price_wei)
    erc8183.set_budget(job_id, price_wei)

    logger.info("Funding escrow...")
    erc8183.fund(job_id, price_wei)
    logger.info("Job %d funded! Waiting for provider to submit...", job_id)

    return job_id


def poll_until_completed(
    private_key: str, password: str, network: str,
    job_id: int, timeout: int = 300, poll_interval: int = 10,
) -> dict:
    """Poll a job until it's COMPLETED or times out."""
    wallet = EVMWalletProvider(password=password, private_key=private_key)
    erc8183 = ERC8183Client(wallet, network=network)

    start = time.time()
    while time.time() - start < timeout:
        try:
            status = erc8183.get_job_status(job_id)
            logger.info("Job %d status: %s", job_id, status.name)

            if status == JobStatus.COMPLETED:
                logger.info("Job %d COMPLETED! Payment released to provider.", job_id)

                # Get the deliverable
                try:
                    job = erc8183.commerce.get_job(job_id)
                    return {
                        "status": "completed",
                        "job_id": job_id,
                        "deliverable_hash": "0x" + job.deliverable.hex(),
                        "deliverable_url": f"{os.getenv('ERC8183_AGENT_URL', 'http://localhost:8010')}/erc8183/job/{job_id}/response",
                    }
                except Exception as e:
                    return {"status": "completed", "job_id": job_id, "note": str(e)}

            if status in (JobStatus.REJECTED, JobStatus.EXPIRED):
                logger.warning("Job %d ended with status: %s", job_id, status.name)
                return {"status": status.name, "job_id": job_id}

            # Try to settle if SUBMITTED
            if status == JobStatus.SUBMITTED:
                try:
                    erc8183.settle(job_id)
                    logger.info("Settled job %d", job_id)
                except Exception:
                    logger.info("Job %d in dispute window, waiting...", job_id)

        except Exception as e:
            logger.debug("Poll error: %s", e)

        time.sleep(poll_interval)

    logger.warning("Timed out waiting for job %d", job_id)
    return {"status": "timeout", "job_id": job_id}


async def main():
    parser = argparse.ArgumentParser(description="ERC-8183 Skill Marketplace Client")
    parser.add_argument("--agent-url", default="http://localhost:8010",
                        help="A2A agent base URL")
    parser.add_argument("--skill", default=None,
                        choices=["liquidity-depth", "rug-risk"],
                        help="Skill to call")
    parser.add_argument("--pair", default=None,
                        help="Pair address for liquidity-depth skill")
    parser.add_argument("--token", default=None,
                        help="Token address for rug-risk skill")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip on-chain steps; just negotiate")
    parser.add_argument("--provider", default=None,
                        help="Provider address (from negotiation result)")
    parser.add_argument("--price-wei", type=int, default=None,
                        help="Price in wei (from negotiation result)")

    args = parser.parse_args()

    # ── Step 1: Discover ──
    logger.info("=== Step 1: Discover agent capabilities ===")
    card = await discover_skills(args.agent_url)
    logger.info("Agent: %s", card.get("name", "?"))
    logger.info("Skills: %s", [s["id"] for s in card.get("skills", [])])

    skills_list = await list_skills(args.agent_url)
    logger.info("Available skills: %s", json.dumps(skills_list, indent=2))

    # ── Step 2: Negotiate (if a skill is specified) ──
    if args.skill:
        logger.info("=== Step 2: Negotiate job ===")

        if args.skill == "liquidity-depth":
            pair = args.pair or "0x7213a1F6820D5B9aF5F4e0B93c75e8B6f3D1C9B1"  # CAKE-WBNB on BSC
            task = json.dumps({"pair": pair, "skill": args.skill})
        elif args.skill == "rug-risk":
            token = args.token or "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82"  # CAKE token
            task = json.dumps({"token": token, "skill": args.skill})
        else:
            task = json.dumps({"skill": args.skill})

        negotiation = await negotiate_job(args.agent_url, args.skill, task)
        logger.info("Negotiation result:\n%s", json.dumps(negotiation, indent=2))

        if args.dry_run:
            logger.info("Dry run — stopping here. No on-chain transactions.")
            return negotiation

        # Extract negotiation envelope
        parts = negotiation.get("result", {}).get("parts", [])
        if parts:
            envelope = parts[0].get("data", {})
            provider = envelope.get("provider_address", args.provider)
            price = envelope.get("price_wei", args.price_wei)
        else:
            provider = args.provider
            price = args.price_wei

        if not provider or not price:
            logger.error("Provider address and price needed (from negotiation or --provider/--price-wei)")
            return

        # ── Step 3: Create on-chain job ──
        logger.info("=== Step 3: Create and fund on-chain job ===")

        pk = os.getenv("BUYER_PRIVATE_KEY") or os.getenv("PRIVATE_KEY")
        pw = os.getenv("BUYER_WALLET_PASSWORD") or os.getenv("WALLET_PASSWORD")
        net = os.getenv("NETWORK", "bsc-testnet")

        if not pk or not pw:
            logger.warning("No BUYER_PRIVATE_KEY in .env — can't create on-chain job. Use --dry-run for off-chain demo.")
            return

        job_id = onchain_create_and_fund(pk, pw, net, provider, price, task)
        if not job_id:
            return

        # ── Step 4: Wait for completion ──
        logger.info("=== Step 4: Waiting for provider to fulfill job ===")
        result = poll_until_completed(pk, pw, net, job_id)
        logger.info("Result: %s", json.dumps(result, indent=2))
        return result

    logger.info("No skill specified. Use --skill to test a specific skill.")
    return card


if __name__ == "__main__":
    asyncio.run(main())
