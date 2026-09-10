/**
 * AdminDailyOps.jsx — the operator's daily loop in one tab.
 * Reconcile Cash App/Chime -> work the distributor queue -> answer tickets.
 * Payouts/KYC/AML live in the Ops/Pool/Alerts (compliance) tab.
 */
import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Zap, DollarSign, MessageCircle, RefreshCw, Check, X, RotateCcw, Ban } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "https://api.wah-lah.com";
const API = `${BACKEND_URL}/api`;

/* ---------------- Reconcile ---------------- */
const ReconcilePanel = () => {
  const [form, setForm] = useState({
    user_email: "", amount_usd: "", source: "cashapp", receipt: "",
    platform: "", note: "", apply_fee: true,
  });
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setResult(null);
    try {
      const { data } = await axios.post(`${API}/admin/cashtag/reconcile`, {
        ...form, amount_usd: Number(form.amount_usd),
        platform: form.platform || undefined,
      });
      setResult(data);
      toast.success(data.duplicate ? "Duplicate receipt — no double credit" : "Deposit reconciled");
      if (!data.duplicate) setForm((f) => ({ ...f, amount_usd: "", receipt: "", note: "" }));
    } catch (err) {
      toast.error(err.response?.data?.detail || "Reconcile failed");
    } finally {
      setBusy(false);
    }
  };

  const set = (k) => (e) => setForm((f) => ({
    ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value,
  }));

  return (
    <section className="ops-panel" data-testid="ops-reconcile">
      <div className="section-header">
        <h2><DollarSign size={20} /> Reconcile Cash App / Chime</h2>
        <p>Confirm the payment in the provider app first — then credit the player. Idempotent on receipt.</p>
      </div>
      <form className="ops-form" onSubmit={submit}>
        <div className="form-group"><label>Player email</label>
          <input value={form.user_email} onChange={set("user_email")} required placeholder="player@email.com" data-testid="reconcile-email" /></div>
        <div className="form-row-2">
          <div className="form-group"><label>Amount USD</label>
            <input type="number" step="0.01" min="0" value={form.amount_usd} onChange={set("amount_usd")} required data-testid="reconcile-amount" /></div>
          <div className="form-group"><label>Source</label>
            <select value={form.source} onChange={set("source")} data-testid="reconcile-source">
              <option value="cashapp">Cash App</option>
              <option value="chime">Chime</option>
              <option value="cashtag">Cashtag</option>
            </select></div>
        </div>
        <div className="form-row-2">
          <div className="form-group"><label>Receipt / confirmation #</label>
            <input value={form.receipt} onChange={set("receipt")} placeholder="CA-…" data-testid="reconcile-receipt" /></div>
          <div className="form-group"><label>Game to fund (optional)</label>
            <input value={form.platform} onChange={set("platform")} placeholder="Fire Kirin — blank = balance only" data-testid="reconcile-platform" /></div>
        </div>
        <div className="form-group"><label>Note</label>
          <input value={form.note} onChange={set("note")} placeholder="verified in app" data-testid="reconcile-note" /></div>
        <label className="checkbox-label">
          <input type="checkbox" checked={!form.apply_fee}
            onChange={(e) => setForm((f) => ({ ...f, apply_fee: !e.target.checked }))} />
          <span className="checkbox-custom" /> Whale comp — waive the fee (0%, audited)
        </label>
        <button type="submit" className="btn-primary" disabled={busy} data-testid="reconcile-submit">
          {busy ? "Crediting…" : "Reconcile deposit"}
        </button>
      </form>
      {result && (
        <div className="ops-result" data-testid="reconcile-result">
          <div><span>Gross</span><strong>${Number(result.gross_usd || 0).toFixed(2)}</strong></div>
          <div><span>Fee</span><strong>${Number(result.fee_usd || 0).toFixed(2)}</strong></div>
          <div><span>Net credited</span><strong>${Number(result.net_usd || 0).toFixed(2)}</strong></div>
          <div><span>Pool</span><strong>{result.pool_transfer_status || "—"}</strong></div>
          {result.duplicate && <div className="ops-dupe">Duplicate receipt — original deposit kept, nothing double-credited.</div>}
        </div>
      )}
    </section>
  );
};

