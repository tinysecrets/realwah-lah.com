# WAH-LAH — Distribution & Partners Playbook

> Strategic sheet for the supply side of the business: how credits move from hub
> wholesale seats → to players → and (soon) to partner-operated game rooms.
> Companion to `docs/MONEY_PLAYBOOK.md` (demand side / margin) and `memory/ROADMAP.md`.

---

## 1. Thesis (one paragraph)

WAH-LAH is today a **retail-to-wholesale arbitrage machine**: prizes are purchased
from distributor "seats" at six hub portals (wholesale), resold to players as game
credits on seven brand cards at a disclosed retail fee, then cashed back out via
gift card or BTC. The near-term unlock is not more surface area — it is (1) **closing
the credit loop** so redeemed credits fund new deposits instead of bleeding cash,
(2) **productizing the plumbing** into a B2B distributor API that other game-room
operators buy, and (3) **deepening supply** by letting sub-distributors bring their own
seats and sharing margin programmatically. All three compound — they do not compete.

---

## 2. Where we are today (the machine, grounded in code)

### 2.1 Supply side — the pool of seats

- **What a "proxy" is**: one distributor *account/seat* at a hub portal, stored in
  MongoDB `distributor_proxies` (username, encrypted password via `crypto_vault`,
  `base_url`, `hub_type`, status, caps). Code: `backend/services/proxy_pool.py`.
  A proxy is **not** an IP/server.
- **Six hub portals** registered in `HUB_CONFIGS`
  (`backend/services/hub_registry.py`): `sugar_sweeps`, `bitbetwin`, `bitplay`,
  `bitspinwin`, `bitofgold`, `win777`. Adding a hub = one config dict (base URL +
  API paths/form selectors + supported platforms); no new class.
- **Transport**: `hub_bridge.py::make_bridge()` picks the **HTTP fast path**
  (`hub_http_bridge.py`) when a hub exposes `api_base_url`, else falls back to a
  Playwright **stealth/anti-bot bridge** (`GenericHubBridge`).
- **The canonical contract** is the BitBetWin *cart order*
  (`hub_registry.py:116-147`, `hub_http_bridge.py:153-195`):
  - `POST /api/users/login/` → Bearer `token`
  - `POST /api/orders/add` with `{ orderItems: [{ product, slug, name, id, price: 1,
    wager: true, qty: amount }], itemsPrice, totalPrice, user_email,
    payment_method: "wallet" }`
  - Recipient = the partner account's email; products are **$1 credit units** with
    per-platform product ids (e.g. fire_kirin `623599`, juwa `623586`). Credits are
    **1:1 USD**.
- **Selection & limits** (`proxy_pool.py`): round-robin by `last_used_at`; skip
  proxies over `per_transfer_cap` (**$500** default) or `daily_cap` (**$5,000**
  default) or not supporting the target platform. Failures → **cooldown at 3**,
  **lock at 5**.
- **Routing**: `execute_pool_transfer()` (`backend/routes/distributor_pool.py:71`)
  picks a proxy → decrypts credentials → `make_bridge()` → `bridge.transfer(
  recipient, amount, platform)`. Called after a BTC deposit completes
  (`currency_service.py::_dispatch_platform_transfer`); idempotent via
  `pool_transfer_status` (`pending → in_progress → done/failed`).
- **Manual fallback**: `self_distributor` mode
  (`routes/self_distributor.py`, `services/self_distributor.py`) — operator flips
  mode to `manual`; deposits become `distribution_tasks` (`awaiting_send →
  done/failed`); operator sends credits by hand and **keeps 100% margin**.

### 2.2 Demand side — the 7 brand cards

- `backend/game_seed.py` seeds 7 brands: `fire_kirin`, `juwa`, `orion_stars`,
  `ultra_panda`, `panda_master`, `game_vault`, `vblink` (slug, platform_id, logo,
  game_url, accent). Admin CRUD at `backend/routes/payment.py:46-105`.
- Players see one lobby, pick a brand, deposit → credits land on their in-game
  account via the pool → they play on the partner's site.

### 2.3 The money flow (fees = pure house margin)

| Knob | Applied on | Default | Cap | Live-tunable |
|---|---|---|---|---|
| `cashtag` | Cash App / Chime deposit reconcile | 12% | 50% | `POST /api/admin/revenue/settings` |
| `giftcard` | Gift card redemption | 5% | 50% | same |
| `btc` | BTC redemption | 10% | 50% | same |

- Every fee is written to `revenue_ledger`
  (`{kind, user_id, gross_usd, fee_usd, net_usd, ref_id, ref_kind, created_at}`);
  P&L at `GET /api/admin/revenue/summary`. All fees are **disclosed** on the player
  screen. Code: `backend/services/revenue.py`.
