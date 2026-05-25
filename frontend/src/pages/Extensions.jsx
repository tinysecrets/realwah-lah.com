import { useState, useEffect } from "react";
import axios from "axios";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft,
  KeyRound,
  Mail,
  Lock,
  ShieldCheck,
  Gift,
  UserPlus,
  Users,
  Crown,
  Sparkles,
  TicketPercent,
  LifeBuoy,
  Copy,
  Check,
  BarChart3,
  ShieldAlert,
  Zap,
  Trophy,
  Network,
  Power,
  Radio,
  Trash2,
  Plus,
  Unlock,
} from "lucide-react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// ============= SHARED STYLE =============
const shellStyle = {
  minHeight: "100vh",
  background: "radial-gradient(ellipse at top, #1a0b2e 0%, #0a0a0f 70%)",
  color: "#f5e9ff",
  padding: "24px",
  fontFamily: "'Plus Jakarta Sans', -apple-system, system-ui, sans-serif",
};

const cardStyle = {
  background: "linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.015))",
  border: "1px solid rgba(255, 180, 60, 0.18)",
  borderRadius: "18px",
  padding: "28px",
  backdropFilter: "blur(12px)",
  boxShadow: "0 14px 60px rgba(0,0,0,0.45)",
};

const inputStyle = {
  width: "100%",
  padding: "12px 14px",
  borderRadius: "10px",
  background: "rgba(255,255,255,0.05)",
  border: "1px solid rgba(255,255,255,0.12)",
  color: "#f5e9ff",
  fontSize: "14px",
  outline: "none",
};

const primaryBtn = {
  width: "100%",
  padding: "12px 16px",
  background: "linear-gradient(90deg, #ff9a3c 0%, #ff5b5b 100%)",
  border: "none",
  borderRadius: "12px",
  color: "white",
  fontWeight: 700,
  fontSize: "14px",
  letterSpacing: "0.3px",
  cursor: "pointer",
  transition: "transform .15s ease",
};

const secondaryBtn = {
  padding: "10px 14px",
  background: "rgba(255,255,255,0.07)",
  border: "1px solid rgba(255,255,255,0.14)",
  borderRadius: "10px",
  color: "#f5e9ff",
  fontWeight: 600,
  fontSize: "13px",
  cursor: "pointer",
};

const Header = ({ title, back = "/" }) => (
  <div style={{ maxWidth: 960, margin: "0 auto 24px" }}>
    <Link to={back} data-testid="ext-back-link" style={{ color: "#ffb44c", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6, fontSize: 14 }}>
      <ArrowLeft size={16} /> Back
    </Link>
    <h1 style={{ margin: "10px 0 6px", fontSize: 32, letterSpacing: "-0.5px" }}>{title}</h1>
  </div>
);

