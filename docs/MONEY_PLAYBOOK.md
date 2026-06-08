# WAH-LAH — Operator's Money Playbook

> Justin, this is your daily money flow. Read once, then never again.

---

## The 3 Money Knobs (Pure House Margin)

| Knob | What it does | Default | Live tunable? |
|---|---|---|---|
| `cashtag` | Skim on every Cash App / Chime deposit you manually reconcile | **12%** | YES — `POST /api/admin/revenue/settings` |
| `giftcard` | Skim on every gift card redemption | **5%** | YES |
| `btc` | Skim on every BTC payout | **10%** | YES |

These are the three places WAH-LAH makes you money. Stripe deposits go through at 0% house skim (Stripe already eats 2.9%, adding more = chargebacks = dead account). All fees are **disclosed** to the player on the relevant screen so they can never claim they didn't know.

---

## Daily Ops — Cash App / Chime Deposit Reconcile

1. Player sends **$25** to `$jrs092393` with their game tag in the note
2. You confirm the deposit hit your Cash App
3. Hit the admin endpoint (the frontend admin panel calls this for you — same URL):

   ```bash
   POST /api/admin/cashtag/reconcile
   {
     "user_id": "<player_uuid>",
     "amount_usd": 25,
     "source": "cashapp",
     "note": "CashApp receipt #abc123"
   }
   ```

4. System credits the player **22 credits** (net after 12% fee)
5. System logs **$3 to your revenue ledger** (gross $25 − fee $3 = net $22)
6. Done. You just made $3 on a 30-second action.

Same flow for Chime — just set `source` to `chime`.

---

## Daily Ops — Gift Card Redemption (Player Side)

The player initiates this from their dashboard. You don't have to do anything until they hit "Redeem":

1. Player has **25 credits**, wants an Amazon card
2. Hits Redeem on the WAH-LAH dashboard
3. Backend auto-applies the **5% redemption fee**
4. System creates a pending redemption for **$23.75** worth of Amazon
5. **$1.25 lands in your revenue ledger automatically**
6. You see a notification in admin → fulfill the redemption (paste the gift card code or use Tango Card API later)

---

## Daily Ops — BTC Payout (Player Side)

Same pattern as gift card, but bigger fee:

1. Player redeems **25 credits** to BTC
2. System auto-applies **10% fee**
3. Held in `redemption_requests` collection with status `hold_admin_review`
4. KYC/AML checks already ran (Basic/Enhanced thresholds + OFAC sanctions screen)
5. You approve in admin → send BTC manually (or wire Lightning/on-chain later)
6. **$2.50 already in your ledger before you even send the BTC**

---

## The Dashboard

```bash
GET /api/admin/revenue/summary          # P&L for last 30 days
GET /api/admin/revenue/summary?days=7   # last 7 days
GET /api/admin/revenue/ledger           # last 100 raw fee rows
```

What you'll see:

```json
{
  "window_days": 30,
  "total_gross_usd": 12500.00,
  "total_fee_usd": 1640.00,
  "all_time_fee_usd": 4321.00,
  "by_kind": {
    "cashtag":  { "gross_usd": 9200, "fee_usd": 1104, "count": 184 },
    "giftcard": { "gross_usd": 1800, "fee_usd": 90,   "count": 22  },
    "btc":      { "gross_usd": 1500, "fee_usd": 150,  "count": 8   }
  },
  "current_rates": { "cashtag": 0.12, "giftcard": 0.05, "btc": 0.10 }
}
```

That `total_fee_usd` is **your net** for the period. Same dollars in your bank account at end of month.

---

## Adjusting Rates Live (No Redeploy)

Want to raise the cashtag skim to 15% temporarily? Or drop gift card to 3% for a promo weekend?

```bash
POST /api/admin/revenue/settings
{ "cashtag": 0.15 }      # only update what you want; others stay

POST /api/admin/revenue/settings
{ "cashtag": 0.12, "giftcard": 0.03, "btc": 0.10 }   # update multiple at once
```

The rates are loaded fresh on the next call. **No restart, no redeploy.**

Rates are capped at **50%** internally (so you can't accidentally set 500% and brick deposits).

---

## Realistic Income Math

At 100 active players, average $40 deposit/month, ~70% Cash App / 30% Stripe:

| Stream | Volume/mo | House Keep | $/mo |
|---|---|---|---|
| Cash App reconciles (70% × $4000 deposits × 12%) | $2800 | 12% | **$336** |
| Stripe deposits (30% × $4000) | $1200 | 0% | $0 |
| Gift card redemptions (assume 40% of credits cash out, 60% via gift card) | $960 | 5% | **$48** |
| BTC redemptions (40% × 40%) | $640 | 10% | **$64** |
| **TOTAL NET TO JUSTIN** |  |  | **~$450/mo** |

Scale that linearly:
- **500 players**: ~$2,250/mo
- **2,000 players** (real fish-game scale): **~$9,000/mo**
- **5,000 players**: ~$22,500/mo

All clean. All disclosed. All in your bank.

---

## "What If" Plays

- **Promo weekend**: drop Cash App fee to 8% Friday-Sunday → "Lowest fees of the year!" — players binge deposit, you still net hundreds.
- **Whale handler**: when a player deposits >$500 in a session, manually set `apply_fee: false` on the reconcile endpoint → give them 100% credit value. Lock in lifetime loyalty.
- **Slow week**: bump Cash App to 15%, gift card to 7%, BTC to 12% — milk the remaining whales while customer acquisition is paused.
- **Mass cashout day**: if 30 players try to redeem at once, leave fees at default — you're making more than usual, the volume IS the bonus.

---

## What's Coming Next (Backlog)

- [ ] **Frontend admin screen** for the revenue dashboard (currently API-only — quick win, ~2 hours of work when you're ready)
- [ ] **Bonus credits with playthrough** (knob #2 from the original revenue stack — "deposit $25 get $30 in credits, but $5 has 1× playthrough lock")
- [ ] **Tier-based fee structure** (VIP players get 8% Cash App, free players get 15%)
- [ ] **Tango Card B2B integration** so gift cards auto-fulfill at 5% wholesale discount (double margin — 5% house skim + 5% wholesale spread = 10% net per gift card)
- [ ] **Referral rev-share** (inviter gets 2% lifetime of invitee's deposit fees)

Say the word on any of these when you're ready. The base engine is in.

---

## File Locations (For Future Devs)

| What | Where |
|---|---|
| Revenue math + ledger helpers | `/app/backend/services/revenue.py` |
| Cash App reconcile endpoint | `server.py` → `/api/admin/cashtag/reconcile` |
| Gift card fee application | `routes/gift_cards.py` → `/api/giftcard/request` |
| BTC fee application | `server.py` → `/api/redemption/request` |
| Admin dashboard endpoints | `routes/revenue_admin.py` → `/api/admin/revenue/*` |
| Default rates | `backend/.env` → `CASHTAG_KEEP_RATE`, `GIFTCARD_FEE_RATE`, `BTC_FEE_RATE` |
| Live overrides | MongoDB `revenue_settings` collection (key: `_id: "current"`) |
| Revenue history | MongoDB `revenue_ledger` collection |