- **Redemption paths**: gift cards (manual fulfill, `gift_card_redemptions`
  collection, Tango Card planned) and BTC (`services/btc_payout.py` — self-custodied
  HD wallet signed from `BTC_PAYOUT_XPRV`, broadcast via BlockCypher).
- **Income math (from the Money Playbook)**: 100 players ≈ **$450/mo**;
  500 → ~$2,250/mo; 2,000 → **~$9,000/mo**; 5,000 → ~$22,500/mo.

### 2.4 The three structural leaks (why growth today is cash-hungry)

1. **No `pool_pull`.** When a player redeems credits → BTC/gift card, the credits
   leave the ecosystem and are never recovered to a seat. Every payout is funded
   with **new wholesale cash**. The pool's cost per deposit-dollar is roughly
   redeem-rate × payout-volume (plus fees lost on the pulled margins). ROADMAP P0
   has this as a decision point; it is currently unimplemented.
2. **Thin supply redundancy.** Some games are served by only **1 proxy**
   (`juwa2`, `noble` via Sugar Sweeps) → single point of failure; a seat lock or hub
   outage kills that brand's deposits. Pitch-launch gate wants **≥2 active proxies
   per game**.
3. **Direct agent APIs unwired.** Per-game agent endpoints exist in
   `backend/config/platforms.json` (login/recharge/balance/deduct) but are all
   `enabled: false`; JIT registration is a dry-run stub. The entire supply side
   depends on hub accounts you can buy — no direct-to-brand lanes.

---

## 3. The four strategic directions (deep dives)

### Direction A — B2B Distributor API (the "gateway" play)

**Concept.** Sell what you already built: let third-party game-room operators top up
their end-users' game accounts **through WAH-LAH's pool via API**. You become the
virtual master distributor; each partner is a wholesale customer.

| Aspect | Design |
|---|---|
| Partner onboarding | Admin creates partner → `partner_partners` doc (name, status, `live`/`test`, rc of an API key), secret hashed like credentials via `crypto_vault`. |
| Funding | Partner deposits BTC (reuse `/api/checkout/` / BTCPay) → credits a `partner_balance` ledger (reuse `revenue_ledger` pattern + `payment_transactions` idempotency). |
| Top-up | `POST /api/ext/partners/{key}/topup { game_username, platform, amount, ref }` → gate on balance + caps → reuse `execute_pool_transfer()` unchanged. Partner balance decremented; WH transfer idempotent via `pool_transfer_status`. |
| Webhooks | `partner_transfer.succeeded` / `.failed` / `balance.low` — Resend already wired. |
| Pricing | Partner pays a spread on top of your wholesale cost (`partner_margin` % on their balance tier) instead of your player fee. Live-tunable like `revenue_settings`. |
| Audit | Every partner action in a per-partner ledger; admin P&L per partner. |

**Why now**: ~90% of the plumbing exists (pool, idempotent transfers, balances,
admin). Marginal work is auth, a partner balance, and rate limiting. **Why it's the
biggest unlock**: your margin scales with *other people's volume*, decoupled from
wah-lah.com's own player acquisition.

**Risks**: partner AML/KYC (see §7), abuse/chargeback, seat capacity capping your
own players first (priority rules), rate-limit + IP hardware tokens.

### Direction B — Sub-distributor network (deepen supply)

**Concept.** Other operators bring their **own seats/hubs** into your pool; you route
through them and **split margin programmatically**. Turns competitors into suppliers.

- Extend `distributor_proxies` with `owner` (self | partner), `rev_share` %,
  `is_reserve` flag (hit only when self seats are capped/cooling).
- `select_proxy()` gains a preference order: own seats → reserve/sub-distributor.
- Settlement: nightly cron rolls up per-sub-distributor gross volume × agreed split →
  A/P record; BTC-settle or offset against their top-up spend.
- Same pool UI, plus a `sub_distributor` admin list with per-owner health and P&L.

**Why**: removes the working-capital ceiling (their cash funds seats, not yours),
adds redundancy (their seats increase ≥2-per-game coverage), and converts
would-be rivals into partners who *make you money on their own supply*.

**Risks**: trust/AML (an unvetted sub-distributor is a money-mule channel), seat
quality variance, split disputes → require signed rate card + hard cap per owner.

### Direction C — Close the loop: `pool_pull` + rebalancing (the working-capital fix)

This is *not* a new business line — it is the foundation that makes A and B
profitable instead of cash-hungry.

- **`execute_pool_pull()`** — mirror of `execute_pool_transfer()`:
  `bridge.pull(recipient, amount, platform)` moves credits **from a player's game
  account back to a seat** when they redeem. BTC/gift-card redemption requests
  first attempt a pull; only shortfall is bought wholesale.
