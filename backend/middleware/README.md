# Game Middleware System - Complete Documentation

## 🎯 Overview

This middleware automates game credit allocation and Bitcoin payouts by integrating with game platform agent backends (Fire Kirin, Panda Master, Orion Stars, Game Vault).

## 📁 Architecture

```
middleware/
├── session_manager.py       # Maintains 24/7 authenticated sessions
├── backend_bridge.py         # API + Headless browser automation
├── payout_engine.py          # Bitcoin withdrawal processing
├── webhook_handler.py        # Processes BTC payment confirmations
├── game_middleware_manager.py # Coordinates all components
└── README.md                 # This file

config/
└── platforms.json            # Multi-platform configuration

models/
└── transaction_models.py     # Database models
```

## 🚀 Quick Start

### 1. Configure Platforms

Edit `/app/backend/config/platforms.json`:

```json
{
  "platforms": [
    {
      "id": "fire_kirin",
      "enabled": true,  // ← Set to true when you have credentials
      "agent_url": "https://agent.firekirin.xyz",
      "credentials": {
        "username_env": "FIREKIRIN_AGENT_USER",
        "password_env": "FIREKIRIN_AGENT_PASS"
      }
    }
  ]
}
```

### 2. Set Environment Variables

Add to `/app/backend/.env`:

```bash
# Game Platform Credentials
FIREKIRIN_AGENT_USER=your_agent_username
FIREKIRIN_AGENT_PASS=your_agent_password

PANDAMASTER_AGENT_USER=your_agent_username
PANDAMASTER_AGENT_PASS=your_agent_password

ORIONSTARS_AGENT_USER=your_agent_username
ORIONSTARS_AGENT_PASS=your_agent_password

GAMEVAULT_AGENT_USER=your_agent_username
GAMEVAULT_AGENT_PASS=your_agent_password

# Bitcoin Gateway
BTC_GATEWAY_API_URL=https://your-btcpay-server.com
BTC_GATEWAY_API_KEY=your_btcpay_api_key
BTCPAY_STORE_ID=your_store_id
BTC_WEBHOOK_SECRET=your_webhook_secret
```

### 3. Restart Backend

```bash
sudo supervisorctl restart backend
```

## 📖 Component Details

### 1. Session Manager

**Purpose**: Maintains authenticated sessions with game platforms 24/7

**Features**:
- Automatic login with CSRF token handling
- Session cookie/JWT token management
- Background heartbeat every 5 minutes
- Auto-reconnect on session expiry

**Usage**:
```python
session_manager = SessionManager(platform_config)
success, msg = session_manager.login()

# Make authenticated requests
success, response = session_manager.make_request(
    "POST",
    "/api/agent/recharge",
    data={"player_id": "user123", "amount": 100}
)
```

### 2. Backend Bridge

**Purpose**: Automates interactions with game agent panels

**Modes**:
- **API Mode** (Primary): Direct API calls via SessionManager
- **Headless Mode** (Fallback): Playwright browser automation

**Key Functions**:
```python
bridge = BackendBridge(platform_config)
await bridge.initialize()

# Add credits
success, msg, tx_id = await bridge.recharge_user(
    player_id="user123",
    amount=100.0,
    game_id="fire_kirin"
)

# Check balance
success, balance = await bridge.get_player_balance(
    player_id="user123",
    game_id="fire_kirin"
)

# Deduct credits (for withdrawals)
success, msg, tx_id = await bridge.deduct_credits(
    player_id="user123",
    amount=50.0,
    game_id="fire_kirin"
)
```

### 3. Payout Engine

**Purpose**: Handles Bitcoin withdrawals with approval workflow

**Features**:
- Automatic payouts under threshold ($500 default)
- Manual approval for large amounts
- Integration with BTCPay Server / CoinGate
- Double-spending prevention

**Workflow**:
1. User requests withdrawal
2. If amount < threshold → Immediate payout
3. If amount >= threshold → Pending approval
4. Admin approves/rejects via API
5. BTC sent to user's wallet

**Admin Endpoints**:
```bash
# Get pending payouts
GET /api/admin/payouts/pending

# Approve payout
POST /api/admin/payouts/{payout_id}/approve

# Reject payout
POST /api/admin/payouts/{payout_id}/reject
Body: {"reason": "Suspicious activity"}
```

