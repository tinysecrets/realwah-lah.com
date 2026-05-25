import { useState, useEffect, useRef } from "react";
import axios from "axios";
import { toast } from "sonner";
import "./NerveCenter.css";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ASCII = String.raw`
███╗   ██╗███████╗██████╗ ██╗   ██╗███████╗     ██████╗███████╗███╗   ██╗████████╗███████╗██████╗
████╗  ██║██╔════╝██╔══██╗██║   ██║██╔════╝    ██╔════╝██╔════╝████╗  ██║╚══██╔══╝██╔════╝██╔══██╗
██╔██╗ ██║█████╗  ██████╔╝██║   ██║█████╗      ██║     █████╗  ██╔██╗ ██║   ██║   █████╗  ██████╔╝
██║╚██╗██║██╔══╝  ██╔══██╗╚██╗ ██╔╝██╔══╝      ██║     ██╔══╝  ██║╚██╗██║   ██║   ██╔══╝  ██╔══██╗
██║ ╚████║███████╗██║  ██║ ╚████╔╝ ███████╗    ╚██████╗███████╗██║ ╚████║   ██║   ███████╗██║  ██║
╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝     ╚═════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚══════╝╚═╝  ╚═╝`;

const fmt$ = (v) => `$${Number(v || 0).toFixed(2)}`;
const fmtTime = (iso) => {
  if (!iso) return "--:--:--";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch { return "--:--:--"; }
};

const Siren = ({ alerts, onAck }) => {
  if (!alerts || alerts.length === 0) {
    return (
      <div className="nerve-siren quiet" data-testid="siren-quiet">
        <div className="label"><span className="nerve-status-dot ok" /> ALL SYSTEMS GREEN — NO OPEN ALERTS</div>
      </div>
    );
  }
  return (
    <div className="nerve-siren" data-testid="siren-active">
      <div className="label">▲ {alerts.length} ACTIVE ALERT{alerts.length > 1 ? "S" : ""} ▲</div>
      <ul>
        {alerts.map((a) => (
          <li key={a.id} data-testid={`siren-alert-${a.id}`}>
            <div>
              <b style={{ color: "#ff9a9a" }}>[{a.type}]</b>{" "}
              <span>{a.message}</span>
              {a.user_email && <span style={{ color: "#5b8870", marginLeft: 6 }}>· {a.user_email}</span>}
            </div>
            <button className="ack" data-testid={`ack-${a.id}`} onClick={() => onAck(a.id)}>ACK</button>
          </li>
        ))}
      </ul>
    </div>
  );
};

const Panel = ({ title, children, testid }) => (
  <div className="nerve-panel" data-testid={testid}>
    <h4>{title}</h4>
    {children}
  </div>
);

const Sparkline = ({ data }) => {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="nerve-spark" data-testid="nerve-sparkline">
      {data.map((d, i) => (
        <span key={i} style={{ height: `${(d.value / max) * 100}%` }} data-label={d.day} title={`${d.day}: $${d.value.toFixed(2)}`} />
      ))}
    </div>
  );
};

const ActivityFeed = ({ events }) => (
  <div className="nerve-panel nerve-feed" data-testid="activity-feed">
    <h4>» LIVE ACTIVITY FEED</h4>
    {events.length === 0 ? (
      <div style={{ color: "#5b8870", fontSize: 12 }}>No activity yet.</div>
    ) : (
      events.map((e, i) => {
        const cls = e.kind.includes("failed") ? "failed" : e.kind.startsWith("alert.") ? "alert" : "";
        return (
          <div key={i} className={`nerve-event ${cls}`} data-testid={`event-${i}`}>
            <span className="icon">{e.icon}</span>
            <span className="ts">{fmtTime(e.ts)}</span>
            <span className="title">{e.title}</span>
            <span className="kind">{e.kind}</span>
          </div>
        );
      })
    )}
  </div>
);