- **Credit rebalancer**: cron that (a) sweeps pulled credits into the seat with the
  lowest balance, (b) auto-disables seats whose `balance_cached < floor`, (c) raises
  an alert when aggregate `daily_capacity_remaining < 20%`.
- **Nightly balance resync** (already on ROADMAP): ping each proxy dashboard for
  `balance_cached`; feeds the auto-disable rule.
- **Economic effect**: redeemed dollars stay in the system → new deposits are funded
  by recycled credits → margin roughly doubles at equal player count (you stop paying
  wholesale on the redeem portion).

**Priority order**: land C-first. It is the difference between "scaling revenue"
and "scaling cash burn."

### Direction D — Direct-to-brand integrations (cut out the hub)

- Wire the agent APIs in `platforms.json` (JIT) for your **top 1-2 volume brands**.
  No hub seat, no cart order, no wholesale margin → full retailer margin minus the
  brand's own terms. Lower latency, no anti-bot risk on the hub side.
- Cost: per-brand integration + credentials + compliance exposure with each brand,
  and the brands' own reconciliation tooling (the ecosystem's operators usually
  still settle through a distributor). Do **selectively**, as a margin lever, not a
  first move.

---

## 4. Recommended sequencing

| Phase | Focus | Outcome | Rough effort |
|---|---|---|---|
| **0** | `pool_pull` + rebalancer + nightly resync + balance floor | Recycling credit loop; no more blind wholesale bleed | 2-3 dev days |
| **1** | Redundancy gate: ≥2 seats per game; `Ping all`; capacity alert | No single point of failure under live traffic | 1-2 dev days (mostly existing code) |
| **2** | **B2B Distributor API** (Direction A) — partner model, API key, balance, top-up reuse, webhooks | First paying B2B partner | 3-5 dev days |
| **3** | Sub-distributor onramp (Direction B) — owner/rev_share/reserve, AP settlement | Supply scales without your cash | 2-3 dev days |
| 4 | Direct-to-brand for top volume brands (Direction D) | Margin lift on the biggest lines | per-brand 1-2 weeks |

The **1-2-3** sequence is intentional: fix the leak (0) → make supply safe (1) →
sell the machine (2) → let others feed it (3). Each phase pays for the next.

---

## 5. Build-ready API sketch (Direction A, Phase 2)

Reusing existing endpoints/models; new collection `partner_partners`, new
`partner_balance` ledger, new `partner_api_keys`.

```
POST /api/admin/partners                       { name, default_margin }        → partner + test key (rc)
POST /api/admin/partners/{id}/keys/live         → live key, rotate-able
POST /api/admin/partners/{id}/keys/{kid}/revoke
GET  /api/admin/partners/{id}/p&l

# Partner-facing (auth: X-API-Key)
POST /api/portal/topup                          { game_username, platform, amount, ref, webhook_url }
GET  /api/portal/balance                        → { available_usd, locked_usd }
GET  /api/portal/transfers?limit=...&cursor=...
POST /api/portal/quote                          { platform, amount }            → spread + total (preflight)
```

- **Reuse**: `execute_pool_transfer()`, `pool_transfer_status`, `crypto_vault`,
  `revenue_settings` pattern (→ `partner_margin`), `hub_http_bridge` cart order.
- **New**: rate limiter per key, IP allowlist per partner, balance reservation
  (atomic decrement + `pending` transfer, release on `failed`), webhook delivery
  with retries, per-partner cap that never starves first-party players (priority:
  `self` seats first).

---

## 6. Economics — worked examples

Assumptions: wholesale $1.00 credit ≈ $0.90 cost (hub price), brand product price
1:1 USD.

**A. First-party player deposit ($25 → Fire Kirin)**
- Player pays $25 via Cash App → 22 credits after 12% cashtag fee → $3 house.
- Cost to seat ≈ 22 × $0.90 = $19.80 → **gross path margin ≈ $5.20** (fee + wholesale
  spread), before payout leakage.

**B. Redemption that now recycles (after Phase 0)**
- 22 credits redeemed → BTC: 10% fee = $2.20 house; `pool_pull` recovers up to 22
  credits to a seat → next $19.80 of deposits cost **$0 additional wholesale**.

**C. B2B partner top-up ($500/mo through your API, 3% spread)**
- Partner buys through you at 3% over wholesale ($1.00 + 3% → you keep $15/mo per
  partner at zero marketing cost). 20 partners ≈ $300/mo **pure spread**, stacking
  on top of first-party margin.