### 4. Webhook Handler

**Purpose**: Processes incoming Bitcoin payment confirmations

**Flow**:
1. BTCPay/CoinGate sends webhook on payment confirmation
2. Verify signature (HMAC)
3. Check payment status (confirmed/paid)
4. Extract user_id, game_id, amount from metadata
5. Call BackendBridge to allocate credits
6. Log transaction in database
7. Update user's local balance

**Webhook Endpoint**:
```
POST /api/webhooks/bitcoin
```

**BTCPay Webhook Setup**:
1. Go to BTCPay Store Settings → Webhooks
2. Add webhook URL: `https://your-domain.com/api/webhooks/bitcoin`
3. Select events: `InvoiceSettled`, `InvoicePaid`
4. Set secret (save to `BTC_WEBHOOK_SECRET`)

### 5. Game Middleware Manager

**Purpose**: Central coordinator for all components

**Responsibilities**:
- Initialize all platform bridges
- Coordinate credit allocation
- Process withdrawal requests
- Provide system status

**Usage**:
```python
manager = GameMiddlewareManager("config/platforms.json", db)
await manager.initialize()

# Allocate credits
success, msg = await manager.allocate_credits(
    user_id="user123",
    game_id="fire_kirin",
    platform_id="fire_kirin",
    player_id="FK_user123",
    amount_usd=100.0
)

# Process withdrawal
success, msg, payout_id = await manager.process_withdrawal(
    user_id="user123",
    game_id="fire_kirin",
    platform_id="fire_kirin",
    player_id="FK_user123",
    amount_usd=50.0,
    credits=50.0,
    btc_address="bc1q...",
    user_email="user@example.com"
)
```

## 🔄 Complete User Flows

### Deposit Flow (Inbound)

```
User makes BTC payment
↓
BTCPay confirms payment (1+ confirmations)
↓
Webhook sent to /api/webhooks/bitcoin
↓
WebhookHandler verifies signature
↓
Extract user_id, game_id, amount from invoice metadata
↓
Get user's game account credentials from database
↓
BackendBridge.recharge_user() called
↓
SessionManager makes authenticated API call to game platform
↓
Game platform adds credits to player account
↓
Transaction logged in database
↓
User's local balance updated
↓
✅ User receives credits in game
```

### Withdrawal Flow (Outbound)

```
User requests withdrawal via /api/withdraw/request
↓
Check user has sufficient balance in game
↓
BackendBridge.deduct_credits() removes credits from game
↓
PayoutEngine.initiate_payout() called
↓
If amount < $500:
  → BTCPay/CoinGate API called immediately
  → BTC sent to user's wallet
  → Status: COMPLETED
↓
If amount >= $500:
  → Payout saved as PENDING_APPROVAL
  → Admin notified
  → Wait for admin action
  ↓
  Admin approves:
    → BTCPay/CoinGate API called
    → BTC sent
    → Status: APPROVED → COMPLETED
  ↓
  Admin rejects:
    → Credits remain deducted (manual intervention needed)
    → Status: REJECTED
```

## 🛠️ Configuration Options

### Platform Config

```json
{
  "id": "fire_kirin",
  "enabled": true,
  "agent_url": "https://agent.firekirin.xyz",
  "login_endpoint": "/api/auth/login",
  "recharge_endpoint": "/api/agent/recharge",
  "balance_endpoint": "/api/agent/balance",
  "deduct_endpoint": "/api/agent/deduct",
  "use_headless": false,  // Set true to use browser automation
  "credentials": {
    "username_env": "FIREKIRIN_AGENT_USER",
    "password_env": "FIREKIRIN_AGENT_PASS"
  },
  "rate_limit": {
    "requests_per_minute": 30,
    "retry_attempts": 3,
    "retry_delay_seconds": 5
  }
}
```

### Bitcoin Config

```json
{
  "gateway_type": "btcpay",  // or "coingate"
  "webhook_secret_env": "BTC_WEBHOOK_SECRET",
  "min_confirmations": 1,
  "payout_approval_threshold_usd": 500,
  "manual_approval_required": true
}
```

## 🔐 Security Best Practices