export default function NerveCenter() {
  const [data, setData] = useState(null);
  const [feed, setFeed] = useState([]);
  const [err, setErr] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const tickRef = useRef(null);

  const load = async () => {
    setRefreshing(true);
    try {
      const [o, f] = await Promise.all([
        axios.get(`${API}/ext/nerve/overview`),
        axios.get(`${API}/ext/nerve/activity-feed?limit=60`),
      ]);
      setData(o.data);
      setFeed(f.data || []);
      setErr(null);
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    load();
    // Try WebSocket for live pushes — fall back to polling if it fails.
    let ws = null;
    let wsAlive = false;
    try {
      const wsUrl = (API.replace(/^http/, "ws")) + "/ext/nerve/ws";
      ws = new WebSocket(wsUrl);
      ws.onopen = () => { wsAlive = true; };
      ws.onmessage = (evt) => {
        try {
          const m = JSON.parse(evt.data);
          // Any push triggers a fresh load; "ping" is a heartbeat and can be ignored.
          if (m.kind && m.kind !== "ping") load();
        } catch {}
      };
      ws.onclose = () => { wsAlive = false; };
    } catch {
      wsAlive = false;
    }
    // Polling fallback — only runs if WS didn't connect OR is dropped.
    tickRef.current = setInterval(() => { if (!wsAlive) load(); }, 15000);
    return () => {
      if (ws) { try { ws.close(); } catch {} }
      clearInterval(tickRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ack = async (id) => {
    try {
      await axios.post(`${API}/ext/nerve/alerts/${id}/acknowledge`);
      toast.success("Alert acknowledged");
      load();
    } catch (e) {
      toast.error("Ack failed");
    }
  };

  if (err) {
    return (
      <div className="nerve-root">
        <div className="nerve-banner">{ASCII}</div>
        <div style={{ color: "#ff5a5a", marginTop: 20, fontSize: 14 }}>
          <span className="nerve-prompt">[CRITICAL]</span> connection lost: {err}
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="nerve-root">
        <div className="nerve-banner">{ASCII}</div>
        <div style={{ color: "#3aff9c", marginTop: 20, fontSize: 13 }}>
          <span className="nerve-prompt">booting</span> ...loading telemetry...
        </div>
      </div>
    );
  }

  const { users, payments, queues, pool, siren } = data;
  const poolPct = pool.total > 0 ? Math.round((pool.active / pool.total) * 100) : 0;

  return (
    <div className="nerve-root" data-testid="nerve-center">
      <div className="nerve-banner">{ASCII}</div>
      <div className="nerve-topbar">
        <div className="meta">
          <span><span className="nerve-prompt">root@sugarcity</span>:~/nerve-center$</span>
          <span>TIME <b>{fmtTime(data.timestamp)}</b></span>
          <span>REFRESH <b>15s</b></span>
          <span><span className={`nerve-status-dot ${refreshing ? "warn" : "ok"}`} />{refreshing ? "SYNCING" : "LIVE"}</span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="nerve-btn" data-testid="nerve-refresh" onClick={load} disabled={refreshing}>
            {refreshing ? "⟳" : "↻"} REFRESH
          </button>
          <a href="/admin" className="nerve-btn" data-testid="nerve-goto-admin">ADMIN</a>
          <a href="/admin/extensions" className="nerve-btn" data-testid="nerve-goto-ext">EXTENSIONS</a>
        </div>
      </div>

      <Siren alerts={siren} onAck={ack} />

      <div className="nerve-grid">
        <Panel title="» PLAYERS" testid="panel-users">
          <div className="big">{users.total}</div>
          <div className="sub">total registered</div>
          <div style={{ marginTop: 10 }}>
            <div className="row"><span className="k">last 24h</span><span className="v">+{users.last_24h}</span></div>
            <div className="row"><span className="k">last 7d</span><span className="v">+{users.last_7d}</span></div>
          </div>
        </Panel>

        <Panel title="» REVENUE" testid="panel-revenue">
          <div className="big">{fmt$(payments.revenue_24h)}</div>
          <div className="sub">last 24h · {payments.transactions_24h} tx</div>
          <Sparkline data={payments.sparkline_7d} />
          <div className="row" style={{ marginTop: 14 }}>
            <span className="k">7d total</span><span className="v">{fmt$(payments.revenue_7d)}</span>
          </div>
          <div className="row">
            <span className="k">lifetime paid</span><span className="v">{payments.total_paid_ever}</span>
          </div>
        </Panel>

        <Panel title="» PROXY POOL" testid="panel-pool">
          <div className="big">{pool.active}<span style={{ fontSize: 18, color: "#5b8870" }}>/{pool.total}</span></div>
          <div className="sub">active proxies ({poolPct}%)</div>
          <div style={{ marginTop: 10 }}>
            <div className="row"><span className="k">cooldown</span><span className={`v ${pool.cooldown ? "hot" : ""}`}>{pool.cooldown}</span></div>
            <div className="row"><span className="k">locked</span><span className={`v ${pool.locked ? "cold" : ""}`}>{pool.locked}</span></div>
            <div className="row"><span className="k">capacity left</span><span className="v">{fmt$(pool.daily_capacity_remaining)}</span></div>
          </div>
        </Panel>

        <Panel title="» QUEUES" testid="panel-queues">
          <div className="row"><span className="k">tickets open</span><span className={`v ${queues.tickets_open ? "hot" : ""}`}>{queues.tickets_open}</span></div>
          <div className="row"><span className="k">redemptions pending</span><span className={`v ${queues.redemptions_pending ? "hot" : ""}`}>{queues.redemptions_pending}</span></div>
          <div className="row"><span className="k">admin alerts open</span><span className={`v ${queues.admin_alerts_open ? "cold" : ""}`}>{queues.admin_alerts_open}</span></div>
          <div className="row"><span className="k">jit failures</span><span className={`v ${queues.jit_failures_open ? "cold" : ""}`}>{queues.jit_failures_open}</span></div>
          <div style={{ marginTop: 10, fontSize: 10, color: "#5b8870" }}>{">"} work the hot rows first</div>
        </Panel>

        <ActivityFeed events={feed} />
      </div>
    </div>
  );
}
