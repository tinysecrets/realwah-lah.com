# Game Integration Spec — Wiring WAH-LAH to the 7 Game Brands

**Status:** Diagnostic / procurement spec (Option A). Reads the *actual running code*
and states exactly what must be true for one deposit dollar to reach one game.

The short truth: **today, a deposit books credits only on the player's WAH-LAH
account. Nothing is pushed to any game, and the player's generated
username/password does not exist on the game's servers.** This document maps the
two broken halves and the per-brand requirements to fix it.

---

## 1. What actually happens today (deposit → credit)

A BTC deposit is finalized in
`backend/services/currency_service.py:complete_btc_purchase` (called by the
BlockCypher webhook). That function:

1. Flips the `btc_deposits` record to `completed`.
2. Credits `Sugar Tokens` + bonus `Game Credits` via `$inc` on the **local user
   doc** in Mongo.
3. Returns. **No call to any game platform.**

There are two code subsystems that *attempt* to talk to the games. Both are
**unwired in the running app**:

| Subsystem | Files | What it does | Live today? |
|---|---|---|---|
| Middleware game bridge | `middleware/session_manager.py`, `middleware/backend_bridge.py`, `middleware/game_middleware_manager.py` | Full agent-login + recharge/deduct/balance HTTP machinery (CSRF, cookie/token sessions, 5-min heartbeat, payload variants) | **No.** `GameMiddlewareManager` is never instantiated in the running app. All platforms `enabled: false` in `config/platforms.json`. |
| Platform JIT registration | `routes/platform_jit.py` | `register()` adapter + `/ext/platform/register` endpoint | **No.** The `register()` adapter is a **dry-run stub** (returns the master username as the "platform UID"; sends nothing to the game). `register_adapter()` has **zero callers**, so `get_adapter()` always falls back to the stub. |

Consequences, verified in code:

- **Player login won't work at the game.** `PlatformAdapter.register()`
  (`platform_jit.py:52-55`) returns `True, username` without any network call,
  and no real adapter is ever registered. The username/password stored on the
  WAH-LAH user is not known to Fire Kirin / Juwa / etc.
- **Money won't reach the game.** A completed deposit never calls
  `allocate_credits()` / `recharge_user()`. `platforms.json` has no agent
  credentials and every platform is `enabled: false`.

So the entire "player deposits, plays in the game, withdraws winnings" loop is
**not operational**. The five-step plan below is what must happen — in order —
for any single game to go live.

---

## 2. The five steps that must be true for ANY game to work

These are per-game and non-negotiable. Everything is gated on **step 1**.

### Step 1 — Obtain a distributor/agent account (this is the real-money step)

The game brands are real-money fish/credit platforms that sell **agent /
distributor accounts** to operators. This is the relationship that lets you top
up player balances. The agent panel is the thing your backend automates.

> ⚠️ Compliance note, read before paying anything: Fire Kirin, Juwa, Orion
> Stars, Ultra Panda, Panda Master, Game Vault, and vBlink are **grey-market
> platforms that are illegal in many US states** (e.g. banned in Texas,
> Michigan, New Jersey) and have been subject to trademark / real-money-gambling
> litigation (NFL, casinos). Buying/operating agent accounts carries
> enforcement and ToS risk, and these "agent APIs" are **not** official public
> APIs — they are reverse-engineered and change without notice. This is a
> business/compliance decision, not just an engineering one.

### Step 2 — Provision agent credentials as environment vars

Per brand, set the agent username/password (referenced by
`config/platforms.json` → `credentials.username_env` / `password_env`):

```
FIREKIRIN_AGENT_USER   FIREKIRIN_AGENT_PASS
JUWA_AGENT_USER        JUWA_AGENT_PASS
JUWA2_AGENT_USER       JUWA2_AGENT_PASS
ULTRAPANDA_AGENT_USER  ULTRAPANDA_AGENT_PASS
PANDAMASTER_AGENT_USER PANDAMASTER_AGENT_PASS
ORIONSTARS_AGENT_USER  ORIONSTARS_AGENT_PASS
GAMEVAULT_AGENT_USER   GAMEVAULT_AGENT_PASS
```

### Step 3 — Verify and correct the real agent API schema (per brand)

The endpoint paths + payloads in `config/platforms.json` and
`middleware/backend_bridge.py` are **guesses** and will differ per brand. Confirm
against a live agent panel:

- **login endpoint & auth style** — session cookie (JSESSIONID / connect.sid) vs
  bearer token vs CSRF-token form. `session_manager.py` handles all three but
  must match reality.
- **recharge / balance / deduct paths** — e.g. Panda Master `/agent/addcredits`
  + `/agent/playerinfo` + `/agent/removecredits`; Orion `/api/credit/add` +
  `/api/player/info`. Field names (`player_id` vs `playerId` vs `user_id`,
  `amount` vs `credits` vs `credit_amount`) are currently brute-forced via
  payload variants (`backend_bridge.py:160-176`) — pin them down instead.
- **success response shape** — the credit/tx parser looks for
  `transaction_id | transactionId | id | txId` (`backend_bridge.py:188-196`);
  the balance parser keys on `balance | credits | amount | credit_balance`
  (`backend_bridge.py:285-289`). Confirm these fields actually come back.
