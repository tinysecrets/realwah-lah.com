import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Trophy, Plus, Search, Crown, Ban, CircleCheck, RefreshCw } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "https://api.wah-lah.com";
const API = `${BACKEND_URL}/api`;

const STATUS_BADGE = {
  upcoming: "inactive",
  live: "active",
  drawing: "active",
  concluded: "inactive",
  cancelled: "inactive",
};

function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function AdminCompetition() {
  const [comps, setComps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState("list"); // list | create
  const [selected, setSelected] = useState(null); // summary payload
  const [summary, setSummary] = useState(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    name: "Million Dollar Sweepstakes",
    prize_usd: "1000000",
    status: "live",
    starts_at: "",
    draws_at: "",
    entry_per_purchase_usd: "1",
    entry_amoe_daily: "1",
  });

  const fetchList = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/admin/competition`);
      setComps(Array.isArray(data) ? data : []);
    } catch {
      toast.error("Failed to load competitions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchList(); }, [fetchList]);

  const openSummary = async (comp) => {
    setSelected(comp);
    setSummary(null);
    try {
      const { data } = await axios.get(`${API}/admin/competition/${comp.id}/summary`);
      setSummary(data);
    } catch {
      toast.error("Failed to load summary");
    }
  };

  const createCompetition = async (e) => {
    e.preventDefault();
    setBusy(true);
    const payload = {
      name: form.name,
      prize_usd: parseFloat(form.prize_usd || "0"),
      status: form.status,
      starts_at: form.starts_at || undefined,
      draws_at: form.draws_at || undefined,
      rules: {
        entry_per_purchase_usd: parseFloat(form.entry_per_purchase_usd || "1"),
        entry_amoe_daily: parseInt(form.entry_amoe_daily || "1", 10),
      },
    };
    try {
      await axios.post(`${API}/admin/competition`, payload);
      toast.success("Competition created");
      setView("list");
      setForm({ ...form, starts_at: "", draws_at: "" });
      fetchList();
    } catch {
      toast.error("Failed to create competition");
    } finally {
      setBusy(false);
    }
  };

  const setStatus = async (comp, status) => {
    setBusy(true);
    try {
      await axios.post(`${API}/admin/competition/${comp.id}/update`, { status });
      toast.success(`Competition ${status}`);
      fetchList();
    } catch {
      toast.error("Update failed");
    } finally {
      setBusy(false);
    }
  };

  const runDraw = async (comp) => {
    if (!window.confirm("Run the weighted draw now? This selects the grand prize winner and is irreversible once concluded.")) return;
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/admin/competition/${comp.id}/draw`);
      if (data.already_drawn) {
        toast.info("Already drawn");
      } else {
        const w = data.winner || {};
        toast.success(`Winner: ${w.name || w.email || "selected"}`);
      }
      fetchList();
      if (selected?.id === comp.id) openSummary(comp);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Draw failed");
    } finally {
      setBusy(false);
    }
  };

  const markPaid = async (comp) => {
    setBusy(true);
    try {
      await axios.post(`${API}/admin/competition/${comp.id}/prize-paid`);
      toast.success("Prize marked paid");
      fetchList();
      if (selected?.id === comp.id) openSummary(comp);
    } catch {
      toast.error("Failed to mark prize paid");
    } finally {
      setBusy(false);
    }
  };

  const cancelComp = async (comp) => {
    if (!window.confirm("Cancel this competition? Entries stop and status becomes cancelled.")) return;
    setBusy(true);
    try {
      await axios.post(`${API}/admin/competition/${comp.id}/cancel`);
      toast.success("Competition cancelled");
      fetchList();
    } catch {
      toast.error("Cancel failed");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="admin-section" style={{ opacity: 0.6 }}>Loading competitions…</div>;
  }

  return (
    <div className="admin-section">
      <div className="section-header">
        <h2>Million Dollar Competition</h2>
        <div style={{ display: "flex", gap: 10 }}>
          <button className="btn-primary" onClick={() => setView(view === "create" ? "list" : "create")}>
            {view === "create" ? <Search size={14} style={{ verticalAlign: -2 }} /> : <Plus size={14} style={{ verticalAlign: -2 }} />}
            {view === "create" ? " List" : " New Competition"}
          </button>
        </div>
      </div>

      {view === "create" ? (
        <form onSubmit={createCompetition} className="admin-section" style={{ maxWidth: 560 }}>
          <div className="form-group">
            <label>Name</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Prize (USD)</label>
              <input type="number" min="0" value={form.prize_usd} onChange={(e) => setForm({ ...form, prize_usd: e.target.value })} required />
            </div>
            <div className="form-group">
              <label>Status</label>
              <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                <option value="upcoming">Upcoming</option>
                <option value="live">Live</option>
              </select>
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Starts (ISO, optional)</label>
              <input placeholder="YYYY-MM-DDTHH:MM:SS" value={form.starts_at} onChange={(e) => setForm({ ...form, starts_at: e.target.value })} />
            </div>
            <div className="form-group">
              <label>Draws at (ISO, optional)</label>
              <input placeholder="YYYY-MM-DDTHH:MM:SS" value={form.draws_at} onChange={(e) => setForm({ ...form, draws_at: e.target.value })} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Entries per $1</label>
              <input type="number" min="0.01" step="0.01" value={form.entry_per_purchase_usd} onChange={(e) => setForm({ ...form, entry_per_purchase_usd: e.target.value })} />
            </div>
            <div className="form-group">
              <label>Free entries / AMOE daily</label>
              <input type="number" min="1" value={form.entry_amoe_daily} onChange={(e) => setForm({ ...form, entry_amoe_daily: e.target.value })} />
            </div>
          </div>
          <button className="btn-primary" type="submit" disabled={busy}>{busy ? "Creating…" : "Create Competition"}</button>
        </form>
      ) : (
        <>
          <div className="data-table">
            <table>
              <thead>
                <tr><th>Name</th><th>Prize</th><th>Status</th><th>Starts</th><th>Draws</th><th>Winner</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {comps.length === 0 && (
                  <tr><td colSpan={7} style={{ opacity: 0.6 }}>No competitions yet. Create the first one.</td></tr>
                )}
                {comps.map((comp) => (
                  <tr key={comp.id}>
                    <td>{comp.name} <span style={{ fontSize: 11, opacity: 0.5 }}>#{comp.id?.slice(0, 8)}</span></td>
                    <td>${Number(comp.prize_usd || 0).toLocaleString()}</td>
                    <td><span className={`badge ${STATUS_BADGE[comp.status] || "inactive"}`}>{comp.status}</span></td>
                    <td>{fmtDate(comp.starts_at)}</td>
                    <td>{fmtDate(comp.draws_at)}</td>
                    <td>{comp.winner ? `${comp.winner.name || ""}${comp.prize_status ? ` · ${comp.prize_status}` : ""}` : "—"}</td>
                    <td>
                      <button className="btn-sm" onClick={() => openSummary(comp)}>Summary</button>
                      {comp.status === "upcoming" && <button className="btn-sm primary" disabled={busy} onClick={() => setStatus(comp, "live")}>Go Live</button>}
                      {comp.status === "live" && <button className="btn-sm primary" disabled={busy} onClick={() => runDraw(comp)}>Run Draw</button>}
                      {comp.status === "concluded" && comp.winner && <button className="btn-sm" disabled={busy} onClick={() => markPaid(comp)}>Mark Paid</button>}
                      {!(comp.status === "concluded" || comp.status === "cancelled") && (
                        <button className="btn-sm danger" disabled={busy} onClick={() => cancelComp(comp)}>Cancel</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {selected && summary && (
        <div className="modal-overlay" onClick={() => { setSelected(null); setSummary(null); }}>
          <div className="modal-content comp-admin-detail" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => { setSelected(null); setSummary(null); }}>×</button>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              {summary.competition.winner ? <Crown size={20} style={{ color: "#e8b854" }} /> : <Trophy size={20} style={{ color: "#e8b854" }} />}
              <h2 style={{ margin: 0 }}>{summary.competition.name}</h2>
            </div>
            <p style={{ opacity: 0.7, marginTop: 0 }}>
              ${Number(summary.competition.prize_usd || 0).toLocaleString()} · {summary.competition.status}
              {summary.competition.winner && summary.competition.winner.name ? ` · Winner: ${summary.competition.winner.name}` : ""}
            </p>

            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", margin: "10px 0 16px" }}>
              <div><span style={{ fontSize: 22, fontWeight: 700, color: "#e8b854" }}>{summary.totals.total_entries || 0}</span> <span style={{ opacity: 0.6, fontSize: 12 }}>entries</span></div>
              <div><span style={{ fontSize: 22, fontWeight: 700, color: "#e8b854" }}>{summary.totals.total_players || 0}</span> <span style={{ opacity: 0.6, fontSize: 12 }}>players</span></div>
            </div>

            <h4 style={{ marginBottom: 8 }}>Leaderboard</h4>
            <div className="data-table">
              <table>
                <thead><tr><th>#</th><th>Email</th><th>Entries</th></tr></thead>
                <tbody>
                  {summary.leaderboard && summary.leaderboard.length > 0 ? summary.leaderboard.map((row) => (
                    <tr key={row.rank}>
                      <td>{row.rank}</td>
                      <td>{row.name}</td>
                      <td>{row.entries.toLocaleString()}</td>
                    </tr>
                  )) : (
                    <tr><td colSpan={3} style={{ opacity: 0.6 }}>No entries yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
              {summary.competition.status === "live" && (
                <button className="btn-primary" disabled={busy} onClick={() => runDraw(selected)}>
                  <Crown size={14} style={{ verticalAlign: -2 }} /> Run Draw
                </button>
              )}
              {summary.competition.winner && !summary.competition.prize_status && (
                <button className="btn-sm primary" disabled={busy} onClick={() => markPaid(selected)}>
                  <CircleCheck size={14} style={{ verticalAlign: -2 }} /> Mark Prize Paid
                </button>
              )}
              {summary.competition.status === "upcoming" && (
                <button className="btn-sm primary" disabled={busy} onClick={() => setStatus(selected, "live")}>
                  <RefreshCw size={14} style={{ verticalAlign: -2 }} /> Go Live
                </button>
              )}
              {!(summary.competition.status === "concluded" || summary.competition.status === "cancelled") && (
                <button className="btn-sm danger" disabled={busy} onClick={() => cancelComp(selected)}>
                  <Ban size={14} style={{ verticalAlign: -2 }} /> Cancel
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}