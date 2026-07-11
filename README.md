# ERC-8183 Skill Marketplace

**Sell AI skills per-call on BNB Chain — no subscriptions, no dashboards, just agent-to-agent commerce.**

## What This Is

A **provider agent** that exposes on-chain skills via the ERC-8183 protocol. Any other agent or script can discover it via ERC-8004, negotiate a price, fund escrow in U tokens, receive the deliverable, and settle trustlessly. If the provider cheats, the client disputes and a voter quorum decides.

### Skills Available

| Skill | Price | What it does |
|-------|-------|-------------|
| `liquidity-depth` | 0.5 U | Analyzes a PancakeSwap V2 pair's liquidity depth, price impact at 1%/5%/10% slippage, optimal trade size, and concentration risk |
| `rug-risk` | 1.0 U | Checks a BSC token for rug-pull indicators: mint authority, LP lock status, honeypot patterns, holder concentration |

## Architecture

```
                    A2A (HTTP)
Client ─────────────────────────► Server (FastAPI)
  │    GET /.well-known/agent-card.json     │
  │    POST /a2a  negotiate-erc8183-job      │──► NegotiationHandler (signs quote)
  │                                  │
  │    On-chain (ERC-8183 protocol)  │
  │    createJob → fund()            │
  │                                  │
  │    ◄── funded_job_watcher ◄───── │──► skill handler → submit_result()
  │                                  │
  │    settle() (permissionless)     │
```

## Quick Start

### 1. Prerequisites

```bash
pip install bnbagent fastapi uvicorn httpx python-dotenv web3
```

### 2. Set up your wallet

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

Generate a wallet or use an existing one:

```python
from bnbagent import EVMWalletProvider
wallet = EVMWalletProvider(password="your-password")
print(f"Address: {wallet.address}")  # fund this with BNB + U tokens
```

### 3. Run the server

```bash
python -m src.server
```

This starts:
- A2A discovery at `http://localhost:8010/.well-known/agent-card.json`
- A2A negotiation at `POST http://localhost:8010/a2a`
- A funded-job poll loop that watches for new client jobs and dispatches them to skill handlers

### 4. Run the client (separate terminal)

```bash
# Dry run: discover + negotiate only
python examples/client.py --skill liquidity-depth --pair 0x... --dry-run

# Full flow: discover → negotiate → create job → fund → wait for result
python examples/client.py --skill rug-risk --token 0x...
```

### 5. Run the settle operator (optional, separate terminal)

```bash
python -m src.auto_settle
```

This permissionlessly settles completed jobs whose dispute window has elapsed.

### 6. Register on ERC-8004 (optional)

```bash
python -m src.register
```

Other agents can now discover your skill marketplace via on-chain lookup.

## Testing on Testnet

1. Get tBNB from the [BSC Faucet](https://www.bnbchain.org/en/testnet-faucet)
2. Get test U tokens from the [U Faucet](https://united-coin-u.github.io/u-faucet/)
3. Set `NETWORK=bsc-testnet` in `.env`
4. Run the server and client

## Deployment Checklist

- [ ] Fund wallet with BNB (gas) and U tokens (for testing)
- [ ] Run server and verify health: `curl http://localhost:8010/health`
- [ ] Test dry-run with each skill
- [ ] Test full on-chain flow on testnet
- [ ] Deploy behind a public URL (ngrok or cloud VM)
- [ ] Set `A2A_BASE_URL` and `ERC8183_AGENT_URL` to your public URL
- [ ] Register on ERC-8004 for discovery
- [ ] Run settle operator

## Adding a New Skill

1. Create `src/skills/your_skill.py` with a handler function:

```python
def your_handler(job_description: str) -> tuple[str, dict]:
    \"\"\"Do something useful and return (result_string, metadata).\"\"\"
    result = do_analysis(job_description)
    return json.dumps(result), {"skill": "your-skill", "status": "ok"}
```

2. Register it in `src/skills/__init__.py`:

```python
"your-skill": {
    "handler": your_handler,
    "price_wei": 750_000_000_000_000_000,  # 0.75 U
    "description": "...",
    "tags": ["...", "..."],
}
```

That's it. The server picks it up automatically.

## How ERC-8183 Gets Us Paid

1. **Client** finds our agent card, picks `liquidity-depth`
2. **Client** calls `negotiate-erc8183-job` → gets a signed quote for 0.5 U
3. **Client** creates an on-chain job: `createJob(provider=us, ...)` → `fund(0.5 U)` → tokens locked in escrow
4. **Our server** detects the funded job via poll loop → runs the skill handler → `submit_result()`
5. **Either party** calls `settle()` after dispute window → verdict = APPROVE (silence = approval) → **0.5 U released to us**
6. If client disputes, a whitelisted voter panel decides. Bad dispute = they lose the fee.

No payment infra, no chargebacks, no subscription management. We get paid when we deliver.
