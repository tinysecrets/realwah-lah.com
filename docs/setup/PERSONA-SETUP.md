# Persona KYC — One-Time Setup (5 min)

The code is already wired. Just plug in 4 keys.

## 1. Sign up & access dashboard
1. Go to https://withpersona.com → **Sign up** with `Jrs092393@gmail.com`
2. Verify email → land in dashboard
3. Top-left environment selector → confirm you're in **Sandbox** (test) for now

## 2. Get the API key
- Left sidebar → **API → API Keys**
- Click **Create API Key** (or copy the existing Sandbox key)
- Copy value → it'll start with `persona_sandbox_...`
- **Save this** → you'll paste it as `PERSONA_API_KEY`

## 3. Create the 2 inquiry templates

### Basic (for $500+ redemptions)
- Left sidebar → **Inquiries → Templates** → **Create template**
- Pick the **KYC Solution** from Solutions Library
- Name it: `kyc-basic-sweepstakes-500`
- Default settings are fine (Government ID + Selfie)
- **Save** → top of the editor shows the Template ID (`itmpl_...`)
- **Save this** → `PERSONA_TEMPLATE_ID_BASIC`

### Enhanced (for $5,000+ redemptions)
- Same flow → **Create template**
- Pick the **KYC + AML Solution** (adds watchlist screening)
- Name it: `kyc-enhanced-sweepstakes-5000`
- **Save** → copy the new Template ID
- **Save this** → `PERSONA_TEMPLATE_ID_ENHANCED`

## 4. Webhook + signing secret
- Left sidebar → **Integration → Webhooks** → **Add webhook**
- Endpoint URL: `https://wah-lah.com/api/compliance/persona/webhook`
- Events to subscribe: `inquiry.completed`, `inquiry.failed`
- After save → click into the webhook → **Reveal signing secret** → copy
- **Save this** → `PERSONA_WEBHOOK_SECRET`

## 5. Push the keys to Fly.io
Once you have all 4, run from your local machine (or paste back here and I'll do it next time you give me a Fly token):
```bash
flyctl secrets set --app wah-lah \
  PERSONA_API_KEY='persona_sandbox_...' \
  PERSONA_TEMPLATE_ID_BASIC='itmpl_...' \
  PERSONA_TEMPLATE_ID_ENHANCED='itmpl_...' \
  PERSONA_WEBHOOK_SECRET='wbhsec_...' \
  PERSONA_ENVIRONMENT='sandbox'
```

That's it. The code at `/app/backend/services/compliance/persona.py` auto-detects the env vars and flips `PERSONA_ENABLED=True` on next deploy. Redemptions ≥$500 will trigger Basic, ≥$5000 will trigger Enhanced.

## 6. Going to Production
When you're ready for real verifications:
1. Persona dashboard → **Organization → Billing** → pick a plan
2. Switch the env selector top-left to **Production**
3. Repeat steps 2–4 in Production env (separate API key, separate templates, separate webhook secret)
4. Redeploy with `PERSONA_ENVIRONMENT=production` + the new prod values

## 7. Local testing tip
If you ever want to test webhooks against your laptop, install `ngrok`, run `ngrok http 8001`, and use the `https://xxxx.ngrok.io/api/compliance/persona/webhook` URL in the Persona dashboard webhook config. ngrok inspector lets you replay payloads without making fresh inquiries.
