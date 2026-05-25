/**
 * AdminGiftCards.jsx — queue of pending gift card redemptions with fulfill / reject actions.
 */
import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { Gift, Check, X, RefreshCw, Clock, Mail } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const AdminGiftCards = () => {
  const [pending, setPending] = useState([]);
  const [loading, setLoading] = useState(false);
  const [codeFor, setCodeFor] = useState({});   // { [rid]: "CODE-HERE" }
  const [busyId, setBusyId] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/ext/giftcard/admin/pending`);
      setPending(data);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const fulfill = async (rid) => {
    const code = (codeFor[rid] || "").trim();
    if (code.length < 4) return alert("Paste the gift-card code first.");
    setBusyId(rid);
    try {
      await axios.post(`${API}/ext/giftcard/admin/fulfill/${rid}`, { code });
      setCodeFor((m) => ({ ...m, [rid]: "" }));
      await load();
    } catch (e) { alert(e.response?.data?.detail || "Failed"); }
    finally { setBusyId(""); }
  };

  const reject = async (rid) => {
    const reason = prompt("Reason for rejection (credits will be refunded):");
    if (!reason) return;
    setBusyId(rid);
    try {
      await axios.post(`${API}/ext/giftcard/admin/reject/${rid}`, { reason });
      await load();
    } catch (e) { alert(e.response?.data?.detail || "Failed"); }
    finally { setBusyId(""); }
  };

  return (
    <div className="admin-giftcards" data-testid="admin-giftcards">
      <div className="admin-gc-header">
        <div>
          <h3><Gift size={18} /> Pending Gift Cards</h3>
          <p className="admin-gc-sub">Queue of cards awaiting manual code fulfillment.</p>
        </div>
        <button
          className="admin-gc-refresh"
          onClick={load}
          disabled={loading}
          data-testid="admin-gc-refresh"
        >
          <RefreshCw size={14} className={loading ? "is-spinning" : ""} /> Reload
        </button>
      </div>

      {pending.length === 0 && (
        <div className="admin-gc-empty" data-testid="admin-gc-empty">
          No pending cards. Shop is clean, Boss.
        </div>
      )}

      <div className="admin-gc-list">
        {pending.map((r) => (
          <div key={r.id} className="admin-gc-card" data-testid={`admin-gc-card-${r.id}`}>
            <div className="agc-top">
              <div className="agc-brand">
                <Gift size={14} /> {r.brand_label}
                <span className="agc-amount">${r.amount_usd}</span>
              </div>
              <div className="agc-meta">
                <Clock size={12} /> {new Date(r.created_at).toLocaleString()}
              </div>
            </div>
            <div className="agc-who">
              <span className="agc-chip">{r.user_email}</span>
              <span className="agc-arrow">→</span>
              <span className="agc-chip agc-recipient"><Mail size={10} /> {r.recipient_email}</span>
            </div>
            <div className="agc-actions">
              <input
                type="text"
                placeholder="Paste gift card code"
                value={codeFor[r.id] || ""}
                onChange={(e) => setCodeFor((m) => ({ ...m, [r.id]: e.target.value }))}
                data-testid={`agc-code-${r.id}`}
                disabled={busyId === r.id}
              />
              <button
                className="agc-fulfill"
                onClick={() => fulfill(r.id)}
                disabled={busyId === r.id}
                data-testid={`agc-fulfill-${r.id}`}
              >
                <Check size={14} /> Fulfill
              </button>
              <button
                className="agc-reject"
                onClick={() => reject(r.id)}
                disabled={busyId === r.id}
                data-testid={`agc-reject-${r.id}`}
              >
                <X size={14} /> Reject
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AdminGiftCards;