// ============= FORGOT PASSWORD =============
export const ForgotPasswordPage = () => {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [devLink, setDevLink] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await axios.post(`${API}/ext/password/forgot`, { email });
      toast.success(data.message);
      if (data.dev_reset_link) setDevLink(data.dev_reset_link);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={shellStyle} data-testid="forgot-password-page">
      <Header title="Forgot password" back="/login" />
      <div style={{ maxWidth: 460, margin: "0 auto" }}>
        <div style={cardStyle}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
            <KeyRound size={22} color="#ffb44c" />
            <div style={{ color: "#cfc3e8" }}>Enter your email to receive a reset link.</div>
          </div>
          <form onSubmit={submit}>
            <label style={{ display: "block", fontSize: 13, marginBottom: 6 }}>Email</label>
            <input
              data-testid="forgot-email-input"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={inputStyle}
              placeholder="you@example.com"
            />
            <button data-testid="forgot-submit-btn" disabled={loading} type="submit" style={{ ...primaryBtn, marginTop: 16 }}>
              {loading ? "Sending…" : "Send reset link"}
            </button>
          </form>
          {devLink && (
            <div data-testid="forgot-dev-link" style={{ marginTop: 16, padding: 12, background: "rgba(255,180,60,0.08)", border: "1px dashed #ffb44c", borderRadius: 10, fontSize: 12, wordBreak: "break-all" }}>
              <b>Dev mode link:</b>
              <br />
              <a href={devLink} style={{ color: "#ffb44c" }}>{devLink}</a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ============= RESET PASSWORD =============
export const ResetPasswordPage = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [token] = useState(params.get("token") || "");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (pw !== pw2) return toast.error("Passwords do not match");
    if (!token) return toast.error("Missing token");
    setLoading(true);
    try {
      await axios.post(`${API}/ext/password/reset`, { token, new_password: pw });
      toast.success("Password reset. Please log in.");
      navigate("/login");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Reset failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={shellStyle} data-testid="reset-password-page">
      <Header title="Reset password" back="/login" />
      <div style={{ maxWidth: 460, margin: "0 auto" }}>
        <div style={cardStyle}>
          <form onSubmit={submit}>
            <label style={{ display: "block", fontSize: 13, marginBottom: 6 }}>New password</label>
            <input data-testid="reset-new-password-input" type="password" value={pw} onChange={(e) => setPw(e.target.value)} required minLength={6} style={inputStyle} />
            <label style={{ display: "block", fontSize: 13, margin: "14px 0 6px" }}>Confirm password</label>
            <input data-testid="reset-confirm-password-input" type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} required minLength={6} style={inputStyle} />
            <button data-testid="reset-submit-btn" disabled={loading} style={{ ...primaryBtn, marginTop: 18 }}>{loading ? "Resetting…" : "Reset password"}</button>
          </form>
        </div>
      </div>
    </div>
  );
};

// ============= SETTINGS (2FA, Change Password, Referral, Promo) =============
export const SettingsPage = () => {
  const [tab, setTab] = useState("security");
  return (
    <div style={shellStyle} data-testid="settings-page">
      <Header title="Account settings" />
      <div style={{ maxWidth: 960, margin: "0 auto" }}>
        <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
          {[
            { id: "security", label: "Security", icon: <ShieldCheck size={16} /> },
            { id: "rewards", label: "Rewards & Promo", icon: <Gift size={16} /> },
            { id: "referral", label: "Referrals", icon: <Users size={16} /> },
            { id: "vip", label: "VIP Tier", icon: <Crown size={16} /> },
            { id: "support", label: "Support", icon: <LifeBuoy size={16} /> },
          ].map((t) => (
            <button
              key={t.id}
              data-testid={`settings-tab-${t.id}`}
              onClick={() => setTab(t.id)}
              style={{
                ...secondaryBtn,
                borderColor: tab === t.id ? "#ffb44c" : "rgba(255,255,255,0.14)",
                background: tab === t.id ? "rgba(255,180,60,0.12)" : "rgba(255,255,255,0.07)",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>
        {tab === "security" && <SecurityPanel />}
        {tab === "rewards" && <PromoPanel />}
        {tab === "referral" && <ReferralPanel />}
        {tab === "vip" && <VipPanel />}
        {tab === "support" && <SupportPanel />}
      </div>
    </div>
  );
};

const SecurityPanel = () => {
  const [cur, setCur] = useState("");
  const [nw, setNw] = useState("");
  const [twofa, setTwofa] = useState({ enabled: false });
  const [setup, setSetup] = useState(null);
  const [code, setCode] = useState("");

  const loadStatus = async () => {
    try {
      const { data } = await axios.get(`${API}/ext/2fa/status`);
      setTwofa(data);
    } catch (err) { console.error("Extensions error:", err); }
  };
  useEffect(() => { loadStatus(); }, []);

  const changePw = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/ext/password/change`, { current_password: cur, new_password: nw });
      toast.success("Password updated");
      setCur(""); setNw("");
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const start2fa = async () => {
    try {
      const { data } = await axios.post(`${API}/ext/2fa/setup`);
      setSetup(data);
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const enable2fa = async () => {
    try {
      await axios.post(`${API}/ext/2fa/enable`, { code });
      toast.success("2FA enabled");
      setSetup(null); setCode(""); loadStatus();
    } catch (err) { toast.error(err.response?.data?.detail || "Invalid code"); }
  };

  const disable2fa = async () => {
    try {
      await axios.post(`${API}/ext/2fa/disable`, { code });
      toast.success("2FA disabled");
      setCode(""); loadStatus();
    } catch (err) { toast.error(err.response?.data?.detail || "Invalid code"); }
  };

  return (
    <div style={{ display: "grid", gap: 18, gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))" }}>
      <div style={cardStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
          <Lock size={18} color="#ffb44c" /><h3 style={{ margin: 0 }}>Change password</h3>
        </div>
        <form onSubmit={changePw}>
          <label style={{ fontSize: 13 }}>Current password</label>
          <input data-testid="sec-current-pw" type="password" value={cur} onChange={(e) => setCur(e.target.value)} required style={inputStyle} />
          <label style={{ fontSize: 13, marginTop: 12, display: "block" }}>New password</label>
          <input data-testid="sec-new-pw" type="password" value={nw} onChange={(e) => setNw(e.target.value)} required minLength={6} style={inputStyle} />
          <button data-testid="sec-change-pw-btn" type="submit" style={{ ...primaryBtn, marginTop: 14 }}>Update password</button>
        </form>
      </div>

      <div style={cardStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
          <ShieldCheck size={18} color="#ffb44c" /><h3 style={{ margin: 0 }}>Two-factor authentication</h3>
        </div>
        <div style={{ color: "#cfc3e8", fontSize: 13, marginBottom: 12 }}>
          Status: <b data-testid="sec-2fa-status" style={{ color: twofa.enabled ? "#79ffa6" : "#ff9a3c" }}>{twofa.enabled ? "Enabled" : "Disabled"}</b>
        </div>

        {!twofa.enabled && !setup && (
          <button data-testid="sec-2fa-setup-btn" onClick={start2fa} style={primaryBtn}>Enable 2FA</button>
        )}

        {!twofa.enabled && setup && (
          <div>
            <p style={{ fontSize: 13, color: "#cfc3e8" }}>Scan this QR in your authenticator app, or use the secret below.</p>
            <img data-testid="sec-2fa-qr" alt="2FA QR" src={setup.qr_code_base64} style={{ width: 180, height: 180, borderRadius: 12, background: "white", padding: 8 }} />
            <div style={{ fontSize: 12, marginTop: 8, wordBreak: "break-all", color: "#ffb44c" }}>Secret: <code data-testid="sec-2fa-secret">{setup.secret}</code></div>
            <input data-testid="sec-2fa-code" placeholder="6-digit code" value={code} onChange={(e) => setCode(e.target.value)} style={{ ...inputStyle, marginTop: 10 }} />
            <button data-testid="sec-2fa-enable-btn" onClick={enable2fa} style={{ ...primaryBtn, marginTop: 10 }}>Verify & enable</button>
          </div>
        )}

        {twofa.enabled && (
          <div>
            <input data-testid="sec-2fa-disable-code" placeholder="6-digit code to disable" value={code} onChange={(e) => setCode(e.target.value)} style={inputStyle} />
            <button data-testid="sec-2fa-disable-btn" onClick={disable2fa} style={{ ...primaryBtn, marginTop: 10, background: "linear-gradient(90deg,#ff5b5b,#c94141)" }}>Disable 2FA</button>
          </div>
        )}
      </div>
    </div>
  );
};

const PromoPanel = () => {
  const [code, setCode] = useState("");
  const [history, setHistory] = useState([]);

  const load = async () => {
    try { const { data } = await axios.get(`${API}/ext/promo/history`); setHistory(data); } catch (err) { console.error("Extensions error:", err); }
  };
  useEffect(() => { load(); }, []);

  const redeem = async (e) => {
    e.preventDefault();
    try {
      const { data } = await axios.post(`${API}/ext/promo/redeem`, { code });
      toast.success(data.message);
      setCode(""); load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  return (
    <div style={{ display: "grid", gap: 18, gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))" }}>
      <div style={cardStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
          <TicketPercent size={18} color="#ffb44c" /><h3 style={{ margin: 0 }}>Redeem promo code</h3>
        </div>
        <form onSubmit={redeem}>
          <input data-testid="promo-code-input" placeholder="Enter promo code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} required style={inputStyle} />
          <button data-testid="promo-redeem-btn" style={{ ...primaryBtn, marginTop: 12 }}>Redeem</button>
        </form>
      </div>
      <div style={cardStyle}>
        <h3 style={{ marginTop: 0 }}>My redemptions</h3>
        {history.length === 0 ? (
          <div data-testid="promo-history-empty" style={{ color: "#9d93b5", fontSize: 13 }}>No redemptions yet.</div>
        ) : (
          <ul style={{ paddingLeft: 16, fontSize: 14 }}>
            {history.map((h, i) => (
              <li key={i} style={{ marginBottom: 6 }}>
                <b>{h.code}</b> — +{h.credits} credits <span style={{ color: "#9d93b5" }}>({h.created_at?.slice(0,10)})</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

const ReferralPanel = () => {
  const [me, setMe] = useState(null);
  const [copied, setCopied] = useState(false);
  const [friendCode, setFriendCode] = useState("");

  const load = async () => {
    try { const { data } = await axios.get(`${API}/ext/referral/me`); setMe(data); } catch (err) { console.error("Extensions error:", err); }
  };
  useEffect(() => { load(); }, []);

  const copy = () => {
    if (!me) return;
    navigator.clipboard.writeText(me.referral_code);
    setCopied(true); setTimeout(() => setCopied(false), 1500);
  };

  const redeemFriend = async (e) => {
    e.preventDefault();
    try {
      const { data } = await axios.post(`${API}/ext/referral/redeem`, { code: friendCode });
      toast.success(data.message);
      setFriendCode(""); load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  return (
    <div style={{ display: "grid", gap: 18, gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))" }}>
      <div style={cardStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
          <UserPlus size={18} color="#ffb44c" /><h3 style={{ margin: 0 }}>Your referral code</h3>
        </div>
        {me ? (
          <>
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <div data-testid="referral-code" style={{ fontFamily: "monospace", fontSize: 22, padding: "10px 14px", background: "rgba(255,180,60,0.12)", border: "1px dashed #ffb44c", borderRadius: 10 }}>{me.referral_code}</div>
              <button data-testid="referral-copy-btn" onClick={copy} style={secondaryBtn}>{copied ? <Check size={16} /> : <Copy size={16} />}</button>
            </div>
            <div style={{ marginTop: 16, fontSize: 14, color: "#cfc3e8" }}>
              <div><b data-testid="referral-count">{me.referred_count}</b> friends signed up</div>
              <div><b data-testid="referral-earned">{me.bonus_earned}</b> credits earned</div>
              <div style={{ marginTop: 6, color: "#9d93b5" }}>Each referral rewards both of you with +{me.reward_per_signup} credits.</div>
            </div>
          </>
        ) : <div>Loading…</div>}
      </div>
      <div style={cardStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
          <Gift size={18} color="#ffb44c" /><h3 style={{ margin: 0 }}>Use a friend's code</h3>
        </div>
        <form onSubmit={redeemFriend}>
          <input data-testid="referral-friend-code" placeholder="Friend's referral code" value={friendCode} onChange={(e) => setFriendCode(e.target.value.toUpperCase())} required style={inputStyle} />
          <button data-testid="referral-redeem-btn" style={{ ...primaryBtn, marginTop: 12 }}>Redeem</button>
        </form>
      </div>
    </div>
  );
};

const VipPanel = () => {
  const [tier, setTier] = useState(null);
  const [tiers, setTiers] = useState([]);
  useEffect(() => {
    axios.get(`${API}/ext/vip/tier`).then(r => setTier(r.data)).catch(() => {});
    axios.get(`${API}/ext/vip/tiers`).then(r => setTiers(r.data)).catch(() => {});
  }, []);

  return (
    <div style={{ display: "grid", gap: 18 }}>
      <div style={cardStyle} data-testid="vip-current">
        {tier ? (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <Crown size={26} color={tier.color} />
              <div>
                <div style={{ fontSize: 22, fontWeight: 700, color: tier.color }} data-testid="vip-tier-name">{tier.name}</div>
                <div style={{ color: "#cfc3e8", fontSize: 13 }}>Lifetime spend: ${tier.lifetime_spend_usd.toFixed(2)}</div>
              </div>
            </div>
            <div style={{ marginTop: 16 }}>
              <div style={{ height: 10, background: "rgba(255,255,255,0.08)", borderRadius: 6, overflow: "hidden" }}>
                <div style={{ width: `${(tier.progress * 100).toFixed(0)}%`, height: "100%", background: `linear-gradient(90deg, ${tier.color}, #ffb44c)` }} />
              </div>
              {tier.next_tier && (
                <div style={{ marginTop: 8, fontSize: 13, color: "#cfc3e8" }}>
                  ${tier.next_tier.needed.toFixed(2)} to reach <b>{tier.next_tier.name}</b>
                </div>
              )}
            </div>
          </>
        ) : "Loading…"}
      </div>
      <div style={cardStyle}>
        <h3 style={{ marginTop: 0 }}>All tiers</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px,1fr))", gap: 12 }}>
          {tiers.map(t => (
            <div key={t.name} data-testid={`vip-tier-${t.name.toLowerCase()}`} style={{ padding: 14, borderRadius: 12, background: "rgba(255,255,255,0.04)", border: `1px solid ${t.color}55` }}>
              <div style={{ color: t.color, fontWeight: 700 }}>{t.name}</div>
              <div style={{ fontSize: 12, color: "#9d93b5" }}>Min spend: ${t.min_spend}</div>
              <div style={{ fontSize: 12, color: "#9d93b5" }}>Deposit bonus: {t.bonus_pct}%</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const SupportPanel = () => {
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [priority, setPriority] = useState("normal");
  const [tickets, setTickets] = useState([]);

  const load = async () => {
    try { const { data } = await axios.get(`${API}/ext/support/tickets`); setTickets(data); } catch (err) { console.error("Extensions error:", err); }
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/ext/support/ticket`, { subject, message, priority });
      toast.success("Ticket submitted");
      setSubject(""); setMessage(""); setPriority("normal"); load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  return (
    <div style={{ display: "grid", gap: 18, gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))" }}>
      <div style={cardStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
          <LifeBuoy size={18} color="#ffb44c" /><h3 style={{ margin: 0 }}>Open a ticket</h3>
        </div>
        <form onSubmit={submit}>
          <input data-testid="ticket-subject" placeholder="Subject" value={subject} onChange={e => setSubject(e.target.value)} required style={inputStyle} />
          <textarea data-testid="ticket-message" placeholder="Describe your issue…" value={message} onChange={e => setMessage(e.target.value)} required style={{ ...inputStyle, minHeight: 120, marginTop: 10, resize: "vertical" }} />
          <select data-testid="ticket-priority" value={priority} onChange={e => setPriority(e.target.value)} style={{ ...inputStyle, marginTop: 10 }}>
            <option value="low">Low</option>
            <option value="normal">Normal</option>
            <option value="high">High</option>
          </select>
          <button data-testid="ticket-submit-btn" style={{ ...primaryBtn, marginTop: 12 }}>Submit ticket</button>
        </form>
      </div>
      <div style={cardStyle}>
        <h3 style={{ marginTop: 0 }}>My tickets</h3>
        {tickets.length === 0 ? <div style={{ color: "#9d93b5", fontSize: 13 }} data-testid="tickets-empty">No tickets yet.</div> : (
          <div style={{ display: "grid", gap: 10 }}>
            {tickets.map(t => (
              <div key={t.id} data-testid={`ticket-item-${t.id}`} style={{ padding: 12, background: "rgba(255,255,255,0.04)", borderRadius: 10, border: "1px solid rgba(255,255,255,0.08)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <b>{t.subject}</b>
                  <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 999, background: t.status === "open" ? "#ff9a3c" : t.status === "answered" ? "#4caf50" : "#6b6b6b" }}>{t.status}</span>
                </div>
                <div style={{ fontSize: 12, color: "#9d93b5", marginTop: 4 }}>{t.message?.slice(0,120)}{t.message?.length > 120 ? "…" : ""}</div>
                {t.responses?.length > 0 && (
                  <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px dashed rgba(255,255,255,0.08)" }}>
                    {t.responses.map((r, i) => (
                      <div key={i} style={{ fontSize: 12, marginTop: 4 }}>
                        <b style={{ color: "#ffb44c" }}>{r.author}:</b> {r.message}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// ============= ADMIN EXTENSIONS =============
export const AdminExtensions = ({ embedded = false }) => {
  const [tab, setTab] = useState("compliance");
  const content = (
    <div style={{ maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
        {[
          { id: "compliance", label: "Compliance", icon: <ShieldCheck size={16} /> },
          { id: "pool", label: "Distributor Pool", icon: <Network size={16} /> },
          { id: "alerts", label: "JIT Alerts", icon: <ShieldAlert size={16} /> },
          { id: "analytics", label: "Analytics", icon: <BarChart3 size={16} /> },
          { id: "promo", label: "Promo Codes", icon: <TicketPercent size={16} /> },
          { id: "tickets", label: "Support Tickets", icon: <LifeBuoy size={16} /> },
        ].map((t) => (
          <button
            key={t.id}
            data-testid={`admin-ext-tab-${t.id}`}
            onClick={() => setTab(t.id)}
            style={{
              ...secondaryBtn,
              fontSize: 14,
              padding: "10px 16px",
              borderColor: tab === t.id ? "#ffb44c" : "rgba(255,255,255,0.22)",
              background: tab === t.id ? "rgba(255,180,60,0.18)" : "rgba(255,255,255,0.08)",
              color: tab === t.id ? "#ffb44c" : "#f0e9ff",
              fontWeight: tab === t.id ? 700 : 500,
              display: "inline-flex", alignItems: "center", gap: 8,
            }}
          >{t.icon}{t.label}</button>
        ))}
      </div>
      {tab === "compliance" && <AdminCompliance />}
      {tab === "analytics" && <AdminAnalytics />}
      {tab === "promo" && <AdminPromo />}
      {tab === "tickets" && <AdminTickets />}
      {tab === "alerts" && <AdminAlerts />}
      {tab === "pool" && <AdminProxyPool />}
    </div>
  );
  if (embedded) return <div data-testid="admin-extensions-page">{content}</div>;
  return (
    <div style={shellStyle} data-testid="admin-extensions-page">
      <Header title="Admin extensions" back="/admin" />
      {content}
    </div>
  );
};

const AdminAnalytics = () => {
  const [overview, setOverview] = useState(null);
  const [rev, setRev] = useState([]);
  const [signups, setSignups] = useState([]);
  const [topUsers, setTopUsers] = useState([]);

  useEffect(() => {
    axios.get(`${API}/ext/admin/analytics/overview`).then(r => setOverview(r.data)).catch(() => {});
    axios.get(`${API}/ext/admin/analytics/revenue-by-day?days=14`).then(r => setRev(r.data)).catch(() => {});
    axios.get(`${API}/ext/admin/analytics/signups-by-day?days=14`).then(r => setSignups(r.data)).catch(() => {});
    axios.get(`${API}/ext/admin/analytics/top-users?limit=10`).then(r => setTopUsers(r.data)).catch(() => {});
  }, []);

  const Stat = ({ label, value, testid, icon }) => (
    <div style={{ ...cardStyle, padding: 18 }} data-testid={testid}>
      <div style={{ color: "#9d93b5", fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>{icon}{label}</div>
      <div style={{ fontSize: 28, fontWeight: 800, marginTop: 6 }}>{value}</div>
    </div>
  );

  return (
    <div style={{ display: "grid", gap: 18 }}>
      <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(180px,1fr))" }}>
        {overview && (
          <>
            <Stat testid="stat-total-users" label="Total users" value={overview.total_users} icon={<Users size={14} />} />
            <Stat testid="stat-new-users" label="New users (7d)" value={overview.new_users_7d} icon={<Sparkles size={14} />} />
            <Stat testid="stat-revenue" label="Total revenue" value={`$${(overview.total_revenue || 0).toFixed(2)}`} icon={<Zap size={14} />} />
            <Stat testid="stat-completed-tx" label="Completed tx" value={overview.completed_transactions} icon={<Trophy size={14} />} />
            <Stat testid="stat-promos" label="Promo redemptions" value={overview.promo_redeemed} icon={<TicketPercent size={14} />} />
            <Stat testid="stat-referrals" label="Referrals" value={overview.referrals} icon={<UserPlus size={14} />} />
            <Stat testid="stat-open-tickets" label="Open tickets" value={overview.open_tickets} icon={<LifeBuoy size={14} />} />
          </>
        )}
      </div>
      <div style={{ ...cardStyle }} data-testid="chart-revenue">
        <h3 style={{ margin: "0 0 12px" }}>Revenue (last 14 days)</h3>
        <div style={{ width: "100%", height: 260 }}>
          <ResponsiveContainer>
            <LineChart data={rev}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="date" stroke="#9d93b5" tick={{ fontSize: 11 }} />
              <YAxis stroke="#9d93b5" tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "#1a0b2e", border: "1px solid #ffb44c" }} />
              <Line type="monotone" dataKey="revenue" stroke="#ffb44c" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div style={{ ...cardStyle }} data-testid="chart-signups">
        <h3 style={{ margin: "0 0 12px" }}>Signups (last 14 days)</h3>
        <div style={{ width: "100%", height: 260 }}>
          <ResponsiveContainer>
            <BarChart data={signups}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="date" stroke="#9d93b5" tick={{ fontSize: 11 }} />
              <YAxis stroke="#9d93b5" tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "#1a0b2e", border: "1px solid #ffb44c" }} />
              <Bar dataKey="signups" fill="#ff5b5b" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div style={cardStyle} data-testid="table-top-users">
        <h3 style={{ margin: "0 0 12px" }}>Top users by spend</h3>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ color: "#9d93b5", textAlign: "left" }}>
              <th style={{ padding: 8 }}>Email</th><th style={{ padding: 8 }}>Spend</th>
            </tr>
          </thead>
          <tbody>
            {topUsers.map((u, i) => (
              <tr key={i} style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                <td style={{ padding: 8 }}>{u.email}</td>
                <td style={{ padding: 8 }}>${u.total_spend.toFixed(2)}</td>
              </tr>
            ))}
            {topUsers.length === 0 && <tr><td colSpan={2} style={{ color: "#9d93b5", padding: 12 }}>No data yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const AdminPromo = () => {
  const [list, setList] = useState([]);
  const [form, setForm] = useState({ code: "", bonus_credits: 100, max_uses: 0, description: "" });

  const load = async () => { try { const { data } = await axios.get(`${API}/ext/admin/promo`); setList(data); } catch (err) { console.error("Extensions error:", err); } };
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/ext/admin/promo`, { ...form, bonus_credits: Number(form.bonus_credits), max_uses: Number(form.max_uses) });
      toast.success("Promo created");
      setForm({ code: "", bonus_credits: 100, max_uses: 0, description: "" });
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const del = async (id) => {
    if (!window.confirm("Delete this promo?")) return;
    try { await axios.delete(`${API}/ext/admin/promo/${id}`); load(); } catch (err) { console.error("Extensions error:", err); }
  };

  return (
    <div style={{ display: "grid", gap: 18 }}>
      <div style={cardStyle}>
        <h3 style={{ marginTop: 0 }}>Create promo code</h3>
        <form onSubmit={create} style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
          <input data-testid="admin-promo-code" placeholder="CODE" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} required style={inputStyle} />
          <input data-testid="admin-promo-credits" type="number" min="1" placeholder="Credits" value={form.bonus_credits} onChange={(e) => setForm({ ...form, bonus_credits: e.target.value })} required style={inputStyle} />
          <input data-testid="admin-promo-max-uses" type="number" min="0" placeholder="Max uses (0=∞)" value={form.max_uses} onChange={(e) => setForm({ ...form, max_uses: e.target.value })} style={inputStyle} />
          <input data-testid="admin-promo-desc" placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} style={inputStyle} />
          <button data-testid="admin-promo-create-btn" style={primaryBtn}>Create</button>
        </form>
      </div>
      <div style={cardStyle}>
        <h3 style={{ marginTop: 0 }}>Active promos</h3>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead><tr style={{ color: "#9d93b5", textAlign: "left" }}>
            <th style={{ padding: 8 }}>Code</th><th style={{ padding: 8 }}>Credits</th><th style={{ padding: 8 }}>Uses</th><th style={{ padding: 8 }}>Desc</th><th />
          </tr></thead>
          <tbody>
            {list.map(p => (
              <tr key={p.id} data-testid={`admin-promo-row-${p.code}`} style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                <td style={{ padding: 8, fontFamily: "monospace", color: "#ffb44c" }}>{p.code}</td>
                <td style={{ padding: 8 }}>{p.bonus_credits}</td>
                <td style={{ padding: 8 }}>{p.uses_count}{p.max_uses ? `/${p.max_uses}` : "/∞"}</td>
                <td style={{ padding: 8, color: "#cfc3e8" }}>{p.description}</td>
                <td style={{ padding: 8, textAlign: "right" }}>
                  <button data-testid={`admin-promo-delete-${p.code}`} onClick={() => del(p.id)} style={secondaryBtn}>Delete</button>
                </td>
              </tr>
            ))}
            {list.length === 0 && <tr><td colSpan={5} style={{ padding: 12, color: "#9d93b5" }}>No promos yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const AdminTickets = () => {
  const [tickets, setTickets] = useState([]);
  const [filter, setFilter] = useState("");
  const [replyId, setReplyId] = useState(null);
  const [reply, setReply] = useState("");

  const load = async () => {
    try { const { data } = await axios.get(`${API}/ext/admin/support/tickets${filter ? `?status=${filter}` : ""}`); setTickets(data); } catch (err) { console.error("Extensions error:", err); }
  };
  useEffect(() => { load(); }, [filter]);

  const sendReply = async (id) => {
    try {
      await axios.post(`${API}/ext/admin/support/tickets/${id}/respond`, { message: reply });
      toast.success("Replied");
      setReplyId(null); setReply(""); load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const close = async (id) => {
    try { await axios.post(`${API}/ext/admin/support/tickets/${id}/close`); load(); } catch (err) { console.error("Extensions error:", err); }
  };

  return (
    <div style={{ display: "grid", gap: 18 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {["", "open", "answered", "closed"].map(s => (
          <button key={s || "all"} data-testid={`admin-tickets-filter-${s || "all"}`} onClick={() => setFilter(s)} style={{ ...secondaryBtn, borderColor: filter === s ? "#ffb44c" : "rgba(255,255,255,0.14)" }}>
            {s || "all"}
          </button>
        ))}
      </div>
      <div style={cardStyle}>
        {tickets.length === 0 ? <div style={{ color: "#9d93b5" }} data-testid="admin-tickets-empty">No tickets.</div> : (
          <div style={{ display: "grid", gap: 10 }}>
            {tickets.map(t => (
              <div key={t.id} data-testid={`admin-ticket-${t.id}`} style={{ padding: 14, border: "1px solid rgba(255,255,255,0.08)", borderRadius: 10, background: "rgba(255,255,255,0.03)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap" }}>
                  <div>
                    <b>{t.subject}</b>
                    <div style={{ fontSize: 12, color: "#9d93b5" }}>{t.user_email} • priority: {t.priority}</div>
                  </div>
                  <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 999, background: t.status === "open" ? "#ff9a3c" : t.status === "answered" ? "#4caf50" : "#6b6b6b" }}>{t.status}</span>
                </div>
                <div style={{ marginTop: 8, fontSize: 13, color: "#cfc3e8" }}>{t.message}</div>
                {t.responses?.length > 0 && (
                  <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px dashed rgba(255,255,255,0.08)" }}>
                    {t.responses.map((r, i) => (
                      <div key={i} style={{ fontSize: 12 }}><b style={{ color: "#ffb44c" }}>{r.author}:</b> {r.message}</div>
                    ))}
                  </div>
                )}
                <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                  {replyId === t.id ? (
                    <>
                      <input data-testid={`admin-ticket-reply-input-${t.id}`} placeholder="Reply…" value={reply} onChange={e => setReply(e.target.value)} style={{ ...inputStyle, flex: 1 }} />
                      <button data-testid={`admin-ticket-send-reply-${t.id}`} onClick={() => sendReply(t.id)} style={secondaryBtn}>Send</button>
                      <button onClick={() => { setReplyId(null); setReply(""); }} style={secondaryBtn}>Cancel</button>
                    </>
                  ) : (
                    <>
                      {t.status !== "closed" && <button data-testid={`admin-ticket-reply-${t.id}`} onClick={() => setReplyId(t.id)} style={secondaryBtn}>Reply</button>}
                      {t.status !== "closed" && <button data-testid={`admin-ticket-close-${t.id}`} onClick={() => close(t.id)} style={secondaryBtn}>Close</button>}
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const AdminAlerts = () => {
  const [alerts, setAlerts] = useState([]);
  const [filter, setFilter] = useState("open");

  const load = async () => {
    try {
      const { data } = await axios.get(`${API}/ext/platform/alerts?status=${filter}`);
      setAlerts(data);
    } catch { /* ignore */ }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [filter]);

  const resolve = async (id) => {
    try {
      await axios.post(`${API}/ext/platform/alerts/${id}/resolve`, { resolution: "acknowledged" });
      toast.success("Alert resolved");
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const retry = async (a) => {
    try {
      const { data } = await axios.post(`${API}/ext/platform/admin/retry/${a.user_id}/${a.game_id}`);
      if (data.status === "ok") {
        toast.success(`Re-registered: ${data.platform_uid}`);
      } else {
        toast.error(data.message || "Retry failed");
      }
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Retry failed"); }
  };

  return (
    <div style={{ display: "grid", gap: 18 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {["open", "resolved"].map(s => (
          <button key={s} data-testid={`admin-alerts-filter-${s}`} onClick={() => setFilter(s)} style={{ ...secondaryBtn, borderColor: filter === s ? "#ffb44c" : "rgba(255,255,255,0.14)" }}>{s}</button>
        ))}
      </div>
      <div style={cardStyle}>
        {alerts.length === 0 ? <div style={{ color: "#9d93b5" }} data-testid="admin-alerts-empty">No {filter} alerts.</div> : (
          <div style={{ display: "grid", gap: 10 }}>
            {alerts.map(a => (
              <div key={a.id} data-testid={`admin-alert-${a.id}`} style={{ padding: 14, border: "1px solid rgba(255,180,60,0.35)", borderRadius: 10, background: "rgba(255,90,90,0.08)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap" }}>
                  <div>
                    <b style={{ color: "#ffb44c" }}>{a.type}</b>
                    <div style={{ fontSize: 12, color: "#cfc3e8" }}>
                      {a.user_email} • {a.game_name} ({a.platform_id || a.game_id})
                    </div>
                  </div>
                  <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 999, background: a.status === "open" ? "#ff9a3c" : "#4caf50" }}>{a.status}</span>
                </div>
                <div style={{ marginTop: 8, fontSize: 13, color: "#f5e9ff" }}>{a.message}</div>
                <div style={{ fontSize: 11, color: "#9d93b5", marginTop: 6 }}>{a.created_at?.slice(0, 19)}</div>
                {a.status === "open" && (
                  <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                    <button data-testid={`admin-alert-retry-${a.id}`} onClick={() => retry(a)} style={secondaryBtn}>Retry registration</button>
                    <button data-testid={`admin-alert-resolve-${a.id}`} onClick={() => resolve(a.id)} style={secondaryBtn}>Mark resolved</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default SettingsPage;

// ============= ADMIN DISTRIBUTOR POOL (Hybrid Buffer Strategy) =============
const AdminProxyPool = () => {
  const [proxies, setProxies] = useState([]);
  const [health, setHealth] = useState(null);
  const [hubs, setHubs] = useState([]);
  const [matrix, setMatrix] = useState([]);
  const [readiness, setReadiness] = useState(null);
  const [showAdd, setShowAdd] = useState(false);
  const [showMatrix, setShowMatrix] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [pingAllBusy, setPingAllBusy] = useState(false);
  const [pingAllResult, setPingAllResult] = useState(null);
  const [form, setForm] = useState({
    label: "", username: "", password: "",
    hub_type: "sugar_sweeps",
    base_url: "https://sugarsweeps.com",
    per_transfer_cap: 500, daily_cap: 5000,
  });
  const [pingingId, setPingingId] = useState(null);
  const [pingResult, setPingResult] = useState(null);
  const [testTransfer, setTestTransfer] = useState(null);
  const [testForm, setTestForm] = useState({ recipient_username: "", amount: 1, platform: "fire_kirin" });
  const [testBusy, setTestBusy] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const load = async () => {
    try {
      const [p, h, hbs, mx, rd] = await Promise.all([
        axios.get(`${API}/ext/pool/admin/proxies`),
        axios.get(`${API}/ext/pool/admin/health`),
        axios.get(`${API}/ext/pool/admin/hubs`),
        axios.get(`${API}/ext/pool/admin/routing-matrix`),
        axios.get(`${API}/ext/pool/admin/launch-readiness`),
      ]);
      setProxies(p.data || []);
      setHealth(h.data || null);
      setHubs(hbs.data || []);
      setMatrix(mx.data || []);
      setReadiness(rd.data || null);
    } catch (e) {
      toast.error("Failed to load pool");
    }
  };
  useEffect(() => { load(); }, []);

  // Auto-refresh every 30s when enabled
  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh]);

  const pingAll = async () => {
    setPingAllBusy(true);
    setPingAllResult(null);
    try {
      const { data } = await axios.post(`${API}/ext/pool/admin/ping-all`, {}, { timeout: 120000 });
      setPingAllResult(data);
      if (data.failed === 0) toast.success(`All ${data.passed}/${data.total} proxies ping OK`);
      else toast.error(`${data.failed}/${data.total} proxies failed ping`);
      load();
    } catch (e) {
      toast.error("Ping-all error: " + (e?.response?.data?.detail || e.message));
    } finally {
      setPingAllBusy(false);
    }
  };

  // Auto-update base_url when hub_type changes
  useEffect(() => {
    const hub = hubs.find((h) => h.hub_type === form.hub_type);
    if (hub && form.base_url !== hub.base_url) {
      setForm((f) => ({ ...f, base_url: hub.base_url }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.hub_type, hubs]);

  const addProxy = async () => {
    if (!form.label || !form.username || !form.password) {
      toast.error("Label, username, and password are required"); return;
    }
    try {
      await axios.post(`${API}/ext/pool/admin/proxies`, {
        ...form,
        per_transfer_cap: Number(form.per_transfer_cap),
        daily_cap: Number(form.daily_cap),
      });
      toast.success("Proxy added to pool");
      setShowAdd(false);
      setForm({ label: "", username: "", password: "", hub_type: "sugar_sweeps", base_url: "https://sugarsweeps.com", per_transfer_cap: 500, daily_cap: 5000 });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to add proxy");
    }
  };

  const setStatus = async (id, status) => {
    try {
      await axios.patch(`${API}/ext/pool/admin/proxies/${id}`, { status });
      toast.success(`Proxy ${status}`);
      load();
    } catch (e) { toast.error("Update failed"); }
  };

  const unlock = async (id) => {
    try {
      await axios.post(`${API}/ext/pool/admin/proxies/${id}/unlock`);
      toast.success("Proxy unlocked");
      load();
    } catch (e) { toast.error("Unlock failed"); }
  };

  const removeProxy = async (id) => {
    if (!window.confirm("Delete this proxy permanently?")) return;
    try {
      await axios.delete(`${API}/ext/pool/admin/proxies/${id}`);
      toast.success("Deleted");
      load();
    } catch (e) { toast.error("Delete failed"); }
  };

  const ping = async (p) => {
    setPingingId(p.id);
    try {
      const { data } = await axios.post(`${API}/ext/pool/admin/proxies/${p.id}/ping`);
      setPingResult({ label: p.label, ...data });
      if (data.ok) toast.success(`Ping OK: ${data.message}`);
      else toast.error(`Ping failed`);
      load();
    } catch (e) {
      toast.error("Ping error");
    } finally {
      setPingingId(null);
    }
  };

  const openTestTransfer = (p) => {
    setTestTransfer(p);
    setTestForm({ recipient_username: "", amount: 1, platform: (p.supported_platforms?.[0] || "fire_kirin") });
    setTestResult(null);
  };

  const runTestTransfer = async () => {
    if (!testForm.recipient_username || testForm.amount <= 0) {
      toast.error("Recipient username and amount > 0 required");
      return;
    }
    setTestBusy(true);
    try {
      const { data } = await axios.post(
        `${API}/ext/pool/admin/proxies/${testTransfer.id}/test-transfer`,
        { recipient_username: testForm.recipient_username, amount: Number(testForm.amount), platform: testForm.platform }
      );
      setTestResult(data);
      if (data.ok) toast.success(`Transfer OK: ${data.message}`);
      else toast.error(`Transfer failed`);
      load();
    } catch (e) {
      toast.error("Transfer error: " + (e?.response?.data?.detail || e.message));
    } finally {
      setTestBusy(false);
    }
  };

  const StatusBadge = ({ status }) => {
    const colors = {
      active: { bg: "#4caf50", fg: "#fff" },
      cooldown: { bg: "#ff9a3c", fg: "#000" },
      locked: { bg: "#d32f2f", fg: "#fff" },
      disabled: { bg: "#555", fg: "#fff" },
    };
    const c = colors[status] || colors.disabled;
    return (
      <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 999, background: c.bg, color: c.fg, fontWeight: 700 }}>
        {status}
      </span>
    );
  };

  return (
    <div style={{ display: "grid", gap: 18 }} data-testid="admin-proxy-pool">
      {/* Pilot Launch Checklist */}
      {readiness && (
        <div
          data-testid="launch-readiness"
          style={{
            ...cardStyle,
            padding: 16,
            borderLeft: `4px solid ${readiness.ready ? "#4caf50" : "#ff9a3c"}`,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
            <div>
              <div style={{ fontSize: 12, color: "#9d93b5", letterSpacing: 1.5, textTransform: "uppercase" }}>Pilot Launch Checklist</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: readiness.ready ? "#8ee79a" : "#ffb44c", marginTop: 4 }}>
                {readiness.ready ? "🚀 READY FOR LIVE TRAFFIC" : `⚠ ${readiness.summary}`}
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#cfc3e8", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                  data-testid="pool-autorefresh"
                />
                Auto-refresh (30s)
              </label>
              <button data-testid="pool-pingall" disabled={pingAllBusy || proxies.length === 0} onClick={pingAll} style={{ ...secondaryBtn, display: "inline-flex", alignItems: "center", gap: 6, opacity: pingAllBusy ? 0.6 : 1 }}>
                <Radio size={14} /> {pingAllBusy ? "Pinging all…" : "Ping all"}
              </button>
            </div>
          </div>
          <div style={{ display: "grid", gap: 8, marginTop: 14, gridTemplateColumns: "repeat(auto-fit, minmax(260px,1fr))" }}>
            {(readiness.checks || []).map((c, i) => (
              <div key={i} data-testid={`readiness-check-${i}`} style={{ padding: 10, borderRadius: 8, border: `1px solid ${c.ok ? "rgba(76,175,80,0.4)" : "rgba(255,154,60,0.4)"}`, background: c.ok ? "rgba(76,175,80,0.08)" : "rgba(255,154,60,0.08)" }}>
                <div style={{ fontSize: 12, color: c.ok ? "#8ee79a" : "#ffb44c", fontWeight: 700 }}>
                  {c.ok ? "✓" : "✗"} {c.name}
                </div>
                <div style={{ fontSize: 11, color: "#cfc3e8", marginTop: 3, lineHeight: 1.4 }}>{c.detail}</div>
              </div>
            ))}
          </div>
          {pingAllResult && (
            <details style={{ marginTop: 10 }} open>
              <summary style={{ cursor: "pointer", fontSize: 12, color: "#9d93b5" }}>
                Last Ping-all: {pingAllResult.passed} passed · {pingAllResult.failed} failed
              </summary>
              <div style={{ display: "grid", gap: 4, marginTop: 8, fontSize: 11 }}>
                {(pingAllResult.results || []).map((r) => (
                  <div key={r.id} data-testid={`pingall-result-${r.id}`} style={{ padding: 6, borderRadius: 4, background: r.ok ? "rgba(76,175,80,0.1)" : "rgba(211,47,47,0.1)" }}>
                    <b style={{ color: r.ok ? "#8ee79a" : "#ff6b6b" }}>{r.ok ? "✓" : "✗"} {r.label}</b>
                    <span style={{ color: "#9d93b5", marginLeft: 8 }}>({r.hub_type})</span>
                    <span style={{ color: "#cfc3e8", marginLeft: 8 }}>{r.message}</span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {health && (
        <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(140px,1fr))" }}>
          <div style={{ ...cardStyle, padding: 14 }} data-testid="pool-stat-total">
            <div style={{ color: "#9d93b5", fontSize: 11 }}>Total proxies</div>
            <div style={{ fontSize: 24, fontWeight: 800 }}>{health.total}</div>
          </div>
          <div style={{ ...cardStyle, padding: 14 }} data-testid="pool-stat-active">
            <div style={{ color: "#9d93b5", fontSize: 11 }}>Active</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: "#4caf50" }}>{health.active}</div>
          </div>
          <div style={{ ...cardStyle, padding: 14 }} data-testid="pool-stat-cooldown">
            <div style={{ color: "#9d93b5", fontSize: 11 }}>Cooldown</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: "#ff9a3c" }}>{health.cooldown}</div>
          </div>
          <div style={{ ...cardStyle, padding: 14 }} data-testid="pool-stat-locked">
            <div style={{ color: "#9d93b5", fontSize: 11 }}>Locked</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: "#d32f2f" }}>{health.locked}</div>
          </div>
          <div style={{ ...cardStyle, padding: 14 }} data-testid="pool-stat-capacity">
            <div style={{ color: "#9d93b5", fontSize: 11 }}>Capacity left today</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: "#ffb44c" }}>${health.daily_capacity_remaining.toFixed(2)}</div>
          </div>
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
        <div style={{ color: "#9d93b5", fontSize: 13, maxWidth: 640 }}>
          Rotation pool of Sugar Sweeps distributor accounts. Fund payouts route through the healthiest proxy automatically with per-transfer + daily caps and auto-cooldown on failures.
        </div>
        <button data-testid="pool-matrix-btn" onClick={() => setShowMatrix(!showMatrix)} style={{ ...secondaryBtn, display: "inline-flex", alignItems: "center", gap: 6 }}>
          <BarChart3 size={14} /> {showMatrix ? "Hide Matrix" : "Routing Matrix"}
        </button>
        <button data-testid="pool-add-btn" onClick={() => setShowAdd(!showAdd)} style={{ ...secondaryBtn, display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Plus size={14} /> {showAdd ? "Cancel" : "Add Proxy"}
        </button>
      </div>

      {showMatrix && (
        <div style={{ ...cardStyle }} data-testid="pool-matrix">
          <h3 style={{ marginTop: 0 }}>Routing Matrix — which proxies serve which game?</h3>
          <div style={{ fontSize: 12, color: "#9d93b5", marginBottom: 10 }}>
            Before launch, verify every game has at least one active proxy. Gaps = users with that game will hit "deposit held".
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.12)", color: "#9d93b5" }}>
                  <th style={{ textAlign: "left", padding: "8px 6px" }}>Game platform</th>
                  <th style={{ textAlign: "center", padding: "8px 6px" }}>Active coverage</th>
                  <th style={{ textAlign: "left", padding: "8px 6px" }}>Proxies that can serve it</th>
                </tr>
              </thead>
              <tbody>
                {matrix.map((row) => (
                  <tr key={row.platform} data-testid={`matrix-row-${row.platform}`} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                    <td style={{ padding: "8px 6px", fontWeight: 600 }}>{row.platform}</td>
                    <td style={{ padding: "8px 6px", textAlign: "center" }}>
                      <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 999, fontWeight: 700, background: row.active_coverage === 0 ? "#d32f2f" : row.active_coverage === 1 ? "#ff9a3c" : "#4caf50", color: "#fff" }}>
                        {row.active_coverage} / {row.total_coverage}
                      </span>
                    </td>
                    <td style={{ padding: "8px 6px" }}>
                      {row.proxies.length === 0 ? (
                        <span style={{ color: "#ff6b6b" }}>⚠ No proxy covers this — add one!</span>
                      ) : (
                        row.proxies.map((rp) => (
                          <span key={rp.id} style={{ display: "inline-block", marginRight: 6, marginBottom: 3, fontSize: 11, padding: "2px 8px", borderRadius: 6, background: rp.status === "active" ? "rgba(76,175,80,0.15)" : "rgba(120,120,120,0.2)", color: rp.status === "active" ? "#8ee79a" : "#9d93b5" }}>
                            {rp.label} <span style={{ opacity: 0.6 }}>({rp.hub_type})</span> · ${rp.capacity_remaining.toFixed(0)} left
                          </span>
                        ))
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Ping Diagnostic Modal */}
      {pingResult && (
        <PingDiagnosticModal
          result={pingResult}
          onClose={() => setPingResult(null)}
        />
      )}

      {/* Test Transfer Modal */}
      {testTransfer && (
        <TestTransferModal
          proxy={testTransfer}
          form={testForm}
          setForm={setTestForm}
          busy={testBusy}
          result={testResult}
          onRun={runTestTransfer}
          onClose={() => { setTestTransfer(null); setTestResult(null); }}
        />
      )}

      {showAdd && (
        <div style={{ ...cardStyle }} data-testid="pool-add-form">
          <h3 style={{ marginTop: 0 }}>Add distributor proxy</h3>
          <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(220px,1fr))" }}>
            <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#cfc3e8" }}>
              Distributor hub
              <select
                value={form.hub_type}
                onChange={(e) => setForm({ ...form, hub_type: e.target.value })}
                data-testid="pool-form-hub"
                style={{ padding: "10px 12px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.14)", background: "rgba(255,255,255,0.05)", color: "#f5e9ff", fontSize: 14 }}
              >
                {hubs.map((h) => (
                  <option key={h.hub_type} value={h.hub_type}>{h.label} ({h.hub_type})</option>
                ))}
              </select>
            </label>
            <PoolInput label="Label" value={form.label} onChange={(v) => setForm({ ...form, label: v })} testid="pool-form-label" placeholder="e.g., proxy-01" />
            <PoolInput label="Username / email" value={form.username} onChange={(v) => setForm({ ...form, username: v })} testid="pool-form-username" />
            <PoolInput label="Password" type="password" value={form.password} onChange={(v) => setForm({ ...form, password: v })} testid="pool-form-password" />
            <PoolInput label="Base URL" value={form.base_url} onChange={(v) => setForm({ ...form, base_url: v })} testid="pool-form-url" />
            <PoolInput label="Per-transfer cap ($)" type="number" value={form.per_transfer_cap} onChange={(v) => setForm({ ...form, per_transfer_cap: v })} testid="pool-form-per-tx" />
            <PoolInput label="Daily cap ($)" type="number" value={form.daily_cap} onChange={(v) => setForm({ ...form, daily_cap: v })} testid="pool-form-daily" />
          </div>
          <div style={{ fontSize: 11, color: "#9d93b5", marginTop: 8 }}>
            Supported platforms will auto-populate from the selected hub.
          </div>
          <button data-testid="pool-form-submit" onClick={addProxy} style={{ ...primaryBtn, marginTop: 12 }}>Save proxy</button>
        </div>
      )}

      {proxies.length === 0 ? (
        <div style={{ ...cardStyle, textAlign: "center", padding: 30, color: "#9d93b5" }} data-testid="pool-empty">
          No proxies yet. Add a pilot pool of 3 accounts to enable automatic payouts.
        </div>
      ) : (
        <div style={{ display: "grid", gap: 12 }} data-testid="pool-list">
          {proxies.map((p) => {
            const pct = p.daily_cap > 0 ? Math.min(100, (p.daily_volume_sent / p.daily_cap) * 100) : 0;
            return (
              <div key={p.id} data-testid={`pool-item-${p.id}`} style={{ ...cardStyle, padding: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <b style={{ color: "#ffb44c", fontSize: 16 }}>{p.label}</b>
                      <StatusBadge status={p.status} />
                      <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 999, background: "rgba(124,58,237,0.35)", color: "#e9d5ff", fontWeight: 700, textTransform: "uppercase" }}>
                        {p.hub_type || "sugar_sweeps"}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: "#cfc3e8", marginTop: 2 }}>
                      {p.username} · {p.base_url}
                    </div>
                    {p.supported_platforms?.length > 0 && (
                      <div style={{ fontSize: 10, color: "#9d93b5", marginTop: 3 }}>
                        Routes: {p.supported_platforms.join(", ")}
                      </div>
                    )}
                    {p.lock_reason && <div style={{ fontSize: 11, color: "#ff6b6b", marginTop: 4 }}>Lock reason: {p.lock_reason}</div>}
                    {p.cooldown_until && <div style={{ fontSize: 11, color: "#ff9a3c", marginTop: 4 }}>Cooldown until: {p.cooldown_until.slice(0, 19)}</div>}
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <button data-testid={`pool-ping-${p.id}`} disabled={pingingId === p.id} onClick={() => ping(p)} style={{ ...secondaryBtn, display: "inline-flex", alignItems: "center", gap: 4 }}>
                      <Radio size={13} /> {pingingId === p.id ? "Pinging…" : "Ping"}
                    </button>
                    <button data-testid={`pool-test-${p.id}`} onClick={() => openTestTransfer(p)} style={{ ...secondaryBtn, display: "inline-flex", alignItems: "center", gap: 4 }}>
                      <Zap size={13} /> Test Transfer
                    </button>
                    {p.status === "locked" && (
                      <button data-testid={`pool-unlock-${p.id}`} onClick={() => unlock(p.id)} style={{ ...secondaryBtn, display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <Unlock size={13} /> Unlock
                      </button>
                    )}
                    {p.status !== "disabled" ? (
                      <button data-testid={`pool-disable-${p.id}`} onClick={() => setStatus(p.id, "disabled")} style={{ ...secondaryBtn, display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <Power size={13} /> Disable
                      </button>
                    ) : (
                      <button data-testid={`pool-enable-${p.id}`} onClick={() => setStatus(p.id, "active")} style={{ ...secondaryBtn, display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <Power size={13} /> Enable
                      </button>
                    )}
                    <button data-testid={`pool-delete-${p.id}`} onClick={() => removeProxy(p.id)} style={{ ...secondaryBtn, display: "inline-flex", alignItems: "center", gap: 4 }}>
                      <Trash2 size={13} /> Delete
                    </button>
                  </div>
                </div>
                <div style={{ marginTop: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#9d93b5" }}>
                    <span>Today: ${p.daily_volume_sent.toFixed(2)} / ${p.daily_cap.toFixed(2)}</span>
                    <span>Per-tx cap: ${p.per_transfer_cap.toFixed(2)} · Failures: {p.consecutive_failures}</span>
                  </div>
                  <div style={{ height: 6, background: "rgba(255,255,255,0.08)", borderRadius: 4, marginTop: 4, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${pct}%`, background: pct > 80 ? "#ff9a3c" : "#ffb44c" }} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

// --- Ping Diagnostic Modal ---
const PingDiagnosticModal = ({ result, onClose }) => (
  <div data-testid="ping-modal" onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.65)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
    <div onClick={(e) => e.stopPropagation()} style={{ ...cardStyle, maxWidth: 720, width: "100%", maxHeight: "80vh", overflow: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <h3 style={{ margin: 0 }}>Ping diagnostic — {result.label}</h3>
        <button data-testid="ping-modal-close" onClick={onClose} style={secondaryBtn}>Close</button>
      </div>
      <div style={{ padding: 12, borderRadius: 8, background: result.ok ? "rgba(76,175,80,0.12)" : "rgba(211,47,47,0.12)", border: `1px solid ${result.ok ? "#4caf50" : "#d32f2f"}`, marginBottom: 12 }}>
        <b style={{ color: result.ok ? "#8ee79a" : "#ff6b6b" }}>{result.ok ? "✓ Login successful" : "✗ Login failed"}</b>
        <div style={{ fontSize: 13, marginTop: 4 }}>{result.message}</div>
      </div>
      <div style={{ fontSize: 12, color: "#9d93b5", marginBottom: 6 }}>Step-by-step trace:</div>
      <div style={{ display: "grid", gap: 6, fontFamily: "monospace", fontSize: 12 }}>
        {(result.diagnostic?.steps || []).map((s, i) => (
          <div key={i} style={{ padding: 8, borderRadius: 6, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}>
            <b style={{ color: "#ffb44c" }}>{s.step}</b>
            {Object.entries(s).filter(([k]) => k !== "step").map(([k, v]) => (
              <div key={k} style={{ color: "#cfc3e8", marginLeft: 10 }}>
                <span style={{ color: "#9d93b5" }}>{k}:</span> {typeof v === "string" ? v : JSON.stringify(v)}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  </div>
);

// --- Test Transfer Modal ---
const TestTransferModal = ({ proxy, form, setForm, busy, result, onRun, onClose }) => (
  <div data-testid="test-modal" onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.65)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
    <div onClick={(e) => e.stopPropagation()} style={{ ...cardStyle, maxWidth: 560, width: "100%", maxHeight: "80vh", overflow: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <h3 style={{ margin: 0 }}>Test transfer via {proxy.label}</h3>
        <button data-testid="test-modal-close" onClick={onClose} style={secondaryBtn}>Close</button>
      </div>
      <div style={{ fontSize: 12, color: "#9d93b5", marginBottom: 10 }}>
        Pinned to this specific proxy. Uses REAL P2P on <b>{proxy.base_url}</b>. Start with $1 amount.
      </div>
      <div style={{ display: "grid", gap: 10 }}>
        <PoolInput label="Recipient username (master name of target user)" value={form.recipient_username} onChange={(v) => setForm({ ...form, recipient_username: v })} testid="test-recipient" placeholder="e.g., sugarab123" />
        <PoolInput label="Amount ($)" type="number" value={form.amount} onChange={(v) => setForm({ ...form, amount: v })} testid="test-amount" />
        <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#cfc3e8" }}>
          Target game platform
          <select
            value={form.platform}
            onChange={(e) => setForm({ ...form, platform: e.target.value })}
            data-testid="test-platform"
            style={{ padding: "10px 12px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.14)", background: "rgba(255,255,255,0.05)", color: "#f5e9ff", fontSize: 14 }}
          >
            {(proxy.supported_platforms || []).map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
      </div>
      <button data-testid="test-run" disabled={busy} onClick={onRun} style={{ ...primaryBtn, marginTop: 14, opacity: busy ? 0.6 : 1 }}>
        {busy ? "Running…" : "Run test transfer"}
      </button>
      {result && (
        <div style={{ marginTop: 14, padding: 12, borderRadius: 8, background: result.ok ? "rgba(76,175,80,0.12)" : "rgba(211,47,47,0.12)", border: `1px solid ${result.ok ? "#4caf50" : "#d32f2f"}` }}>
          <b style={{ color: result.ok ? "#8ee79a" : "#ff6b6b" }}>{result.ok ? "✓ Transfer succeeded" : "✗ Transfer failed"}</b>
          <div style={{ fontSize: 13, marginTop: 4 }}>{result.message}</div>
          {result.diagnostic?.steps && (
            <details style={{ marginTop: 10 }}>
              <summary style={{ cursor: "pointer", fontSize: 12, color: "#9d93b5" }}>Show diagnostic steps</summary>
              <div style={{ display: "grid", gap: 4, fontFamily: "monospace", fontSize: 11, marginTop: 8 }}>
                {result.diagnostic.steps.map((s, i) => (
                  <div key={i} style={{ padding: 6, background: "rgba(255,255,255,0.04)", borderRadius: 4 }}>
                    <b style={{ color: "#ffb44c" }}>{s.step}</b>{" "}
                    {Object.entries(s).filter(([k]) => k !== "step").map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`).join(" · ")}
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </div>
  </div>
);

const PoolInput = ({ label, value, onChange, type = "text", placeholder = "", testid }) => (
  <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#cfc3e8" }}>
    {label}
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      data-testid={testid}
      style={{
        padding: "10px 12px",
        borderRadius: 8,
        border: "1px solid rgba(255,255,255,0.14)",
        background: "rgba(255,255,255,0.05)",
        color: "#f5e9ff",
        fontSize: 14,
      }}
    />
  </label>
);

// ============================================================
// Compliance admin panel — KYC queue, Payout hold queue, AML,
// OFAC hits, Geoblock config.
// ============================================================
const AdminCompliance = () => {
  const [view, setView] = useState("dashboard");
  const [overview, setOverview] = useState(null);
  const [kycQueue, setKycQueue] = useState([]);
  const [payoutQueue, setPayoutQueue] = useState([]);
  const [amlEvents, setAmlEvents] = useState([]);
  const [ofacHits, setOfacHits] = useState([]);
  const [flags, setFlags] = useState({});
  const [loading, setLoading] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [ov, kq, pq, am, oh, ff] = await Promise.all([
        axios.get(`${API}/ext/compliance/admin/overview`),
        axios.get(`${API}/ext/compliance/admin/kyc/queue`),
        axios.get(`${API}/ext/compliance/admin/payouts/queue`),
        axios.get(`${API}/ext/compliance/admin/aml/events?limit=50`),
        axios.get(`${API}/ext/compliance/admin/ofac/hits?limit=50`),
        axios.get(`${API}/ext/compliance/admin/feature-flags`),
      ]);
      setOverview(ov.data);
      setKycQueue(kq.data || []);
      setPayoutQueue(pq.data || []);
      setAmlEvents(am.data || []);
      setOfacHits(oh.data || []);
      setFlags(ff.data || {});
    } catch (e) { toast.error("Failed to load compliance data"); }
    setLoading(false);
  };

  const toggleFlag = async (key, value) => {
    try {
      const r = await axios.patch(`${API}/ext/compliance/admin/feature-flags`, { key, value });
      setFlags(r.data);
      toast.success(`${key} → ${value ? "ON" : "OFF"}`);
    } catch (e) { toast.error(`Flag update failed: ${e?.response?.data?.detail || e.message}`); }
  };

  useEffect(() => { loadAll(); }, []);

  const refreshOfac = async () => {
    try {
      const r = await axios.post(`${API}/ext/compliance/admin/ofac/refresh`);
      toast.success(`OFAC list refreshed: ${r.data.count} entries (${r.data.source})`);
      loadAll();
    } catch { toast.error("OFAC refresh failed"); }
  };

  const decideKyc = async (userId, tier, decision) => {
    const notes = window.prompt(`Notes for ${decision} (optional):`, "");
    if (notes === null) return;
    try {
      await axios.post(`${API}/ext/compliance/admin/kyc/decide`, { user_id: userId, tier, decision, notes });
      toast.success(`KYC ${decision}d`);
      loadAll();
    } catch (e) { toast.error(`KYC decision failed: ${e?.response?.data?.detail || e.message}`); }
  };

  const actPayout = async (redemptionId, action) => {
    const notes = window.prompt(`Notes for ${action} (optional):`, "");
    if (notes === null) return;
    if (action === "approve" && !window.confirm("Approve this BTC payout? This will attempt to send real Bitcoin via the configured gateway.")) return;
    try {
      const r = await axios.post(`${API}/ext/compliance/admin/payouts/action`, { redemption_id: redemptionId, action, notes });
      toast.success(`Payout ${action}d — status: ${r.data.status}`);
      loadAll();
    } catch (e) { toast.error(`Payout action failed: ${e?.response?.data?.detail || e.message}`); }
  };

  const statCard = (label, value, tone = "neutral", testid) => {
    const toneColor = { good: "#3aff9c", bad: "#ff4d6d", warn: "#ffb44c", neutral: "#cfc3e8" }[tone];
    return (
      <div data-testid={testid} style={{
        padding: 16, borderRadius: 12, background: "rgba(255,255,255,0.04)",
        border: `1px solid ${toneColor}33`, minWidth: 140,
      }}>
        <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1, color: "#a593c2", marginBottom: 6 }}>{label}</div>
        <div style={{ fontSize: 28, fontWeight: 700, color: toneColor }}>{value}</div>
      </div>
    );
  };

  const subtabs = [
    { id: "dashboard", label: "Dashboard" },
    { id: "kyc", label: `KYC queue (${kycQueue.length})` },
    { id: "payouts", label: `Payout hold (${payoutQueue.length})` },
    { id: "aml", label: "AML events" },
    { id: "ofac", label: "OFAC hits" },
  ];

  return (
    <div data-testid="admin-compliance-panel" style={{ color: "#f0e9ff" }}>
      <div style={{
        padding: 14, marginBottom: 16, borderRadius: 10,
        background: "rgba(255, 71, 87, 0.08)", border: "1px solid rgba(255, 71, 87, 0.35)",
        fontSize: 13, color: "#ffd4d8",
      }}>
        <strong style={{ color: "#ff4757" }}>LEGAL NOTICE.</strong> Real-money BTC payouts in a sweepstakes business typically require
        FinCEN MSB registration and state Money Transmitter Licenses. This dashboard gives you the
        compliance audit trail — it is NOT a substitute for counsel. Every decision you make here is
        logged in <code>kyc_events</code> / <code>admin_alerts</code> for your regulator.
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {subtabs.map(s => (
          <button
            key={s.id}
            data-testid={`compliance-subtab-${s.id}`}
            onClick={() => setView(s.id)}
            style={{
              padding: "8px 14px", borderRadius: 8, fontSize: 13, cursor: "pointer",
              border: "1px solid " + (view === s.id ? "#ffb44c" : "rgba(255,255,255,0.14)"),
              background: view === s.id ? "rgba(255,180,60,0.18)" : "rgba(255,255,255,0.04)",
              color: view === s.id ? "#ffb44c" : "#cfc3e8", fontWeight: view === s.id ? 700 : 500,
            }}
          >{s.label}</button>
        ))}
        <button onClick={loadAll} data-testid="compliance-refresh-btn" style={{
          marginLeft: "auto", padding: "8px 14px", borderRadius: 8, fontSize: 13, cursor: "pointer",
          border: "1px solid rgba(255,255,255,0.14)", background: "rgba(255,255,255,0.04)", color: "#cfc3e8",
        }}>{loading ? "Loading…" : "Refresh"}</button>
      </div>

      {view === "dashboard" && overview && (
        <div>
          {/* Master feature flag switches */}
          <div style={{
            padding: 18, marginBottom: 22, borderRadius: 3,
            background: "linear-gradient(145deg, rgba(14,12,9,0.95), rgba(7,6,5,0.95))",
            border: "1px solid rgba(201, 169, 97, 0.35)",
          }}>
            <div style={{
              fontFamily: "'Cinzel', serif", fontSize: 13, fontWeight: 500,
              letterSpacing: "0.3em", color: "#c9a961", textTransform: "uppercase",
              marginBottom: 14, textAlign: "center",
            }}>Master Switches</div>
            {[
              { key: "btc_payouts_enabled", label: "Bitcoin Payouts", desc: "Enable cash-equivalent BTC redemption. Leave OFF until MSB/MTL legal review is complete.", danger: true },
              { key: "redeem_tab_visible", label: "User-Side Redeem Tab", desc: "Show the Redeem tab on the player dashboard." },
              { key: "withdraw_tab_visible", label: "User-Side Withdraw Tab", desc: "Show the Withdraw (BTC) tab on the player dashboard." },
              { key: "giftcard_redemption_enabled", label: "Gift Card Redemption", desc: "Alternative prize path (Amazon/Visa gift cards) while BTC is disabled." },
            ].map(f => {
              const on = !!flags[f.key];
              return (
                <div key={f.key} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "12px 0", borderTop: "1px solid rgba(201, 169, 97, 0.1)",
                  gap: 16,
                }}>
                  <div style={{ flex: 1 }}>
                    <div style={{
                      fontFamily: "'Cinzel', serif", fontSize: 12, letterSpacing: "0.22em",
                      color: f.danger && on ? "#ff6b6b" : "#ece2cd", textTransform: "uppercase",
                      fontWeight: 600,
                    }}>{f.label}</div>
                    <div style={{
                      fontFamily: "'Cormorant Garamond', serif", fontStyle: "italic",
                      fontSize: 13, color: "#8a8278", marginTop: 4,
                    }}>{f.desc}</div>
                  </div>
                  <button
                    type="button"
                    data-testid={`flag-toggle-${f.key}`}
                    onClick={() => toggleFlag(f.key, !on)}
                    aria-pressed={on}
                    style={{
                      position: "relative",
                      width: 60, height: 30, borderRadius: 30,
                      background: on
                        ? (f.danger ? "linear-gradient(180deg, #ff6b6b, #c44)" : "linear-gradient(180deg, #e6c976, #8a7540)")
                        : "rgba(20,20,26,0.8)",
                      border: "1px solid " + (on ? (f.danger ? "#ff6b6b" : "#c9a961") : "rgba(201,169,97,0.3)"),
                      cursor: "pointer",
                      boxShadow: on ? "inset 0 1px 0 rgba(255,255,255,0.25), 0 4px 14px rgba(201,169,97,0.25)" : "inset 0 1px 2px rgba(0,0,0,0.5)",
                      transition: "all 0.2s ease",
                      flexShrink: 0,
                    }}
                  >
                    <span style={{
                      position: "absolute",
                      top: 3, left: on ? 33 : 3,
                      width: 22, height: 22, borderRadius: "50%",
                      background: "#fff",
                      boxShadow: "0 2px 6px rgba(0,0,0,0.4)",
                      transition: "left 0.2s ease",
                    }} />
                  </button>
                </div>
              );
            })}
            {flags.btc_payouts_enabled && (
              <div style={{
                marginTop: 14, padding: 10, borderRadius: 2,
                background: "rgba(255, 107, 107, 0.1)", border: "1px solid rgba(255, 107, 107, 0.4)",
                fontFamily: "'Cormorant Garamond', serif", fontStyle: "italic",
                fontSize: 13, color: "#ffd4d8",
              }}>
                ⚠ BTC payouts are LIVE. Ensure you have active MSB registration + required state MTLs before approving any payout.
              </div>
            )}
          </div>

          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
            {statCard("KYC pending", overview.kyc.pending_review, overview.kyc.pending_review > 0 ? "warn" : "neutral", "stat-kyc-pending")}
            {statCard("KYC approved", overview.kyc.approved, "good", "stat-kyc-approved")}
            {statCard("KYC declined", overview.kyc.declined, "bad", "stat-kyc-declined")}
            {statCard("Payouts on hold", overview.payouts.hold_admin_review, overview.payouts.hold_admin_review > 0 ? "warn" : "neutral", "stat-payout-hold")}
            {statCard("Open alerts", overview.alerts.open, overview.alerts.open > 0 ? "bad" : "good", "stat-alerts-open")}
            {statCard("OFAC hits", overview.alerts.ofac_hits_all_time, overview.alerts.ofac_hits_all_time > 0 ? "bad" : "good", "stat-ofac-hits")}
          </div>
          <div style={{ padding: 16, borderRadius: 10, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)" }}>
            <h3 style={{ margin: "0 0 12px", fontSize: 15, color: "#ffb44c" }}>Configuration</h3>
            <div style={{ fontSize: 13, lineHeight: 1.8 }}>
              <div>KYC basic threshold: <strong style={{ color: "#fff" }}>${overview.thresholds.kyc_basic_usd}</strong></div>
              <div>KYC enhanced threshold: <strong style={{ color: "#fff" }}>${overview.thresholds.kyc_enhanced_usd}</strong></div>
              <div>CTR alert threshold: <strong style={{ color: "#fff" }}>${overview.thresholds.ctr_usd}</strong></div>
              <div>Persona KYC: <strong style={{ color: overview.persona_enabled ? "#3aff9c" : "#ffb44c" }}>{overview.persona_enabled ? "ENABLED" : "DISABLED — using manual upload fallback"}</strong></div>
              <div>Blocked states: <strong style={{ color: "#fff" }}>{overview.blocked_states.join(", ") || "none"}</strong></div>
            </div>
            <button onClick={refreshOfac} data-testid="ofac-refresh-btn" style={{
              marginTop: 14, padding: "8px 16px", borderRadius: 8, border: "1px solid #3aff9c44",
              background: "rgba(58,255,156,0.1)", color: "#3aff9c", fontSize: 13, cursor: "pointer",
            }}>Refresh OFAC SDN list</button>
          </div>
        </div>
      )}

      {view === "kyc" && (
        <div data-testid="compliance-kyc-queue">
          {kycQueue.length === 0 && <div style={{ padding: 20, color: "#a593c2" }}>No KYC items pending review.</div>}
          {kycQueue.map((k, i) => (
            <div key={i} style={{ padding: 14, marginBottom: 10, borderRadius: 10, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{k.user_email}</div>
                  <div style={{ fontSize: 12, color: "#a593c2" }}>tier: <strong>{k.tier}</strong> · method: {k.method} · status: <span style={{ color: k.status === "review" ? "#ffb44c" : "#cfc3e8" }}>{k.status}</span></div>
                  {k.uploaded_doc_id && <div style={{ fontSize: 11, color: "#888", marginTop: 4 }}>doc: {k.uploaded_doc_id}</div>}
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={() => decideKyc(k.user_id, k.tier, "approve")} data-testid={`kyc-approve-${k.user_id}-${k.tier}`} style={{ padding: "7px 14px", borderRadius: 8, border: "1px solid #3aff9c66", background: "rgba(58,255,156,0.15)", color: "#3aff9c", cursor: "pointer", fontSize: 13 }}>Approve</button>
                  <button onClick={() => decideKyc(k.user_id, k.tier, "reject")} data-testid={`kyc-reject-${k.user_id}-${k.tier}`} style={{ padding: "7px 14px", borderRadius: 8, border: "1px solid #ff4d6d66", background: "rgba(255,77,109,0.15)", color: "#ff4d6d", cursor: "pointer", fontSize: 13 }}>Reject</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {view === "payouts" && (
        <div data-testid="compliance-payout-queue">
          {payoutQueue.length === 0 && <div style={{ padding: 20, color: "#a593c2" }}>No payouts on hold.</div>}
          {payoutQueue.map(p => (
            <div key={p.id} style={{ padding: 14, marginBottom: 10, borderRadius: 10, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 10 }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{p.user_email || p.user_id}</div>
                  <div style={{ fontSize: 12, color: "#a593c2", marginTop: 2 }}>amount: <strong style={{ color: "#fff" }}>${p.amount_usd}</strong> ({p.game_credits} credits)</div>
                  <div style={{ fontSize: 11, color: "#888", marginTop: 2, fontFamily: "monospace" }}>{p.btc_address}</div>
                  <div style={{ fontSize: 11, color: "#888" }}>status: <span style={{ color: "#ffb44c" }}>{p.status}</span></div>
                </div>
                {p.status === "hold_admin_review" && (
                  <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={() => actPayout(p.id, "approve")} data-testid={`payout-approve-${p.id}`} style={{ padding: "7px 14px", borderRadius: 8, border: "1px solid #3aff9c66", background: "rgba(58,255,156,0.15)", color: "#3aff9c", cursor: "pointer", fontSize: 13 }}>Approve → Send BTC</button>
                    <button onClick={() => actPayout(p.id, "reject")} data-testid={`payout-reject-${p.id}`} style={{ padding: "7px 14px", borderRadius: 8, border: "1px solid #ff4d6d66", background: "rgba(255,77,109,0.15)", color: "#ff4d6d", cursor: "pointer", fontSize: 13 }}>Reject</button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {view === "aml" && (
        <div data-testid="compliance-aml-events" style={{ fontFamily: "monospace", fontSize: 12 }}>
          {amlEvents.length === 0 && <div style={{ padding: 20, color: "#a593c2", fontFamily: "sans-serif" }}>No AML events recorded yet.</div>}
          {amlEvents.map((e, i) => (
            <div key={i} style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)", color: "#cfc3e8" }}>
              <span style={{ color: "#888" }}>{(e.created_at || "").slice(0, 19)}</span>
              {" "}<span style={{ color: "#ffb44c" }}>{e.event_type}</span>
              {" "}user={e.user_id?.slice(-8)} ${e.amount_usd}
            </div>
          ))}
        </div>
      )}

      {view === "ofac" && (
        <div data-testid="compliance-ofac-hits">
          {ofacHits.length === 0 && <div style={{ padding: 20, color: "#a593c2" }}>No OFAC hits recorded. (This is good.)</div>}
          {ofacHits.map((h, i) => (
            <div key={i} style={{ padding: 12, marginBottom: 8, borderRadius: 8, background: "rgba(255,77,109,0.08)", border: "1px solid #ff4d6d44" }}>
              <div style={{ fontSize: 12, color: "#ff4d6d", fontWeight: 600 }}>SDN MATCH · {h.context}</div>
              <div style={{ fontSize: 11, color: "#888", fontFamily: "monospace", marginTop: 4 }}>{h.btc_address}</div>
              <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>user: {h.user_id?.slice(-8)} · {(h.created_at || "").slice(0, 19)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

