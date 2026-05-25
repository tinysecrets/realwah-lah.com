/**
 * LaunchChecklist.jsx — admin pre-flight widget.
 * Polls /api/ext/launch-checklist and shows a 6-gate readiness panel with
 * a top banner ("READY FOR LIVE TRAFFIC" / "LAUNCH WITH CAUTION" / "DO NOT LAUNCH").
 */
import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { CheckCircle2, AlertTriangle, XCircle, RefreshCw, Rocket } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const statusIcon = (s) => {
  if (s === "pass") return <CheckCircle2 size={18} className="lc-ico lc-pass" />;
  if (s === "warn") return <AlertTriangle size={18} className="lc-ico lc-warn" />;
  return <XCircle size={18} className="lc-ico lc-fail" />;
};

const LaunchChecklist = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/ext/launch-checklist`);
      setData(data);
    } catch (e) {
      setData({ error: e.response?.data?.detail || e.message });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (!data) {
    return <div className="launch-checklist is-loading" data-testid="launch-checklist-loading">Casting the pre-flight spell…</div>;
  }
  if (data.error) {
    return <div className="launch-checklist is-error">{data.error}</div>;
  }

  const s = data.summary;
  const bannerClass =
    s.banner === "READY FOR LIVE TRAFFIC" ? "is-ready" :
    s.banner === "DO NOT LAUNCH" ? "is-blocked" : "is-caution";

  return (
    <div className="launch-checklist" data-testid="launch-checklist">
      <div className={`lc-banner ${bannerClass}`} data-testid="lc-banner">
        <Rocket size={22} />
        <div className="lc-banner-text">
          <strong>{s.banner}</strong>
          <span>{s.passing} passing · {s.warning} warnings · {s.failing} failing</span>
        </div>
        <button
          className="lc-refresh"
          onClick={load}
          disabled={loading}
          data-testid="lc-refresh-btn"
          title="Re-run checks"
        >
          <RefreshCw size={14} className={loading ? "is-spinning" : ""} />
        </button>
      </div>
      <div className="lc-checks">
        {data.checks.map((c) => (
          <div key={c.key} className={`lc-row lc-row-${c.status}`} data-testid={`lc-row-${c.key}`}>
            {statusIcon(c.status)}
            <div className="lc-row-text">
              <div className="lc-row-label">{c.label}</div>
              <div className="lc-row-detail">{c.detail}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default LaunchChecklist;
