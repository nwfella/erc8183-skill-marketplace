"""
Auto-settle operator for the Skill Marketplace.

Permissionlessly settles ERC-8183 jobs once the dispute window has elapsed.
Run as a separate process alongside the server.

Usage:
    python -m src.auto_settle
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from bnbagent.erc8183 import ERC8183Client, JobStatus
from bnbagent.wallets import EVMWalletProvider

load_dotenv(Path(__file__).resolve().parent.parent / os.environ.get("ENV_FILE", ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("auto_settle")


async def settle_loop(client: ERC8183Client, poll_interval: int = 15):
    """Poll for SUBMITTED jobs and settle them when the dispute window passes."""
    logger.info("Auto-settler starting on %s", client.network.name)

    while True:
        try:
            job_counter = await asyncio.to_thread(client.commerce.job_counter)
            start = max(1, job_counter - 100)  # scan last 100 jobs

            for job_id in range(start, job_counter + 1):
                try:
                    job = await asyncio.to_thread(client.commerce.get_job, job_id)
                except Exception:
                    continue  # skip jobs that error on fetch

                if job.status == JobStatus.SUBMITTED:
                    logger.info("Job %d is SUBMITTED — attempting settle", job_id)
                    try:
                        tx = await asyncio.to_thread(client.settle, job_id)
                        logger.info("Job %d settled! TX: %s", job_id, tx.get("transactionHash"))
                    except Exception as e:
                        # Expected fail if dispute window hasn't passed
                        logger.debug("Job %d not yet settleable: %s", job_id, e)

        except Exception as e:
            logger.error("Poll error: %s — retrying in %ds", e, poll_interval)

        await asyncio.sleep(poll_interval)


async def main():
    private_key = os.getenv("PRIVATE_KEY")
    password = os.getenv("WALLET_PASSWORD")
    network = os.getenv("NETWORK", "bsc-testnet")

    if not password:
        logger.error("WALLET_PASSWORD required")
        return

    wallet = EVMWalletProvider(password=password, private_key=private_key)
    client = ERC8183Client(wallet, network=network)

    await settle_loop(client)


if __name__ == "__main__":
    asyncio.run(main())
