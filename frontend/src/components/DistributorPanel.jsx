/**
 * DistributorPanel.jsx — self-service operator panel.
 *
 * Lets the operator (you) register your own distributor accounts per game
 * platform and route player deposits to them. Talks to the live
 * /ext/pool/* distributor-pool backend (the real credit-injection path).
 *
 * Credentials entered here are encrypted at rest in the vault (proxy_pool);
 * the API never returns the password. Passwords shown here are local-only.
 */
import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import {
  Plus, Pencil, Trash2, Unlock, Zap, RefreshCw, Activity,
  Server, ShieldCheck, AlertTriangle, CheckCircle2, CircleDollarSign,
  Users, Loader2, ExternalLink, Ban
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const STATUS_LABEL = {
  active: { label: "Active", cls: "st-active" },
  cooldown: { label: "Cooldown", cls: "st-cooldown" },
  locked: { label: "Locked", cls: "st-locked" },
  disabled: { label: "Disabled", cls: "st-disabled" },
};
const STATUS_CHOICES = ["active", "disabled"];

const DistributorPanel = () => {
  const [proxies, setProxies] = useState([]);
  const [hubs, setHubs] = useState([]);
  const [health, setHealth] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [matrix, setMatrix] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");

  // add/edit form state
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null); // proxy id or null (new)
  const [form, setForm] = useState({
    label: "", username: "", password: "", hub_type: "sugar_sweeps",
    base_url: "", supported_platforms: [], daily_cap: "", per_transfer_cap: "",
  });
  const [testForm, setTestForm] = useState({ recipient_username: "", amount: "", platform: "fire_kirin" });
  const [testBusy, setTestBusy] = useState(false);
  const [activeTab, setActiveTab] = useState("accounts");

  const getToken = () => (typeof document === "undefined" ? "" : "");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, h, hp, rd, mx] = await Promise.all([
        axios.get(`${API}/ext/pool/admin/proxies`),
        axios.get(`${API}/ext/pool/admin/hubs`),
        axios.get(`${API}/ext/pool/admin/health`),
        axios.get(`${API}/ext/pool/admin/launch-readiness`),
        axios.get(`${API}/ext/pool/admin/routing-matrix`),
      ]);
      setProxies(p.data || []);
      setHubs(h.data || []);
      setHealth(hp.data || null);
      setReadiness(rd.data || null);
      setMatrix(mx.data || []);
    } catch (e) {
      console.error("Distributor load failed", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const resetForm = () => {
    setForm({
      label: "", username: "", password: "", hub_type: "sugar_sweeps",
      base_url: "", supported_platforms: [], daily_cap: "", per_transfer_cap: "",
    });
    setEditing(null);
  };

  const openNew = () => { resetForm(); setShowForm(true); };
  const openEdit = (p) => {
    setEditing(p.id);
    setForm({
      label: p.label || "", username: p.username || "", password: "",
      hub_type: p.hub_type || "sugar_sweeps", base_url: p.base_url || "",
      supported_platforms: p.supported_platforms || [],
      daily_cap: p.daily_cap ? String(p.daily_cap) : "",
      per_transfer_cap: p.per_transfer_cap ? String(p.per_transfer_cap) : "",
    });
    setShowForm(true);
  };

  const togglePlatform = (slug) => {
    setForm((f) => ({
      ...f,
      supported_platforms: f.supported_platforms.includes(slug)
        ? f.supported_platforms.filter((s) => s !== slug)
        : [...f.supported_platforms, slug],
    }));
  };

  const save = async () => {
    if (!form.label || !form.username || (!editing && !form.password)) {
      return alert("Label, username, and password (new) are required.");
    }
    setBusy("save");
    const payload = {
      label: form.label,
      username: form.username,
      hub_type: form.hub_type,
      base_url: form.base_url || undefined,
      supported_platforms: form.supported_platforms,
      daily_cap: form.daily_cap ? parseFloat(form.daily_cap) : undefined,
      per_transfer_cap: form.per_transfer_cap ? parseFloat(form.per_transfer_cap) : undefined,
    };
    if (form.password) payload.password = form.password;
    try {
      if (editing) {
        await axios.patch(`${API}/ext/pool/admin/proxies/${editing}`, payload);
      } else {
        await axios.post(`${API}/ext/pool/admin/proxies`, payload);
      }
      setShowForm(false); resetForm(); await load();
    } catch (e) { alert(e.response?.data?.detail || "Save failed"); }
    finally { setBusy(""); }
  };

  const remove = async (p) => {
    if (!confirm(`Remove distributor "${p.label}"? This is irreversible.`)) return;
    setBusy(p.id);
    try { await axios.delete(`${API}/ext/pool/admin/proxies/${p.id}`); await load(); }
    catch (e) { alert(e.response?.data?.detail || "Delete failed"); }
    finally { setBusy(""); }
  };

  const unlock = async (p) => {
    if (!confirm(`Unlock distributor "${p.label}"?`)) return;
    setBusy(p.id);
    try { await axios.post(`${API}/ext/pool/admin/proxies/${p.id}/unlock`); await load(); }
    catch (e) { alert(e.response?.data?.detail || "Unlock failed"); }
    finally { setBusy(""); }
  };

  const pingOne = async (p) => {
    setBusy(p.id);
    try {
      const { data } = await axios.post(`${API}/ext/pool/admin/proxies/${p.id}/ping`);
      alert(`Ping: ${data.ok ? "OK ✓" : "FAIL ✗"}\n\n${data.message}`);
      await load();
    } catch (e) { alert(e.response?.data?.detail || "Ping failed"); }
    finally { setBusy(""); }
  };

  const pingAll = async () => {
    setBusy("pingall");
    try {
      const { data } = await axios.post(`${API}/ext/pool/admin/ping-all`);
      alert(`Ping all: ${data.passed}/${data.total} passed.`);
      await load();
    } catch (e) { alert(e.response?.data?.detail || "Ping all failed"); }
    finally { setBusy(""); }
  };

  const testTransfer = async (p) => {
    if (!testForm.recipient_username || !testForm.amount) return alert("Recipient + amount required.");
    setTestBusy(p.id);
    try {
      const { data } = await axios.post(`${API}/ext/pool/admin/proxies/${p.id}/test-transfer`, {
        recipient_username: testForm.recipient_username,
        amount: parseFloat(testForm.amount),
        platform: testForm.platform,
      });
      alert(`${data.ok ? "SUCCESS ✓" : "FAILED ✗"}\n${data.message}`);
    } catch (e) { alert(e.response?.data?.detail || "Test transfer failed"); }
    finally { setTestBusy(""); }
  };

  const allPlatforms = Array.from(new Set(
    (matrix || []).map((m) => m.platform).concat(hubs.flatMap((h) => h.supported_platforms || []))
  ));

  return (
    <div className="distributor-panel" data-testid="distributor-panel">
      <div className="dp-header">
        <div>
          <h3><Server size={18} /> Distributor Pool</h3>
          <p className="dp-sub">Your distributor accounts. Player deposits fund these, crediting the player's game on login.</p>
        </div>
        <div className="dp-actions">
          <button className="dp-refresh" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? "is-spinning" : ""} /> Reload
          </button>
          <button className="dp-add" onClick={openNew}>
            <Plus size={14} /> Add Distributor
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="dp-tabs">
        {[
          ["accounts", "Accounts", Server],
          ["readiness", "Launch Readiness", ShieldCheck],
          ["matrix", "Coverage", Users],
          ["test", "Test Transfer", Zap],
        ].map(([key, label, Icon]) => (
          <button
            key={key}
            className={`dp-tab ${activeTab === key ? "dp-tab-active" : ""}`}
            onClick={() => setActiveTab(key)}
          >
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>

      {/* Health summary */}
      {health && (
        <div className="dp-health">
          <span>Total <strong>{health.total}</strong></span>
          <span className="st-active">Active <strong>{health.active}</strong></span>
          <span className="st-cooldown">Cooldown <strong>{health.cooldown}</strong></span>
          <span className="st-locked">Locked <strong>{health.locked}</strong></span>
          <span className="st-disabled">Disabled <strong>{health.disabled}</strong></span>
          <span>Daily cap remaining <strong>${(health.daily_capacity_remaining ?? 0).toLocaleString()}</strong></span>
        </div>
      )}

      {/* ---------------------------- ACCOUNTS TAB ---------------------------- */}
      {activeTab === "accounts" && (
        <div className="dp-body">
          {proxies.length === 0 && !loading && (
            <div className="dp-empty">
              No distributor accounts yet. Add your first one to start funding player games.
            </div>
          )}

          <div className="dp-list">
            {proxies.map((p) => {
              const st = STATUS_LABEL[p.status] || STATUS_LABEL.active;
              return (
                <div key={p.id} className="dp-card">
                  <div className="dp-card-top">
                    <div className="dp-id">
                      <Server size={16} />
                      <div>
                        <div className="dp-name">
                          {p.label}
                          <span className={`dp-status ${st.cls}`}>{st.label}</span>
                        </div>
                        <div className="dp-meta">{p.hub_type} · {p.username} · {p.base_url}</div>
                      </div>
                    </div>
                    <div className="dp-card-actions">
                      <button className="icon-btn" title="Test login" onClick={() => pingOne(p)} disabled={busy === p.id}>
                        <Activity size={15} />
                      </button>
                      {p.status === "locked" || p.status === "cooldown" ? (
                        <button className="icon-btn" title="Unlock" onClick={() => unlock(p)} disabled={busy === p.id}>
                          <Unlock size={15} />
                        </button>
                      ) : null}
                      <button className="icon-btn" title="Edit" onClick={() => openEdit(p)} disabled={busy === p.id}>
                        <Pencil size={15} />
                      </button>
                      <button className="icon-btn danger" title="Delete" onClick={() => remove(p)} disabled={busy === p.id}>
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>

                  <div className="dp-cap">
                    <span>Balance <b>${(p.balance_cached || 0).toLocaleString()}</b></span>
                    <span>Sent today <b>${(p.daily_volume_sent || 0).toLocaleString()}</b> / ${(p.daily_cap || 0).toLocaleString()}</span>
                    <span>Per transfer <b>${(p.per_transfer_cap || 0).toLocaleString()}</b></span>
                    <span>Failures <b>{p.consecutive_failures || 0}</b></span>
                  </div>

                  <div className="dp-platforms">
                    {(p.supported_platforms || []).length === 0
                      ? <span className="dp-pl chip">All platforms</span>
                      : p.supported_platforms.map((pl) => <span key={pl} className="dp-pl chip">{pl}</span>)}
                  </div>

                  {p.lock_reason && <div className="dp-lock">Locked: {p.lock_reason}</div>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* --------------------------- READINESS TAB --------------------------- */}
      {activeTab === "readiness" && (
        <div className="dp-body">
          {readiness && (
            <div className={`dp-ready ${readiness.ready ? "ok" : "not"}`}>
              <CheckCircle2 size={20} />
              <span><strong>{readiness.ready ? "READY FOR LIVE TRAFFIC" : "Not ready"}</strong> — {readiness.summary}</span>
            </div>
          )}
          <div className="dp-ready-grid">
            {(readiness?.checks || []).map((c) => (
              <div key={c.name} className={`dp-ready-card ${c.ok ? "ok" : "warn"}`}>
                {c.ok ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
                <strong>{c.name}</strong>
                <p>{c.detail}</p>
              </div>
            ))}
          </div>
          <div className="dp-actions" style={{ marginTop: 12 }}>
            <button className="dp-add" onClick={pingAll} disabled={busy === "pingall"}>
              {busy === "pingall" ? <Loader2 size={14} className="is-spinning" /> : <Activity size={14} />} Ping All Distributors
            </button>
          </div>
        </div>
      )}

      {/* ---------------------------- COVERAGE TAB --------------------------- */}
      {activeTab === "matrix" && (
        <div className="dp-body">
          <div className="dp-matrix">
            <div className="dp-matrix-head">
              <span>Platform</span><span>Active coverage</span><span>Total</span><span>Distributors</span>
            </div>
            {(matrix || []).map((m) => (
              <div key={m.platform} className="dp-matrix-row">
                <span className="chip">{m.platform}</span>
                <span className={m.active_coverage >= 2 ? "ok-text" : "warn-text"}>
                  {m.active_coverage} {m.active_coverage >= 2 ? "✓" : "⚠"}
                </span>
                <span>{m.total_coverage}</span>
                <span className="dp-matrix-proxies">
                  {m.proxies.length === 0
                    ? <em>none</em>
                    : m.proxies.map((x) => (
                        <span key={x.id} className={`dp-mini ${x.status === "active" ? "ok" : "warn"}`}>
                          {x.label} (${(x.capacity_remaining || 0).toLocaleString()})
                        </span>
                      ))}
                </span>
              </div>
            ))}
            {matrix?.length === 0 && <div className="dp-empty">No platforms registered yet.</div>}
          </div>
          <p className="dp-hint">Requires ≥2 active distributors per platform for redundancy.</p>
        </div>
      )}

      {/* --------------------------- TEST TRANSFER TAB --------------------------- */}
      {activeTab === "test" && (
        <div className="dp-body">
          <div className="dp-test-form">
            <input
              placeholder="Player game username"
              value={testForm.recipient_username}
              onChange={(e) => setTestForm({ ...testForm, recipient_username: e.target.value })}
            />
            <input
              placeholder="Amount ($)"
              type="number"
              min="1"
              value={testForm.amount}
              onChange={(e) => setTestForm({ ...testForm, amount: e.target.value })}
            />
            <select
              value={testForm.platform}
              onChange={(e) => setTestForm({ ...testForm, platform: e.target.value })}
            >
              {allPlatforms.map((pl) => <option key={pl} value={pl}>{pl}</option>)}
            </select>
          </div>
          {testBusy && <p className="dp-hint"><Loader2 size={13} className="is-spinning" /> Testing…</p>}
          <div className="dp-list" style={{ marginTop: 12 }}>
            {proxies.map((p) => (
              <div key={p.id} className="dp-card">
                <div className="dp-card-top">
                  <div className="dp-id"><Server size={16} /><div>
                    <div className="dp-name">{p.label}</div>
                    <div className="dp-meta">{p.status} · ${(p.per_transfer_cap || 0).toLocaleString()} max</div>
                  </div></div>
                  <button className="dp-add" disabled={testBusy === p.id} onClick={() => testTransfer(p)}>
                    {testBusy === p.id ? <Loader2 size={14} className="is-spinning" /> : <Zap size={14} />} Send {testForm.amount ? `$${testForm.amount}` : ""}
                  </button>
                </div>
              </div>
            ))}
            {proxies.length === 0 && <div className="dp-empty">Add a distributor first.</div>}
          </div>
        </div>
      )}

      {/* ------------------------------ ADD / EDIT FORM ------------------------------ */}
      {showForm && (
        <div className="dp-modal-backdrop">
          <div className="dp-modal" data-testid="dp-modal">
            <div className="dp-modal-head">
              <h4>{editing ? "Edit Distributor" : "Add Distributor"}</h4>
              <button className="icon-btn" onClick={() => { setShowForm(false); resetForm(); }}>×</button>
            </div>

            <label className="dp-field">
              <span>Label</span>
              <input value={form.label} placeholder="My Fire Kirin account" onChange={(e) => setForm({ ...form, label: e.target.value })} />
            </label>

            <label className="dp-field">
              <span>Hub type</span>
              <select value={form.hub_type} onChange={(e) => setForm({ ...form, hub_type: e.target.value })}>
                {(hubs.length ? hubs : [{ hub_type: "sugar_sweeps" }]).map((h) => (
                  <option key={h.hub_type} value={h.hub_type}>{h.hub_type}</option>
                ))}
              </select>
            </label>

            <div className="dp-row2">
              <label className="dp-field">
                <span>Distributor username</span>
                <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
              </label>
              <label className="dp-field">
                <span>{editing ? "Password (leave blank to keep)" : "Distributor password"}</span>
                <input type="password" value={form.password} autoComplete="new-password"
                  onChange={(e) => setForm({ ...form, password: e.target.value })} />
              </label>
            </div>

            <div className="dp-row2">
              <label className="dp-field">
                <span>Base URL (optional)</span>
                <input value={form.base_url} placeholder="https://sugarsweeps.com" onChange={(e) => setForm({ ...form, base_url: e.target.value })} />
              </label>
              <div style={{ display: "flex", gap: 10, flex: 1 }}>
                <label className="dp-field">
                  <span>Daily cap</span>
                  <input type="number" min="0" value={form.daily_cap} onChange={(e) => setForm({ ...form, daily_cap: e.target.value })} />
                </label>
                <label className="dp-field">
                  <span>Per-transfer cap</span>
                  <input type="number" min="0" value={form.per_transfer_cap} onChange={(e) => setForm({ ...form, per_transfer_cap: e.target.value })} />
                </label>
              </div>
            </div>

            <div className="dp-field">
              <span>Platforms this account can fund</span>
              <div className="dp-pl-check">
                {allPlatforms.map((slug) => (
                  <label key={slug} className={`chip check ${form.supported_platforms.includes(slug) ? "on" : ""}`}>
                    <input type="checkbox" checked={form.supported_platforms.includes(slug)} onChange={() => togglePlatform(slug)} />
                    {slug}
                  </label>
                ))}
                {allPlatforms.length === 0 && <em>No platforms registered. Add games in Admin → Games first.</em>}
              </div>
            </div>

            <div className="dp-modal-foot">
              <button className="dp-ghost" onClick={() => { setShowForm(false); resetForm(); }}>Cancel</button>
              <button className="dp-save" onClick={save} disabled={busy === "save"}>
                {busy === "save" ? <Loader2 size={14} className="is-spinning" /> : null} {editing ? "Save changes" : "Create distributor"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DistributorPanel;