/* ---------------- Distributor queue ---------------- */
const DistributorPanel = () => {
  const [mode, setMode] = useState("auto");
  const [summary, setSummary] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [status, setStatus] = useState("awaiting_send");
  const [notes, setNotes] = useState({});

  const load = useCallback(async () => {
    try {
      const [s, q, m] = await Promise.all([
        axios.get(`${API}/ext/distributor/summary`),
        axios.get(`${API}/ext/distributor/queue`, { params: { status, limit: 100 } }),
        axios.get(`${API}/ext/distributor/settings`),
      ]);
      setSummary(s.data);
      setTasks(Array.isArray(q.data) ? q.data : q.data.tasks || []);
      setMode(m.data.mode || m.data.distribution_mode || "auto");
    } catch {
      toast.error("Failed to load distributor queue");
    }
  }, [status]);

  useEffect(() => { load(); }, [load]);

  const act = async (taskId, action) => {
    const note = notes[taskId] || "";
    try {
      const body = action === "retry" ? undefined : { note };
      const { data } = await axios.post(`${API}/ext/distributor/queue/${taskId}/${action}`, body);
      toast.success(data.message || "Done");
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Action failed");
    }
  };

  const flipMode = async () => {
    const next = mode === "auto" ? "manual" : "auto";
    if (!window.confirm(`Switch distribution to ${next.toUpperCase()} mode?`)) return;
    try {
      await axios.post(`${API}/ext/distributor/settings`, { mode: next });
      setMode(next);
      toast.success(`Mode: ${next}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Mode switch failed");
    }
  };

  return (
    <section className="ops-panel" data-testid="ops-distributor">
      <div className="section-header">
        <h2><Zap size={20} /> Distributor queue</h2>
        <p>
          Mode: <strong data-testid="dist-mode">{mode}</strong>
          {" "}<button type="button" className="btn-sm" onClick={flipMode} data-testid="dist-flip">
            Switch to {mode === "auto" ? "manual" : "auto"}
          </button>
        </p>
      </div>
      {summary && (
        <div className="ledger-summary">
          <div className="ledger-stat"><span className="ledger-stat-num">{summary.awaiting ?? summary.pending ?? 0}</span><span className="ledger-stat-label">Awaiting</span></div>
          <div className="ledger-stat"><span className="ledger-stat-num">{summary.overdue?.count ?? 0}</span><span className="ledger-stat-label">Overdue</span></div>
          <div className="ledger-stat"><span className="ledger-stat-num">{summary.today?.tasks_done ?? 0}</span><span className="ledger-stat-label">Done today</span></div>
        </div>
      )}
      <div className="ledger-filters">
        {["awaiting_send", "failed", "done", "cancelled"].map((st) => (
          <button key={st} type="button" className={`chip-btn ${status === st ? "active" : ""}`}
            onClick={() => setStatus(st)} data-testid={`dist-filter-${st}`}>
            {st.replace(/_/g, " ")}
          </button>
        ))}
        <button type="button" className="chip-btn" onClick={load} data-testid="dist-refresh">
          <RefreshCw size={13} /> Refresh
        </button>
      </div>
      {tasks.length === 0 ? (
        <div className="empty-state"><Zap size={40} /><p>Queue is clear</p></div>
      ) : (
        <div className="transactions-list">
          {tasks.map((t) => {
            const id = t.id || t._id || t.task_id;
            return (
              <div key={id} className="transaction-row" data-testid="dist-task">
                <div className="tx-details">
                  <span className="tx-game">{t.send_instruction || `Send ${t.platform_amount ?? t.amount_credits} to ${t.recipient_username} on ${t.platform}`}</span>
                  <span className="tx-sub">{t.user_email || ""}{t.deposit_id ? ` · dep ${String(t.deposit_id).slice(0, 8)}` : ""}{t.created_at ? ` · ${new Date(t.created_at).toLocaleString()}` : ""}</span>
                  {status === "awaiting_send" && (
                    <input className="ops-note" placeholder="Note (optional)"
                      value={notes[id] || ""} data-testid="dist-note"
                      onChange={(e) => setNotes((n) => ({ ...n, [id]: e.target.value }))} />
                  )}
                </div>
                <div className="tx-side ops-actions">
                  <span className="tx-amount">${Number(t.platform_amount ?? 0).toFixed(2)}</span>
                  {status === "awaiting_send" && (<>
                    <button type="button" className="btn-sm primary" data-testid="dist-confirm"
                      onClick={() => act(id, "confirm-sent")}><Check size={13} /> Sent</button>
                    <button type="button" className="btn-sm danger" data-testid="dist-fail"
                      onClick={() => act(id, "mark-failed")}><X size={13} /> Failed</button>
                  </>)}
                  {status === "failed" && (<>
                    <button type="button" className="btn-sm primary" data-testid="dist-retry"
                      onClick={() => act(id, "retry")}><RotateCcw size={13} /> Retry</button>
                    <button type="button" className="btn-sm danger" data-testid="dist-cancel"
                      onClick={() => act(id, "cancel")}><Ban size={13} /> Cancel</button>
                  </>)}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
};

/* ---------------- Tickets ---------------- */
const TicketsPanel = () => {
  const [tickets, setTickets] = useState([]);
  const [status, setStatus] = useState("");
  const [openId, setOpenId] = useState(null);
  const [drafts, setDrafts] = useState({});

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/admin/analytics/support-tickets`,
        status ? { params: { status } } : undefined);
      setTickets(data);
    } catch {
      toast.error("Failed to load tickets");
    }
  }, [status]);

  useEffect(() => { load(); }, [load]);

  const respond = async (ticketId) => {
    const message = (drafts[ticketId] || "").trim();
    if (!message) return;
    try {
      await axios.post(`${API}/admin/analytics/support-tickets/${ticketId}/respond`, { message });
      toast.success("Reply sent — player sees it in Concierge");
      setDrafts((d) => ({ ...d, [ticketId]: "" }));
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Reply failed");
    }
  };

  const close = async (ticketId) => {
    try {
      await axios.post(`${API}/admin/analytics/support-tickets/${ticketId}/close`);
      toast.success("Ticket closed");
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Close failed");
    }
  };

  return (
    <section className="ops-panel" data-testid="ops-tickets">
      <div className="section-header">
        <h2><MessageCircle size={20} /> Support tickets</h2>
        <p>Player threads + Genie escalations. Replies land in the player's Concierge tab.</p>
      </div>
      <div className="ledger-filters">
        {[["", "All"], ["open", "Open"], ["pending", "Replied"], ["closed", "Closed"]].map(([id, label]) => (
          <button key={id} type="button" className={`chip-btn ${status === id ? "active" : ""}`}
            onClick={() => setStatus(id)} data-testid={`ticket-filter-${id || "all"}`}>
            {label}
          </button>
        ))}
      </div>
      {tickets.length === 0 ? (
        <div className="empty-state"><MessageCircle size={40} /><p>No tickets here</p></div>
      ) : (
        <div className="transactions-list">
          {tickets.map((t) => (
            <div key={t.ticket_id} className="transaction-row" data-testid="ops-ticket">
              <div className="tx-details">
                <button type="button" className="concierge-ticket-head"
                  onClick={() => setOpenId(openId === t.ticket_id ? null : t.ticket_id)}
                  data-testid="ops-ticket-toggle">
                  <span className="tx-game">
                    {t.source === "genie" ? "🧞 " : ""}{t.subject}
                  </span>
                </button>
                <span className="tx-sub">{t.user_email} · {t.priority} · {t.created_at ? new Date(t.created_at).toLocaleString() : ""}</span>
                {openId === t.ticket_id && (
                  <div className="concierge-thread" data-testid="ops-ticket-thread">
                    <div className="concierge-thread-msg them"><p>{t.message}</p><span>player</span></div>
                    {t.genie_reply && (
                      <div className="concierge-thread-msg me"><p>{t.genie_reply}</p><span>genie (auto)</span></div>
                    )}
                    {(t.responses || []).map((r, i) => (
                      <div key={i} className="concierge-thread-msg me"><p>{r.message}</p><span>{r.by}</span></div>
                    ))}
                    <div className="ops-reply-row">
                      <input className="concierge-input" placeholder="Reply to player…"
                        value={drafts[t.ticket_id] || ""} data-testid="ops-ticket-reply"
                        onChange={(e) => setDrafts((d) => ({ ...d, [t.ticket_id]: e.target.value }))} />
                      <button type="button" className="btn-sm primary" data-testid="ops-ticket-send"
                        onClick={() => respond(t.ticket_id)}>Reply</button>
                      {t.status !== "closed" && (
                        <button type="button" className="btn-sm" data-testid="ops-ticket-close"
                          onClick={() => close(t.ticket_id)}>Close</button>
                      )}
                    </div>
                  </div>
                )}
              </div>
              <div className="tx-side">
                <span className={`badge tx-status-${t.status === "closed" ? "ok" : "wait"}`}>{t.status}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

const AdminDailyOps = () => {
  const [view, setView] = useState("reconcile");
  return (
    <div data-testid="admin-daily-ops">
      <div className="ledger-filters">
        <button type="button" data-testid="ops-view-reconcile"
          className={`chip-btn ${view === "reconcile" ? "active" : ""}`} onClick={() => setView("reconcile")}>
          <DollarSign size={14} /> Reconcile
        </button>
        <button type="button" data-testid="ops-view-distributor"
          className={`chip-btn ${view === "distributor" ? "active" : ""}`} onClick={() => setView("distributor")}>
          <Zap size={14} /> Distributor queue
        </button>
        <button type="button" data-testid="ops-view-tickets"
          className={`chip-btn ${view === "tickets" ? "active" : ""}`} onClick={() => setView("tickets")}>
          <MessageCircle size={14} /> Tickets
        </button>
      </div>
      {view === "reconcile" && <ReconcilePanel />}
      {view === "distributor" && <DistributorPanel />}
      {view === "tickets" && <TicketsPanel />}
    </div>
  );
};

export default AdminDailyOps;