**D. Sub-distributor (owner seat, 70/30 split favoring you)**
- Their seat moves $1,000 gross; you collect 30% of the wholesale spread share per
  agreed rate card (~$15-30/mo per owner) plus routing flexibility, zero capital.

---

## 7. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Seat locked / hub outage kills a brand | Medium | ≥2 seats per game (Phase 1 gate); reserve via sub-distributors; nightly balance resync + auto-disable |
| Redemption bleed → cash burn | High today | Phase 0 `pool_pull` + rebalancer first |
| B2B partner = money-mule / launders deposits | Medium | Partner KYC/OFAC screen (reuse compliance stack: OFAC refresh + geo + KYC thresholds), bank-graded limits, IP allowlist, per-partner caps, declining-balance model (no payouts to partners — only their players' in-game credits; **no refund-to-original-source without manual review**) |
| Chargeback / disputed deposit | Low-Medium | All fees disclosed (chargeback = disclosed-fee defense); manual `apply_fee:false` whale path only under admin control; keep `ref`/receipt strings in ledger |
| Sub-distributor seat quality variance | Medium | Warm-up mode (already backlogged): low caps → ramp; health scoring + cooldown/lock machinery reused |
| IP blocks on hubs | Low | Residential proxy pool backlog item; HTTP fast path preferred (fewer bot checks) |
| Wholesale price inflation on a hub | Low-Medium | Multi-hub arbitrage (rebalancer compares `platform_products` prices); spread guard: auto-warn if wholesale price crosses a threshold |

---

## 8. KPIs to instrument (all admin, before Phase 2)

- `pool_transfer` success rate + failure-by-reason (cooldown/lock/cap) per hub.
- `daily_capacity_remaining` % and time-to-lock per seat.
- Redemption → pull success rate (Phase 0) and **recycled-credit ratio**
  (pulls-funded-deposits ÷ total deposits).
- Per-game revenue margin after wholesale cost (net, not just fee).
- B2B: active partners, top-up volume, spread $, webhook delivery rate, churn.

---

## 9. Open decisions (need Justin's input)

1. **Pool pull scope**: can every brand's bridge pull credits back, or is pull
   limited to platforms where the seat's own account can receive? (Determines
   Phase 0 coverage; start with the brands whose products we control on the seats.)
2. **B2B pricing model**: flat spread on wholesale, or on a "retail tier" table?
   First partner pricing should be negotiated, not automated.
3. **Sub-distributor onboarding bar**: minimum seat funding + verified identity +
   signed rate card, or light-touch first?
4. **Brand priority** for Direction D: which 1-2 brands are your highest-volume,
   so we scope the first direct integration.

---

## 10. File map (build targets)

| Area | File(s) |
|---|---|
| Pool/selection/health | `backend/services/proxy_pool.py`, `backend/routes/distributor_pool.py` |
| Hub contracts (BitBetWin cart) | `backend/services/hub_registry.py`, `backend/services/hub_http_bridge.py`, `backend/services/hub_bridge.py` |
| Manual mode | `backend/services/self_distributor.py`, `backend/routes/self_distributor.py` |
| Revenue/ledger | `backend/services/revenue.py`, `backend/routes/revenue_admin.py` |
| Payouts | `backend/services/btc_payout.py`, `backend/routes/gift_cards.py` |
| Compliance | OFAC refresh + KYC thresholds + geo gate (`backend/routes/boss_genie.py`, compliance services) |
| New (Phase 2) | `partner_partners`, `partner_balance`, `partner_api_keys`, `routes/partners.py`, rate limiter middleware |
| Roadmap hooks | `memory/ROADMAP.md` (pool_pull P0, warm-up mode, inventory, IP rotation) |

---

## 11. Player-facing token-sourcing transparency (support template)

Used verbatim by support when players ask where credits come from. Keep answers
within these four facts — never claim manufacturer-direct sourcing or in-house
minting, and never name an under-contract hub as "ours".

1. **Who supplies credits?** We buy credits *wholesale* from a network of partner
   sweepstakes portals and resell them to players. We are a retail-to-wholesale
   operator, not a manufacturer or a hub.
2. **Redeemability.** Dual-currency model: purchased tokens are play-only and not
   redeemable; only free-AMOE credits and credits won through gameplay redeem.
3. **Fees.** A resale margin is built into funding: BTC/crypto ~10%, Cash App
   ~12%, gift cards ~5%. Redemptions of eligible credits carry no purchase fee.
4. **Brand ownership.** Games in The Bill (Fire Kirin, Juwa, etc.) are run by
   independent game vendors; WAH-LAH is the connecting venue, not their maker.

This support template mirrors `backend/static/terms.html` §4 (sourcing bullets)
and the FAQ accordion on the landing page. Any copy referencing BTC cash-outs
should get counsel review before external send.