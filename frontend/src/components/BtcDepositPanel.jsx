/**
 * BtcDepositPanel.jsx — renders the Bitcoin deposit instructions + live status
 * for a checkout/deposit created via POST /checkout/create.
 *
 * Props:
 *  - deposit: { deposit_id, btc_address, amount_usd, btc_satoshis, btc_usd_rate,
 *               confirmation_required }
 *  - onCompleted: () => void  (called once the deposit is confirmed + credited)
 *  - onCancel: () => void     (optional, hides the panel)
 */
import React, { useEffect, useRef, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Copy, Check, RefreshCw, X } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || "https://api.wah-lah.com"}/api`;

const btcAmount = (sats) => (sats / 1e8).toFixed(8);

const BtcDepositPanel = ({ deposit, onCompleted, onCancel }) => {
  const [status, setStatus] = useState(deposit?.status || "pending");
  const [confirmations, setConfirmations] = useState(0);
  const [copied, setCopied] = useState(false);
  const [expired, setExpired] = useState(false);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!deposit?.deposit_id) return;
    let stop = false;

    const poll = async () => {
      try {
        const { data } = await axios.get(`${API}/checkout/status/${deposit.deposit_id}`);
        if (stop) return;
        setStatus(data.status);
        setConfirmations(data.confirmations || 0);
        if (data.status === "completed") {
          if (timerRef.current) clearInterval(timerRef.current);
          toast.success("Bitcoin deposit confirmed! Credits added.");
          onCompleted && onCompleted();
        } else if (data.status === "expired") {
          setExpired(true);
          if (timerRef.current) clearInterval(timerRef.current);
        }
      } catch { /* transient — keep polling */ }
    };

    poll();
    timerRef.current = setInterval(poll, 6000);
    return () => { stop = true; if (timerRef.current) clearInterval(timerRef.current); };
  }, [deposit?.deposit_id, onCompleted]);

  if (expired) {
    return (
      <div className="payment-box crypto-box" data-testid="btc-deposit-expired">
        <h3 style={{ fontSize: "18px", color: "var(--neon-pink)" }}>Deposit Expired</h3>
        <p className="note">This deposit address is no longer active. Please start a new deposit.</p>
        {onCancel && <button className="btn-primary" onClick={onCancel}>Start Over</button>}
      </div>
    );
  }

  const confirmed = status === "completed";

  return (
    <div className="payment-box crypto-box" data-testid="btc-deposit-panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ fontSize: "18px", marginBottom: "16px", color: "var(--neon-cyan)" }}>
          {confirmed ? "✅ Deposit Confirmed" : "Complete Your Bitcoin Deposit"}
        </h3>
        {onCancel && (
          <button
            className="copy-btn"
            onClick={onCancel}
            aria-label="Close"
            disabled={confirmed}
          >
            <X size={16} />
          </button>
        )}
      </div>

      {!confirmed && (
        <>
          <div className="qr-code">
            <img
              src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${deposit.btc_address}`}
              alt="BTC QR"
            />
          </div>

          <div className="amount-summary">
            <strong>${Number(deposit.amount_usd).toFixed(2)}</strong>
            <span className="btc-sub">≈ {btcAmount(deposit.btc_satoshis)} BTC</span>
          </div>

          <div className="wallet-address" data-testid="btc-deposit-address">
            <span style={{ fontSize: "10px", wordBreak: "break-all" }}>{deposit.btc_address}</span>
            <button
              className="copy-btn"
              data-testid="copy-btc-address"
              onClick={() => {
                navigator.clipboard.writeText(deposit.btc_address);
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
                toast.success("Copied!");
              }}
            >
              {copied ? <Check size={16} /> : <Copy size={16} />}
            </button>
          </div>

          <p className="note" style={{ marginTop: "18px", fontWeight: 600 }}>
            Send exactly {btcAmount(deposit.btc_satoshis)} BTC ({Number(deposit.amount_usd).toFixed(2)} USD)
          </p>
          <p className="note">
            Your credits are added automatically once the payment confirms on-chain
            ({deposit.confirmation_required ?? 1} network confirmation
            {deposit.confirmation_required > 1 ? "s" : ""}). Please send the exact amount.
          </p>

          <div className="status-line">
            <RefreshCw size={14} className="status-spin" />
            <span>Waiting for payment... {confirmations > 0 ? `${confirmations} confirmations` : ""}</span>
          </div>
        </>
      )}

      {confirmed && (
        <p className="note" style={{ fontWeight: 600 }}>Your Sweepstakes package has been funded. Enjoy!</p>
      )}
    </div>
  );
};

export default BtcDepositPanel;