- **player creation/registration** — required for Step 5. How does a new player
  account get created from the agent panel (or does the game auto-create on
  first recharge)? This determines the real `register()` adapter.

### Step 4 — Enable each platform safely

Flip `enabled: true` for a platform **only after** Steps 1–3 pass for it, so you
never take deposits against a platform that can't be honored. Recommended:
enable one brand (easiest to buy — often Juwa or Fire Kirin), prove the full
loop, then replicate.

### Step 5 — Implement the missing code (two fixes)

Two code gaps must be closed once a real agent account exists:

**(a) Real registration adapter.** `routes/platform_jit.py` needs a concrete
adapter that actually creates/logs-in the player at the game (not the dry-run
stub), wired via `register_adapter(platform_id, adapter)` — which currently has
**zero callers**. The player's generated username/password must be sent to the
game and a real `platform_uid` returned and stored.

**(b) Wire the payment path to the bridge.** `complete_btc_purchase`
(`currency_service.py:261`) must, after booking credits, hand off to
`allocate_credits()` → `bridge.recharge_user()` so the amount actually lands in
the game, and store the converted `platform_uid` for future recharge/deduct
lookups.

Also flag: `allocate_credits` uses `credits = amount_usd` at **1:1**
(`game_middleware_manager.py:99`), which will not match how the game prices
in-game credits — confirm the real credit-per-dollar rate per brand.

---

## 3. Per-game integration matrix (current state)

From `config/platforms.json` and source. All `enabled: false` today.

| Brand | slug | agent_url | assumed login | assumed recharge | assumed balance | assumed deduct | Notes |
|---|---|---|---|---|---|---|---|
| Fire Kirin | `fire_kirin` | `https://agent.firekirin.xyz` | `/api/auth/login` | `/api/agent/recharge` | `/api/agent/balance` | `/api/agent/deduct` | Start candidate |
| Juwa | `juwa` | `https://agent.juwa777.com` | `/api/auth/login` | `/api/agent/recharge` | `/api/agent/balance` | `/api/agent/deduct` | Start candidate (easy to buy) |
| Juwa 2 | `juwa2` | `https://agent.juwa2.com` | `/api/auth/login` | `/api/agent/recharge` | `/api/agent/balance` | `/api/agent/deduct` | second Juwa seat |
| Ultra Panda | `ultra_panda` | `https://agent.ultrapanda.mobi` | `/api/auth/login` | `/api/agent/recharge` | `/api/agent/balance` | `/api/agent/deduct` | |
| Panda Master | `panda_master` | `https://agent.pandamaster.vip` | `/agent/login` | `/agent/addcredits` | `/agent/playerinfo` | `/agent/removecredits` | different schema |
| Orion Stars | `orion_stars` | `https://agent.orionstars.vip` | `/api/login` | `/api/credit/add` | `/api/player/info` | `/api/credit/deduct` | different schema |
| Game Vault | `game_vault` | `https://agent.gamevault.com` | `/api/v1/auth` | `/api/v1/credits/add` | `/api/v1/player` | `/api/v1/credits/remove` | different schema |

(Note: `vBlink` — slug `vblink` in the games seed/GAME data — has **no entry** in
`platforms.json`. If you intend to integrate vBlink, add a platform block for it.)

---

## 4. Proven-by-code requirements checklist (sign-off for going live)

Use per brand; write the results into this doc when done.

- [ ] Distributor/agent account purchased (record: brand, cost, monthly limits).
- [ ] Agent env vars set at Render (`<_BRAND>_AGENT_USER`, `<_BRAND>_AGENT_PASS`).
- [ ] Real agent API confirmed for: login auth style, recharge path + fields,
      balance path + fields, deduct path + fields, response tx_id/balance keys.
- [ ] `platforms.json` updated: correct endpoints, `enabled: true`.
- [ ] Real `register()` adapter implemented + `register_adapter()` wired.
- [ ] Player username/password **actually created** at game; `platform_uid` stored.
- [ ] Deposit → `recharge_user()` lands credits in game; verified via balance pull.
- [ ] In-game credit-per-dollar rate confirmed and applied (not hardcoded 1:1).
- [ ] Withdrawal → `deduct_credits()` + BTC payout path exercised once.
- [ ] Frontend gate: only platforms passing the above are shown as "playable".

---

## 5. Immediate safety net (recommended alongside procurement)

While you obtain agent accounts, gate the product so you don't present games as
playable / take deposits that can't be honored:

- Guard `/ext/platform/register` and the deposit UI with an
  **`enabled` + credential-present** check per platform.
- Mark non-integrated games "coming soon / maintenance" in the frontend.

---

## 6. Files to touch when integrating

- `config/platforms.json` — per-brand endpoints, `enabled`, credentials refs.
- `routes/platform_jit.py` — real adapters + `register_adapter()` wiring.
- `middleware/session_manager.py` / `backend_bridge.py` — per-brand schema fixes.
- `middleware/game_middleware_manager.py` — instantiate the manager in the app;
  fix `allocate_credits` 1:1 rate.
- `services/currency_service.py` (`complete_btc_purchase`) — hook deposit →
  recharge handoff.
- `render.yaml` — agent env vars (secrets, `sync: false`).
- Frontend — `enabled`/playable gate.