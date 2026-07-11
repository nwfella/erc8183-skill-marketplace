"""
ERC-8183 Skill Marketplace — A2A-fronted provider server.

Exposes skills as discoverable A2A agent card + ERC-8183 job negotiation.
Runs a funded-job poll loop in the background that dispatches jobs to
skill handlers.

Usage:
    uvicorn src.server:app --port 8010
    # or
    python -m src.server
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Load .env
load_dotenv(Path(__file__).resolve().parent.parent / os.environ.get("ENV_FILE", ".env"))

# ── SDK & local imports ──
from bnbagent import EVMWalletProvider
from bnbagent.erc8183 import ERC8183Client, ERC8183JobOps, NegotiationHandler, funded_job_watcher
from bnbagent.erc8183.config import ERC8183Config
from bnbagent.storage import LocalStorageProvider
from bnbagent.utils import RateLimitExceeded, SlidingWindowLimiter

from src.skills import get_skill, list_skills

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("skill-marketplace")

# ── Config ──
NETWORK = os.getenv("NETWORK", "bsc-testnet")
AGENT_NAME = os.getenv("AGENT_NAME", "skill-marketplace-agent")
AGENT_DESCRIPTION = os.getenv("AGENT_DESCRIPTION", "On-chain AI skills: liquidity depth analysis, rug-pull risk scoring, and more.")
BASE_URL = os.getenv("A2A_BASE_URL", "http://localhost:8010").rstrip("/")
PORT = int(os.getenv("PORT", "8010"))

# ── Wallet ──
_private_key = os.getenv("PRIVATE_KEY")
if not _private_key:
    raise SystemExit("PRIVATE_KEY is required (see .env.example)")
wallet = EVMWalletProvider(
    password=os.getenv("WALLET_PASSWORD", "marketplace-password"),
    private_key=_private_key,
)

# ── Storage ──
storage = LocalStorageProvider.from_env()

# ── ERC-8183 Config ──
config = ERC8183Config.from_env(storage=storage)
job_ops = ERC8183JobOps(
    wallet,
    network=NETWORK,
    storage_provider=storage,
    service_price=int(config.service_price),
    agent_url=config.agent_url,
)
client = ERC8183Client(wallet_provider=wallet, network=NETWORK)

# ── Negotiation handler ──
negotiation_handler = NegotiationHandler(
    service_price=config.service_price,
    currency=client.payment_token,
    wallet_provider=wallet,
    chain_id=client.network.chain_id,
    verifying_contract=client.commerce.address,
)
negotiate_limiter = SlidingWindowLimiter(max_requests=60, window_seconds=60.0)

# ── A2A Agent Card ──
_s = list_skills()
AGENT_CARD = {
    "protocolVersion": "0.3.0",
    "name": AGENT_NAME,
    "description": AGENT_DESCRIPTION,
    "url": f"{BASE_URL}/a2a",
    "preferredTransport": "JSONRPC",
    "version": "1.0.0",
    "capabilities": {"streaming": False, "pushNotifications": False},
    "defaultInputModes": ["application/json"],
    "defaultOutputModes": ["application/json"],
    "skills": [
        {
            "id": "negotiate-erc8183-job",
            "name": "Negotiate an ERC-8183 job for any skill",
            "description": (
                "Send a data part with skill ID, task description, and terms. "
                "Returns a wallet-signed quote. Anchor on-chain via createJob."
            ),
            "tags": ["erc8183", "negotiation"],
            "inputModes": ["application/json"],
            "outputModes": ["application/json"],
        },
        {
            "id": "list-skills",
            "name": "List available skills and prices",
            "description": "Returns all skills this agent offers, with prices in U tokens.",
            "tags": ["discovery"],
            "inputModes": ["application/json"],
            "outputModes": ["application/json"],
        },
    ],
}

# ── FastAPI App ──
app = FastAPI(title=AGENT_NAME, version="0.1.0")

# ── A2A Endpoints ──

@app.get("/.well-known/agent-card.json")
async def agent_card():
    """A2A agent discovery endpoint."""
    return AGENT_CARD


@app.get("/health")
async def health():
    return {"status": "ok", "agent": wallet.address, "skills": len(get_skill_registry())}


def _rpc_error(req_id, code: int, message: str, status: int = 200) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}},
        status_code=status,
    )


def _agent_message(data: dict) -> dict:
    return {
        "kind": "message",
        "role": "agent",
        "messageId": str(uuid.uuid4()),
        "parts": [{"kind": "data", "data": data}],
    }


def _extract_data(message: dict) -> dict | None:
    for part in message.get("parts", []):
        if isinstance(part, dict) and part.get("kind") == "data" and isinstance(part.get("data"), dict):
            return part["data"]
    return None


def get_skill_registry() -> dict:
    """Import here to avoid circular deps at module level."""
    return list_skills()


@app.post("/a2a")
async def a2a_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return _rpc_error(None, -32700, "Parse error", status=400)

    req_id = body.get("id")
    if body.get("jsonrpc") != "2.0" or "method" not in body:
        return _rpc_error(req_id, -32600, "Invalid Request", status=400)
    if body["method"] != "message/send":
        return _rpc_error(req_id, -32601, f"Method not found: {body['method']}")

    message = (body.get("params") or {}).get("message") or {}
    data = _extract_data(message)
    if data is None:
        return _rpc_error(req_id, -32602, "message must carry a data part with a 'skill' field")

    skill = data.get("skill", "")

    # ── list-skills: no negotiation needed ──
    if skill == "list-skills":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": _agent_message({
                "skills": get_skill_registry(),
                "currency": client.payment_token,
            }),
        }

    # ── negotiate-erc8183-job: requires a specific sub-skill ──
    if skill == "negotiate-erc8183-job":
        client_ip = request.client.host if request.client else "unknown"
        try:
            negotiate_limiter.check(client_ip)
        except RateLimitExceeded:
            return _rpc_error(req_id, -32000, "Rate limited, retry later")

        target_skill = data.get("target_skill", "").strip()
        task_description = data.get("task_description", "")
        terms = data.get("terms", {})

        if not target_skill or not task_description:
            return _rpc_error(
                req_id, -32602,
                "negotiate-erc8183-job requires 'target_skill' (string) and 'task_description' (string)",
            )

        skill_info = get_skill(target_skill)
        if not skill_info:
            return _rpc_error(req_id, -32602, f"Unknown skill: '{target_skill}'. Use list-skills to see available skills.")

        # Override service price to the skill's specific price
        handler = NegotiationHandler(
            service_price=skill_info["price_wei"],
            currency=client.payment_token,
            wallet_provider=wallet,
            chain_id=client.network.chain_id,
            verifying_contract=client.commerce.address,
        )

        try:
            result = handler.negotiate({
                "skill": target_skill,
                "task_description": task_description,
                "terms": terms,
            })
        except Exception as exc:
            logger.error("negotiation failed: %s", exc)
            return _rpc_error(req_id, -32603, "Negotiation failed")

        envelope = result.to_dict()
        envelope["provider_address"] = wallet.address
        envelope["skill"] = target_skill
        envelope["price_wei"] = skill_info["price_wei"]
        return {"jsonrpc": "2.0", "id": req_id, "result": _agent_message(envelope)}

    # ── Fallback ──
    return _rpc_error(req_id, -32602, f"Unknown skill: '{skill}'")


# ── Funded Job Dispatcher ──

def _on_funded(job: dict) -> None:
    """Called by the funded-job watcher loop for each funded job.

    Dispatches to the appropriate skill handler based on the job description.
    """
    import json
    job_id = job["jobId"]
    raw_desc = job.get("description", "{}")

    # Parse the description to find the skill target
    try:
        desc = json.loads(raw_desc) if isinstance(raw_desc, str) else raw_desc
    except json.JSONDecodeError:
        desc = {"task": raw_desc}

    skill_id = desc.get("skill", "")
    skill_info = get_skill(skill_id)

    if not skill_info:
        logger.warning("Job %s: unknown skill '%s', rejecting", job_id, skill_id)
        # We can't reject via SDK easily — just log and skip
        return

    logger.info("Job %s: dispatching to skill '%s'", job_id, skill_id)

    try:
        handler = skill_info["handler"]
        result_str, metadata = handler(desc.get("task", raw_desc))

        # Submit the result on-chain
        job_ops.submit_result(job_id, result_str)
        logger.info("Job %s: submitted result successfully", job_id)
    except Exception as e:
        logger.exception("Job %s: handler failed: %s", job_id, e)


# ── Startup: Hook up the funded-job watcher ──

@app.on_event("startup")
async def startup():
    poll_interval = int(os.getenv("ERC8183_FUNDED_POLL_INTERVAL", "15"))
    logger.info("Starting funded-job watcher (interval=%ds)", poll_interval)

    # Run the watcher as a background task
    import asyncio
    asyncio.create_task(funded_job_watcher(job_ops, _on_funded, interval=poll_interval))

    logger.info(
        "Skill Marketplace Agent running on %s\n"
        "  Wallet:     %s\n"
        "  Network:    %s\n"
        "  Skills:     %s\n"
        "  Commerce:   %s\n"
        "  A2A Card:   %s/.well-known/agent-card.json",
        BASE_URL, wallet.address, NETWORK,
        ", ".join(s["id"] for s in get_skill_registry()),
        config.effective_commerce_address,
        BASE_URL,
    )


# ── Main entry point ──

def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
