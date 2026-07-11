"""
ERC-8004 Agent Registration — registers the skill marketplace agent's
on-chain identity so other agents can discover it.

Usage:
    python -m src.register
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / os.environ.get("ENV_FILE", ".env"))

from bnbagent import ERC8004Agent, AgentEndpoint, EVMWalletProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("register")

AGENT_NAME = os.getenv("AGENT_NAME", "skill-marketplace-agent")
AGENT_DESCRIPTION = os.getenv("AGENT_DESCRIPTION", "On-chain AI skills marketplace")
BASE_URL = os.getenv("A2A_BASE_URL", "http://localhost:8010").rstrip("/")
NETWORK = os.getenv("NETWORK", "bsc-testnet")


def main():
    private_key = os.getenv("PRIVATE_KEY")
    password = os.getenv("WALLET_PASSWORD")
    if not private_key or not password:
        raise SystemExit("PRIVATE_KEY and WALLET_PASSWORD required")

    wallet = EVMWalletProvider(password=password, private_key=private_key)
    sdk = ERC8004Agent(network=NETWORK, wallet_provider=wallet)

    agent_uri = sdk.generate_agent_uri(
        name=AGENT_NAME,
        description=AGENT_DESCRIPTION,
        endpoints=[
            AgentEndpoint.a2a(f"{BASE_URL}/a2a"),
            AgentEndpoint.mcp(f"{BASE_URL}/mcp", version="2025-06-18"),
        ],
    )

    logger.info("Registering agent on %s...", NETWORK)
    result = sdk.register_agent(agent_uri=agent_uri)

    logger.info(
        "Agent registered!\n"
        "  ID:           %s\n"
        "  Transaction:  %s\n"
        "  Agent URI:    %s",
        result["agentId"],
        result["transactionHash"],
        agent_uri,
    )


if __name__ == "__main__":
    main()