1. **Environment Variables**: Never hardcode credentials
2. **Webhook Signatures**: Always verify HMAC signatures
3. **HTTPS Only**: Use SSL for all API calls
4. **Session Encryption**: Use strong JWT secrets
5. **Rate Limiting**: Prevent API abuse
6. **Transaction Logging**: Audit all credit transfers
7. **Manual Approval**: For large payouts (>$500)

## 📊 Database Collections

### game_transactions
```json
{
  "transaction_id": "uuid",
  "user_id": "user_id",
  "game_id": "fire_kirin",
  "platform_id": "fire_kirin",
  "transaction_type": "credit_allocation",
  "amount_usd": 100.0,
  "credits": 100.0,
  "status": "completed",
  "payment_method": "bitcoin",
  "btc_tx_hash": "abc123...",
  "platform_tx_id": "FK_TX_456",
  "created_at": "2026-04-06T12:00:00Z"
}
```

### pending_payouts
```json
{
  "payout_id": "uuid",
  "user_id": "user_id",
  "amount_usd": 600.0,
  "btc_address": "bc1q...",
  "status": "pending_approval",
  "created_at": "2026-04-06T12:00:00Z",
  "approved_by": null
}
```

## 🐛 Troubleshooting

### Issue: Middleware not initializing

**Solution**: Check logs for specific error
```bash
tail -100 /var/log/supervisor/backend.err.log | grep -i middleware
```

### Issue: Login failing for platform

**Symptoms**: "Authentication failed" in logs

**Solutions**:
1. Verify credentials in `.env`
2. Check if platform changed login endpoint
3. Try headless mode: `"use_headless": true`
4. Check platform rate limits

### Issue: Credits not allocating

**Symptoms**: Payment confirmed but no credits in game

**Debug Steps**:
1. Check webhook logs: `grep -i webhook /var/log/supervisor/backend.err.log`
2. Verify user has game account configured
3. Check BackendBridge connection status: `GET /api/admin/middleware/status`
4. Test API manually with curl

### Issue: Payout stuck in pending

**Solution**: Admin must approve via:
```bash
POST /api/admin/payouts/{payout_id}/approve
```

## 📈 Monitoring & Health Checks

### System Status Endpoint
```bash
GET /api/admin/middleware/status
```

**Response**:
```json
{
  "initialized": true,
  "bridges": {
    "fire_kirin": {
      "platform_name": "Fire Kirin",
      "is_authenticated": true,
      "last_heartbeat": "2026-04-06T12:00:00Z"
    }
  },
  "payout_engine": "initialized",
  "webhook_handler": "initialized"
}
```

## 🚨 Error Handling

All components implement comprehensive error handling:

- **Retry Logic**: 3 attempts with exponential backoff
- **Graceful Degradation**: System continues if some platforms fail
- **Transaction Rollback**: On critical failures (work in progress)
- **Alert Logging**: All errors logged with context

## 📚 API Reference

### User Endpoints

**Request Withdrawal**
```
POST /api/withdraw/request
Body: {
  "game_id": "fire_kirin",
  "amount_usd": 100.0,
  "btc_address": "bc1q..."
}
```

### Admin Endpoints

**Get Pending Payouts**
```
GET /api/admin/payouts/pending
```

**Approve Payout**
```
POST /api/admin/payouts/{payout_id}/approve
```

**Reject Payout**
```
POST /api/admin/payouts/{payout_id}/reject
Body: {"reason": "Fraud detection"}
```

**Get Middleware Status**
```
GET /api/admin/middleware/status
```

## 🎓 Next Steps

1. **Enable Platforms**: Set `"enabled": true` in platforms.json
2. **Add Credentials**: Configure environment variables
3. **Test Webhooks**: Use BTCPay test mode
4. **Monitor Logs**: Watch for successful logins
5. **Process Test Transaction**: Small deposit to verify flow
6. **Set Up Admin Alerts**: For pending payouts >$500

## 📞 Support

For issues or questions:
1. Check troubleshooting section above
2. Review logs: `/var/log/supervisor/backend.*.log`
3. Test with curl commands
4. Contact platform support for API documentation

---

**Built for Sugar City Sweeps** | Version 1.0
