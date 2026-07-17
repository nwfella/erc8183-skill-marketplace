# Mainnet Launch Checklist 🔒

Step-by-step instructions to launch the ERC-8183 Skill Marketplace on BSC **mainnet** securely.  
**Estimated cost:** ~$10-20 in BNB (gas) + U tokens for initial escrow tests.

---

## Phase 0: Wallet Security (DO NOT SKIP)

### ❌ Never reuse the testnet wallet
The wallet `0x2b56e9d...` used during testnet development had its private key exposed in plaintext. **Do not use it on mainnet.**
The testnet keystore has been deleted, but assume that key is compromised.

### ✅ Generate a fresh wallet

```bash
cd ~/projects/marketplace-skill-agent

# Generate a brand new wallet — you will be the ONLY one with the key
python -c "
from bnbagent import EVMWalletProvider
w = EVMWalletProvider(password='your-very-strong-password')
print(f'Address:  {w.address}')
print(f'Save this password — it decrypts the keystore at ~/.bnbagent/wallets/')
"
```

Delete the `PRIVATE_KEY` line from `.env` once the keystore is saved — the SDK auto-loads from the keystore on subsequent runs using just `WALLET_PASSWORD`.

### 💰 Fund the wallet

Send **real BNB** (~0.01–0.05 BNB for gas) and **real U tokens** to the new address. Buy U on a DEX (PancakeSwap) or from a centralized exchange.

> Gas estimate per operation: ~$0.02-0.05 on BSC. A full launch + 100 jobs costs maybe $5-10 in gas.

---

## Phase 1: Configuration

### `.env` setup

Copy the template and fill in your **own** values:

```bash
cp .env.example .env
```

Required fields on mainnet:

| Variable | Value | Notes |
|----------|-------|-------|
| `WALLET_PASSWORD` | Your keystore password | Never share this |
| `NETWORK` | `bsc` | NOT bsc-testnet |
| `ERC8183_SERVICE_PRICE` | `50000000000000000` (0.05 U) | Adjust per skill |
| `A2A_BASE_URL` | `https://your-public-url.com` | Must be internet-reachable |
| `ERC8183_AGENT_URL` | `https://your-public-url.com/erc8183` | Same as above + /erc8183 |

### Optional overrides

For mainnet, the SDK auto-detects these contract addresses, but you can pin them:

```
ERC8183_COMMERCE_ADDRESS=0xea4daa3100a767e86fded867729ae7446476eba6
ERC8183_ROUTER_ADDRESS=0x51895229e12f9876011789b04f8698af06ccd6da
ERC8183_POLICY_ADDRESS=0x9c01845705b3078aa2e8cff7520a6376fd766de5
```

---

## Phase 2: Deployment

### Step 1 — Start the provider server

```bash
screen -S marketplace
cd ~/projects/marketplace-skill-agent
python -m src.server
# Detach: Ctrl+A, then D
```

### Step 2 — Verify it's alive

```bash
curl https://your-public-url.com/health
# Expected: {"status":"ok","agent":"0x...","skills":2}
```

### Step 3 — Start the settle operator (separate session)

```bash
screen -S settle
cd ~/projects/marketplace-skill-agent
python -m src.auto_settle
# Detach: Ctrl+A, then D
```

### Step 4 — Register ERC-8004 identity (one-time, costs gas)

```bash
cd ~/projects/marketplace-skill-agent
python -m src.register
```

This registers your agent on-chain with ID like `agentId=1606`.  
Cost: ~$1-2 in BNB gas (not sponsored on mainnet).

---

## Phase 3: Smoke Test

### Run a real client job to verify the full flow

```bash
cd ~/projects/marketplace-skill-agent
python examples/client.py \
  --agent-url https://your-public-url.com \
  --skill liquidity-depth \
  --pair 0x0eD7e52944161450477ee417DE9Cd3a859b14fD0 \
  --provider 0xYOUR_WALLET_ADDRESS \
  --price-wei 50000000000000000
```

Expected flow:
1. ✅ Discover agent card
2. ✅ Negotiate → signed quote
3. ✅ Create job on-chain → fund escrow in U tokens
4. ✅ Provider detects job → runs analysis → submits result
5. ✅ Background settler → settles → U released to your wallet

---

## Phase 4: Go Public

### Make your agent discoverable

Other agents find you via ERC-8004 lookup. Your agent ID from Step 4 is their handle.

To advertise, post your agent ID + skill list somewhere discoverable:

- **BNB Chain ecosystem map** — submit your agent
- **Twitter/X** — tweet your agent ID and what it does
- **Your own website** — embed the A2A card URL

### Client code for someone to use your skill

A client only needs ~10 lines to call your skill:

```python
from bnbagent.wallets import EVMWalletProvider
from bnbagent.erc8183 import ERC8183Client

wallet = EVMWalletProvider(password="...")
erc8183 = ERC8183Client(wallet, network="bsc")

# Find agent #1606 on-chain, negotiate, create job
# ... see examples/client.py for the full flow
```

---

## Phase 5: Adding Skills

To add a new skill:

1. Write `src/skills/your_skill.py` with a handler function
2. Register it in `src/skills/__init__.py`
3. Restart the server — it's live and sellable immediately

Example skill prices:

| Skill | Price | Margin |
|-------|-------|--------|
| liquidity-depth | 0.05 U | ~100% (pure on-chain reads) |
| rug-risk | 0.08 U | ~100% (pure on-chain reads) |
| wallet-profiler | 0.03 U | ~100% (pure on-chain reads) |
| MEV sandwich check | 0.10 U | ~100% (mempool data) |

---

## Security Checklist

- [ ] Private key was **never** in `.env` (keystore only)
- [ ] `.env` is in `.gitignore` (confirmed with `git status`)
- [ ] Server runs behind HTTPS (Cloudflare or reverse proxy)
- [ ] Rate limiting enabled (default: 60 req/min)
- [ ] ERC-8183 dispute window — you have time to correct bad deliveries
- [ ] Wallet only holds gas + operational U — not life savings
- [ ] Monitor server logs for unusual client behavior
- [ ] Keep the settle operator running to release locked funds

---

## Cost Summary

|| Item | Cost |
||------|------|
|| BNB for gas (initial) | ~0.01–0.05 BNB (~$5-30) |
|| ERC-8004 registration | ~$1-2 one-time |
|| Per-job gas (submit + settle) | ~$0.02-0.05 |
|| VPS hosting (optional) | ~$5-10/month |
|| **Total to start** | **~$10-30** |

---

## Monitoring

### Check server status
```bash
curl https://your-public-url.com/health
```

### Check wallet balances
```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
from bnbagent.wallets import EVMWalletProvider
from bnbagent.erc8183 import ERC8183Client
w = EVMWalletProvider(password=open('.env').read().split('WALLET_PASSWORD=')[1].split()[0])
c = ERC8183Client(w, network='bsc')
print(f'U balance: {c.token_balance() / 10**c.token_decimals():.2f}')
"
```

### Review settled jobs
The settle operator logs every completed job with TX hash.
