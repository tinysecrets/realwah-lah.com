import { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Trophy, Gift, RefreshCw, Users, Gem, Crown, Medal, Clock } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "https://api.wah-lah.com";
const API = `${BACKEND_URL}/api`;

function pad(n) {
  return String(n).padStart(2, "0");
}

function useCountdown(target) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!target) return undefined;
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [target]);
  const diff = target ? Math.max(0, target - now) : 0;
  return {
    days: Math.floor(diff / 86400000),
    hours: Math.floor((diff % 86400000) / 3600000),
    minutes: Math.floor((diff % 3600000) / 60000),
    seconds: Math.floor((diff % 60000) / 1000),
  };
}

export default function CompetitionPromo({ user, refreshUser }) {
  const [data, setData] = useState({ competition: null, recent_winners: [] });
  const [loading, setLoading] = useState(true);
  const [claiming, setClaiming] = useState(false);

  const fetchComp = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/competition`);
      setData(data);
    } catch {
      setData({ competition: null, recent_winners: [] });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchComp(); }, [fetchComp]);

  const comp = data.competition;
  const target = comp?.draws_at ? new Date(comp.draws_at).getTime() : null;
  const c = useCountdown(target);
  const isLive = comp?.status === "live";

  const claimFreeEntry = async () => {
    if (claiming) return;
    setClaiming(true);
    try {
      const { data } = await axios.post(`${API}/amoe/claim-daily`);
      toast.success(data.message);
      await fetchComp();
      if (refreshUser) await refreshUser();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Claim failed");
    } finally {
      setClaiming(false);
    }
  };

  if (loading) {
    return <div style={{ minHeight: "40vh", display: "flex", alignItems: "center", justifyContent: "center", color: "#d4af37" }}>Loading competition…</div>;
  }

  return (
    <div className="comp-promo">
      {/* Hero */}
      <section className="comp-hero">
        <div className="comp-hero-badge">
          <Trophy size={16} /> {comp ? (comp.status === "live" ? "LIVE — ENTRIES OPEN" : "COMING SOON") : "PROMOTION"}
        </div>
        <h2 className="comp-title">{comp ? comp.name : "Million Dollar Sweepstakes"}</h2>
        <div className="comp-prize">${Number(comp?.prize_usd || 1000000).toLocaleString()}</div>
        <p className="comp-tagline">Grand finale prize pool. Entries on every purchase — plus free daily entries, no purchase necessary.</p>

        {isLive && target && (
          <div className="comp-countdown" data-testid="comp-countdown">
            <div className="comp-timer-cell"><span className="comp-timer-num">{pad(c.days)}</span><span className="comp-timer-label">Days</span></div>
            <div className="comp-timer-cell"><span className="comp-timer-num">{pad(c.hours)}</span><span className="comp-timer-label">Hours</span></div>
            <div className="comp-timer-cell"><span className="comp-timer-num">{pad(c.minutes)}</span><span className="comp-timer-label">Minutes</span></div>
            <div className="comp-timer-cell"><span className="comp-timer-num">{pad(c.seconds)}</span><span className="comp-timer-label">Seconds</span></div>
          </div>
        )}

        <div className="comp-meta-grid">
          <div className="comp-meta-cell">
            <Gift size={18} />
            <div>
              <span className="comp-meta-value">{comp?.totals?.total_entries?.toLocaleString() ?? "—"}</span>
              <span className="comp-meta-label">Total entries</span>
            </div>
          </div>
          <div className="comp-meta-cell">
            <Users size={18} />
            <div>
              <span className="comp-meta-value">{comp?.totals?.total_players?.toLocaleString() ?? "—"}</span>
              <span className="comp-meta-label">Players entered</span>
            </div>
          </div>
          <div className="comp-meta-cell">
            <Gem size={18} />
            <div>
              <span className="comp-meta-value">{comp && user ? comp.my_entries?.toLocaleString() : "—"}</span>
              <span className="comp-meta-label">Your entries</span>
            </div>
          </div>
        </div>

        {isLive && (
          <div className="comp-entry-cta">
            <button
              type="button"
              className="comp-cta-btn"
              data-testid="comp-claim-free"
              onClick={claimFreeEntry}
              disabled={claiming}
            >
              {claiming ? (<><RefreshCw size={18} className="spinning" /> Claiming…</>) : (<><Gift size={18} /> Claim Daily Free Entry</>)}
            </button>
            <span className="comp-cta-hint">No purchase necessary · 1 free entry daily · every $1 purchase = 1 entry</span>
          </div>
        )}

        {!isLive && comp && (
          <div className="comp-entry-cta">
            <span className="comp-cta-hint">Entries open when the promotion goes live. Free daily entries, no purchase necessary.</span>
          </div>
        )}
      </section>

      {/* How it works */}
      <section className="comp-panel">
        <h3 className="comp-panel-title">How to earn entries</h3>
        <div className="comp-how-grid">
          <div className="comp-how-card">
            <Crown size={22} />
            <h4>Play to win</h4>
            <p>Every <strong>$1</strong> you spend on Sugar Tokens banks you <strong>1 entry</strong> into the finale draw automatically.</p>
          </div>
          <div className="comp-how-card">
            <Gift size={22} />
            <h4>Free entries</h4>
            <p>Claim a <strong>free entry every 24 hours</strong> — no purchase necessary. Open to all members, per sweepstakes law.</p>
          </div>
          <div className="comp-how-card">
            <Trophy size={22} />
            <h4>Grand finale draw</h4>
            <p>On the draw date we select one winner at random to take home the <strong>${Number(comp?.prize_usd || 1000000).toLocaleString()}</strong> prize.</p>
          </div>
        </div>
      </section>

      {/* Leaderboard */}
      <section className="comp-panel">
        <h3 className="comp-panel-title">Leaderboard</h3>
        {comp && comp.leaderboard && comp.leaderboard.length > 0 ? (
          <table className="comp-table">
            <thead>
              <tr><th>Rank</th><th>Member</th><th className="comp-tab-num">Entries</th></tr>
            </thead>
            <tbody>
              {comp.leaderboard.map((row) => (
                <tr key={row.rank} className={row.rank <= 3 ? `comp-rank-${row.rank}` : ""}>
                  <td className="comp-rank-cell">
                    {row.rank <= 3 ? <Medal size={16} /> : null} {row.rank}
                  </td>
                  <td>{row.name}</td>
                  <td className="comp-tab-num">{row.entries.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="comp-empty">No entries yet — be the first on the board.</p>
        )}
      </section>

      {/* Past winners */}
      {data.recent_winners && data.recent_winners.length > 0 && (
        <section className="comp-panel">
          <h3 className="comp-panel-title">Past Winners</h3>
          <ul className="comp-winners-list">
            {data.recent_winners.map((w) => (
              <li key={w.competition_id}>
                <span className="comp-winner-name">{w.winner_name}</span>
                <span className="comp-winner-prize">${Number(w.prize_usd).toLocaleString()}</span>
                {w.prize_status === "paid" ? <span className="comp-paid-tag">PAID</span> : null}
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="comp-legal">
        NO PURCHASE NECESSARY. A purchase will not increase your chances of winning. Free entries are available via the daily
        Alternative Method of Entry (AMOE). Void where prohibited. 21+ members only. See full terms in the promotion rules.
      </p>
    </div>
  );
}