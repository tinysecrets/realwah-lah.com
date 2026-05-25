import { useState, useEffect, useCallback, createContext, useContext } from "react";
import "./NewApp.css";
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useSearchParams, Link } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { Eye, EyeOff, Gamepad2, CreditCard, Users, BarChart3, Settings, LogOut, History, Shield, Wallet, Copy, Check, ChevronRight, Sparkles, Star, Download, ArrowDownToLine, ArrowUpFromLine, RefreshCw, DollarSign, Menu, X, Clock, Activity, Wand2, Rocket, Gift } from "lucide-react";
import MasterControlHub from "./components/MasterControlHub";
import MasterControl from "./components/MasterControl";
import LandingPage from "./LandingPage";
import { ForgotPasswordPage, ResetPasswordPage, SettingsPage, AdminExtensions } from "./pages/Extensions";
import NerveCenter from "./pages/NerveCenter";
import BossMode from "./pages/BossMode";
import DepositCelebration from "./components/DepositCelebration";
import LaunchChecklist from "./components/LaunchChecklist";
import AdminGiftCards from "./components/AdminGiftCards";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

axios.defaults.withCredentials = true;

// Auth Context
const AuthContext = createContext(null);
const useAuth = () => useContext(AuthContext);

const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/auth/me`);
      setUser(data);
    } catch { setUser(false); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { checkAuth(); }, [checkAuth]);

  const login = async (email, password) => {
    const { data } = await axios.post(`${API}/auth/login`, { email, password });
    setUser(data);
    return data;
  };

  const register = async (email, password, name, ageVerified) => {
    const { data } = await axios.post(`${API}/auth/register`, { email, password, name, age_verified: ageVerified });
    setUser(data);
    return data;
  };

  const logout = async () => {
    await axios.post(`${API}/auth/logout`);
    setUser(false);
  };

  const refreshUser = async () => {
    try {
      const { data } = await axios.get(`${API}/auth/me`);
      setUser(data);
    } catch { setUser(false); }
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
};

const ProtectedRoute = ({ children, adminOnly = false }) => {
  const { user, loading } = useAuth();
  if (loading) return <LoadingScreen />;
  if (!user) return <Navigate to="/welcome" />;
  if (adminOnly && user.role !== "admin") return <Navigate to="/" />;
  return children;
};

// THE WAH-LAH GENIE — he RUNS the show. Not a sticker. He swirls, pops,
// leans, orbits, and zooms across the stage.
// Single character, 5 poses, all custom-generated for this site only.
// Floating corner mascots — DISABLED. User feedback: these read as
// "itty bitty sticker looking pictures just sitting on the site". The
// cohesive integrated genie now lives only in the landing hero and in
// one spot on the dashboard. Returning null keeps the JSX untouched.
const FloatingCharacters = () => null;

// Card-corner genie — DISABLED. Was rendering a tiny pasted genie sticker
// on every game card. Game cards now carry their own branded SVG art.
const CardGenie = () => null;

// Genie that orbits the WAH-LAH logo in the header — circles the title
// every few seconds, adding a bit of showmanship to the brand mark.
const HeaderGenieOrbit = () => (
  <img
    className="header-genie-orbit"
    src="/mascots/genie_small_peek.png"
    alt=""
    aria-hidden="true"
    onError={(e) => { e.target.style.display = "none"; }}
  />
);

// Animated Background — muted luxury shimmer (less candy, more sparkle)
const CandyBackground = () => (
  <div className="candy-bg">
    {[...Array(6)].map((_, i) => (
      <div key={i} className={`candy candy-${(i % 5) + 1}`} style={{
        left: `${Math.random() * 100}%`,
        animationDelay: `${Math.random() * 5}s`,
        animationDuration: `${15 + Math.random() * 10}s`,
        opacity: 0.25,
      }} />
    ))}
    {[...Array(35)].map((_, i) => (
      <div key={`sparkle-${i}`} className="sparkle" style={{
        left: `${Math.random() * 100}%`,
        top: `${Math.random() * 100}%`,
        animationDelay: `${Math.random() * 3}s`
      }} />
    ))}
  </div>
);

const LoadingScreen = () => (
  <div className="loading-screen">
    <CandyBackground />
    <div className="loader-container">
      <div className="sugar-loader"><Sparkles className="loader-icon" /></div>
      <p className="loader-text">Loading...</p>
    </div>
  </div>
);

// Login Page
const LoginPage = () => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [twoFACode, setTwoFACode] = useState("");
  const [showTwoFA, setShowTwoFA] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const { login, refreshUser } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      if (showTwoFA && twoFACode) {
        await axios.post(`${API}/ext/auth/login-2fa`, { email, password, code: twoFACode });
        await refreshUser();
      } else {
        await login(email, password);
      }
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Login failed");
    } finally { setIsLoading(false); }
  };

  return (
    <div className="auth-page">
      <CandyBackground />
      <div className="auth-mascot auth-mascot-left" aria-hidden="true">
        <img
          src="/mascots/genie_hero.png"
          alt=""
          onError={(e) => { e.target.parentElement.style.display = "none"; }}
        />
      </div>
      <div className="auth-wrapper">
        <div className="auth-brand">
          <div className="brand-icon"><Sparkles size={48} /></div>
          <h1 className="brand-title">WAH-LAH</h1>
          <h2 className="brand-subtitle">· INVITE ONLY ·</h2>
          <p className="brand-tagline">Where the win appears.</p>
        </div>
        
        <div className="auth-card">
          <div className="auth-card-header">
            <h2>Welcome Back!</h2>
            <p>Sign in to your account</p>
          </div>
          
          {error && <div className="error-alert">{error}</div>}
          
          <form onSubmit={handleSubmit}>
            <div className="input-group">
              <label>Email Address</label>
              <input data-testid="login-email" type="email" placeholder="player@email.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            
            <div className="input-group">
              <label>Password</label>
              <div className="password-input">
                <input data-testid="login-password" type={showPassword ? "text" : "password"} placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} required />
                <button type="button" className="password-toggle" onClick={() => setShowPassword(!showPassword)}>
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>
            
            <button data-testid="login-submit" type="submit" className="btn-primary" disabled={isLoading}>
              {isLoading ? <span className="btn-loader"></span> : "Sign In"}
            </button>

            {showTwoFA && (
              <div className="input-group" style={{ marginTop: 12 }}>
                <label>2FA Code</label>
                <input data-testid="login-2fa-code" type="text" placeholder="6-digit code" value={twoFACode} onChange={(e) => setTwoFACode(e.target.value)} />
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10, fontSize: 13 }}>
              <button type="button" onClick={() => setShowTwoFA((v) => !v)} data-testid="login-toggle-2fa" style={{ background: "none", border: "none", color: "#ffb44c", cursor: "pointer", padding: 0 }}>
                {showTwoFA ? "Hide 2FA" : "I use 2FA"}
              </button>
              <Link to="/forgot-password" data-testid="login-forgot-link" style={{ color: "#ffb44c" }}>Forgot password?</Link>
            </div>
          </form>
          
          <div className="auth-footer">
            <p>New player? <Link to="/register">Register Now</Link></p>
          </div>
        </div>
      </div>
    </div>
  );
};

// Register Page
const RegisterPage = () => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [ageVerified, setAgeVerified] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (!ageVerified) {
      setError("You must be 21+ years old to register");
      return;
    }
    if (!termsAccepted) {
      setError("You must accept the Terms and Conditions");
      return;
    }
    setError("");
    setIsLoading(true);
    try {
      // Name is not collected from user - backend derives it from email.
      const derivedName = email.split("@")[0];
      await register(email, password, derivedName, ageVerified);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Registration failed");
    } finally { setIsLoading(false); }
  };

  return (
    <div className="auth-page">
      <CandyBackground />
      <div className="auth-mascot auth-mascot-right" aria-hidden="true">
        <img
          src="/mascots/genie_hero.png"
          alt=""
          onError={(e) => { e.target.parentElement.style.display = "none"; }}
        />
      </div>
      <div className="auth-wrapper">
        <div className="auth-brand">
          <div className="brand-icon"><Sparkles size={48} /></div>
          <h1 className="brand-title">WAH-LAH</h1>
          <h2 className="brand-subtitle">· CLAIM YOUR SEAT ·</h2>
          <p className="brand-tagline">The house doesn't win here.</p>
        </div>
        
        <div className="auth-card">
          <div className="auth-card-header">
            <h2>Create Account</h2>
            <p>Join the sweetest games</p>
          </div>
          
          {error && <div className="error-alert">{error}</div>}
          
          <form onSubmit={handleSubmit}>
            <div className="input-group">
              <label>Email Address</label>
              <input data-testid="register-email" type="email" placeholder="player@email.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            
            <div className="input-group">
              <label>Password</label>
              <div className="password-input">
                <input data-testid="register-password" type={showPassword ? "text" : "password"} placeholder="Min 6 characters" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} />
                <button type="button" className="password-toggle" onClick={() => setShowPassword(!showPassword)}>
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <div className="input-group">
              <label>Confirm Password</label>
              <input data-testid="register-confirm-password" type={showPassword ? "text" : "password"} placeholder="Confirm password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required />
            </div>
            
            <div className="checkbox-group">
              <label className="checkbox-label">
                <input data-testid="register-terms" type="checkbox" checked={termsAccepted} onChange={(e) => setTermsAccepted(e.target.checked)} />
                <span className="checkbox-custom"></span>
                <span>I accept the <a href="#" onClick={(e) => e.preventDefault()}>Terms & Conditions</a></span>
              </label>
              
              <label className="checkbox-label">
                <input data-testid="register-age-verify" type="checkbox" checked={ageVerified} onChange={(e) => setAgeVerified(e.target.checked)} />
                <span className="checkbox-custom"></span>
                <span><Shield size={14} /> I am <strong>21+ years old</strong></span>
              </label>
            </div>
            
            <button data-testid="register-submit" type="submit" className="btn-primary" disabled={isLoading}>
              {isLoading ? <span className="btn-loader"></span> : "Register Now"}
            </button>
          </form>
          
          <div className="auth-footer">
            <p>Already have an account? <Link to="/login">Sign In</Link></p>
          </div>
        </div>
      </div>
    </div>
  );
};

// Main Dashboard with Tabs
const Dashboard = () => {
  const { user, logout, refreshUser } = useAuth();
  const [activeTab, setActiveTab] = useState("games");
  const [games, setGames] = useState([]);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [showBalanceInfo, setShowBalanceInfo] = useState(false);
  const [showOtherMethods, setShowOtherMethods] = useState(false);
  const [flags, setFlags] = useState({
    btc_payouts_enabled: false,
    giftcard_redemption_enabled: true,
    redeem_tab_visible: true,
    withdraw_tab_visible: false,
  });
  const navigate = useNavigate();

  // Fetch feature flags on mount + when admin changes them (re-fetched on tab change for simplicity)
  useEffect(() => {
    axios.get(`${API}/ext/compliance/feature-flags`)
      .then(r => setFlags(r.data))
      .catch(() => {});
  }, [activeTab]);
  
  // AMOE Daily Claim State
  const [amoeEligible, setAmoeEligible] = useState(false);
  const [hoursRemaining, setHoursRemaining] = useState(0);
  const [claimingAmoe, setClaimingAmoe] = useState(false);

  const fetchGames = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/games`);
      setGames(data);
    } catch { toast.error("Failed to load games"); }
  }, []);
  
  const checkAmoeStatus = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/amoe/status`);
      setAmoeEligible(data.eligible);
      setHoursRemaining(data.hours_remaining || 0);
    } catch {
      // AMOE status check failed silently
    }
  }, []);

  const loadVipTier = useCallback(async () => {
    try {
      await axios.get(`${API}/ext/vip/tier`);
      await refreshUser();
    } catch {
      // VIP tier load failed silently
    }
  }, [refreshUser]);

  useEffect(() => { fetchGames(); checkAmoeStatus(); loadVipTier(); }, [fetchGames, checkAmoeStatus, loadVipTier]);
  
  const handleDailyClaim = async () => {
    if (!amoeEligible || claimingAmoe) return;
    
    setClaimingAmoe(true);
    try {
      const { data } = await axios.post(`${API}/amoe/claim-daily`);
      toast.success(data.message);
      await refreshUser(); // Update balance
      await checkAmoeStatus(); // Update claim status
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Claim failed');
    } finally {
      setClaimingAmoe(false);
    }
  };

  const tabs = [
    { id: "games", label: "Play & Deposit", icon: <Gamepad2 size={20} /> },
    ...(flags.redeem_tab_visible ? [{ id: "redeem", label: "Redeem", icon: <RefreshCw size={20} /> }] : []),
    ...(flags.withdraw_tab_visible ? [{ id: "withdraw", label: "Withdraw", icon: <ArrowUpFromLine size={20} /> }] : []),
    { id: "transactions", label: "Ledger", icon: <History size={20} /> },
    { id: "settings", label: "Settings", icon: <Settings size={20} /> },
    { id: "support", label: "Concierge", icon: <Shield size={20} /> },
  ];

  return (
    <div className="dashboard">
      <CandyBackground />
      <FloatingCharacters />
      <div className="dashboard-mascot" aria-hidden="true">
        <img
          src="/mascots/genie_hero.png"
          alt=""
          onError={(e) => {
            e.target.parentElement.style.display = "none";
          }}
        />
      </div>
      
      {/* Header */}
      <header className="dashboard-header">
        <div className="header-left">
          <Sparkles className="header-logo" />
          <div className="header-title">
            <h1>WAH-LAH</h1>
            <span>Members' Floor</span>
          </div>
          <HeaderGenieOrbit />
        </div>
        
        <div className="header-right">
          {/* Dual Currency Balance Display — compact pill */}
          <button
            type="button"
            data-testid="balance-pill-toggle"
            className="balance-pill"
            onClick={() => setShowBalanceInfo((v) => !v)}
            title="Tap to learn how Tokens and Credits work"
          >
            <span className="bp-seg bp-tokens">
              <span className="bp-icon">🎩</span>
              <span className="bp-amount">{user?.sugar_tokens?.toLocaleString() || "0"}</span>
              <span className="bp-label">Tokens</span>
            </span>
            <span className="bp-divider" />
            <span className="bp-seg bp-credits">
              <span className="bp-icon">🎮</span>
              <span className="bp-amount">{user?.game_credits?.toLocaleString() || "0"}</span>
              <span className="bp-label">Credits</span>
            </span>
            <span className="bp-info">ⓘ</span>
          </button>
          
          <div className="user-menu">
            <span className="user-name">{user?.name}</span>
            {user?.vip_tier && (
              <span data-testid="vip-badge" title={`VIP ${user.vip_tier}`} style={{ padding: "2px 8px", borderRadius: 999, background: "rgba(255,180,60,0.15)", border: "1px solid rgba(255,180,60,0.5)", fontSize: 11, color: "#ffb44c", marginLeft: 6 }}>
                <Sparkles size={10} style={{ verticalAlign: "middle" }} /> {user.vip_tier}
              </span>
            )}
            <button data-testid="nav-settings-btn" className="btn-icon" onClick={() => navigate("/settings")} title="Settings">
              <Settings size={20} />
            </button>
            {user?.role === "admin" && (
              <>
                <button data-testid="nav-boss-mode-btn" className="btn-icon boss-mode-nav" onClick={() => navigate("/boss")} title="Boss Mode — summon the Genie">
                  <Wand2 size={20} />
                </button>
                <button data-testid="nav-nerve-center-btn" className="btn-icon" onClick={() => navigate("/admin/nerve-center")} title="Nerve Center" style={{ color: "#3aff9c" }}>
                  <Activity size={20} />
                </button>
                <button className="btn-icon" onClick={() => navigate("/admin")} title="Admin">
                  <Shield size={20} />
                </button>
                <button data-testid="nav-admin-ext-btn" className="btn-icon" onClick={() => navigate("/admin/extensions")} title="Admin Extensions">
                  <BarChart3 size={20} />
                </button>
              </>
            )}
            <button className="btn-icon btn-logout" onClick={logout} title="Logout">
              <LogOut size={20} />
            </button>
          </div>
          
          <button className="mobile-menu-btn" onClick={() => setMobileMenuOpen(!mobileMenuOpen)}>
            {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>

        {showBalanceInfo && (
          <div className="balance-info-panel" data-testid="balance-info-panel">
            <button
              type="button"
              className="bip-close"
              onClick={() => setShowBalanceInfo(false)}
              aria-label="Close"
              data-testid="balance-info-close"
            >×</button>
            <div className="bip-row">
              <div className="bip-tag tokens">🎩 Tokens</div>
              <div className="bip-text">
                <strong>What you buy.</strong> $1 = 100 Tokens. Used to play games.
                Tokens are the "paid product" — they CANNOT be cashed out.
              </div>
            </div>
            <div className="bip-row">
              <div className="bip-tag credits">🎮 Game Credits</div>
              <div className="bip-text">
                <strong>What you redeem.</strong> You receive Credits free as a 100% bonus
                on every Token purchase AND as a free-daily reward (100 credits / 24h).
                ONLY Credits can be redeemed for BTC. This is the sweepstakes leg — it keeps
                us legal under US sweepstakes law.
              </div>
            </div>
            <div className="bip-row">
              <div className="bip-tag amoe">🎁 Free daily (AMOE)</div>
              <div className="bip-text">
                No purchase necessary. Claim 100 free Credits every 24 hours from the dashboard.
              </div>
            </div>
          </div>
        )}
      </header>

      {/* Tab Navigation */}
      <nav className={`tab-nav ${mobileMenuOpen ? "open" : ""}`}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            data-testid={`tab-${tab.id}`}
            className={`tab-btn ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => { setActiveTab(tab.id); setMobileMenuOpen(false); }}
          >
            {tab.icon}
            <span>{tab.label}</span>
          </button>
        ))}
      </nav>

      {/* Content */}
      <main className="dashboard-content">
        {activeTab === "games" && (
          <div>
            {/* AMOE Daily Claim Banner */}
            <div className="amoe-banner">
              <div className="amoe-info">
                <h3>Complimentary Daily Chips <span style={{ fontStyle: "italic", fontWeight: 400, opacity: 0.75, fontSize: 12 }}>· no purchase necessary</span></h3>
                <p>100 credits every 24 hours — house compliments, per state law.</p>
              </div>
              <button 
                onClick={handleDailyClaim}
                disabled={!amoeEligible || claimingAmoe}
                className={`amoe-claim-btn ${amoeEligible ? 'eligible' : 'cooldown'}`}
              >
                {claimingAmoe ? (
                  <>
                    <RefreshCw size={20} className="spinning" />
                    Claiming...
                  </>
                ) : amoeEligible ? (
                  <>
                    <Download size={20} />
                    Claim 100 Credits
                  </>
                ) : (
                  <>
                    <Clock size={20} />
                    Return in {hoursRemaining}h
                  </>
                )}
              </button>
            </div>
            <GamesTab games={games} onSuccess={refreshUser} />
            <div className="other-methods-strip">
              <button
                type="button"
                data-testid="open-other-methods"
                onClick={() => setShowOtherMethods(true)}
                className="other-methods-btn"
              >
                <span className="om-ornament">❦</span>
                Crypto · Cash Cards · Other Methods
                <span className="om-ornament">❦</span>
              </button>
            </div>
          </div>
        )}
        {activeTab === "redeem" && <RedeemTab games={games} />}
        {activeTab === "withdraw" && <WithdrawTab games={games} user={user} onSuccess={refreshUser} />}
        {activeTab === "transactions" && <TransactionsTab />}
        {activeTab === "settings" && <SettingsTab user={user} onSuccess={refreshUser} />}
        {activeTab === "support" && <SupportTab user={user} />}

        {showOtherMethods && (
          <div
            className="wl-drawer-overlay"
            data-testid="other-methods-drawer"
            onClick={(e) => { if (e.target === e.currentTarget) setShowOtherMethods(false); }}
          >
            <div className="wl-drawer">
              <div className="wl-drawer-header">
                <span className="wl-ornament-bar" />
                <h2>Alternative Tender</h2>
                <span className="wl-ornament-bar" />
                <button
                  className="wl-drawer-close"
                  onClick={() => setShowOtherMethods(false)}
                  data-testid="close-other-methods"
                  aria-label="Close"
                >×</button>
              </div>
              <DepositTab games={games} onSuccess={() => { refreshUser(); setShowOtherMethods(false); }} />
            </div>
          </div>
        )}
      </main>
      
      {/* Footer */}
      <footer className="dashboard-footer">
        <p>&copy; 2026 WAH-LAH · Est. 2026 · 21+ Members · Void where prohibited</p>
        <div className="footer-links">
          <a href="/api/legal/terms" target="_blank" rel="noopener noreferrer">Terms of Service</a>
          <span>•</span>
          <a href="/api/legal/privacy" target="_blank" rel="noopener noreferrer">Privacy Policy</a>
          <span>•</span>
          <a href="/api/legal/responsible-gaming" target="_blank" rel="noopener noreferrer">Responsible Gaming</a>
        </div>
      </footer>
    </div>
  );
};

// Play & Deposit Tab — merged Games + Deposit experience
const GamesTab = ({ games, onSuccess }) => {
  const { user } = useAuth();
  const [copiedField, setCopiedField] = useState("");
  const [amounts, setAmounts] = useState({});
  const [loadingGame, setLoadingGame] = useState("");
  const [platformAccounts, setPlatformAccounts] = useState({});
  const [celebrate, setCelebrate] = useState(false);

  const copyText = (text, field) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(""), 2000);
    toast.success("Copied!");
  };

  const fetchPlatformAccounts = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/ext/platform/accounts`);
      setPlatformAccounts(data || {});
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { fetchPlatformAccounts(); }, [fetchPlatformAccounts]);

  const amountFor = (gameId) => amounts[gameId] ?? 10;

  const setAmount = (gameId, value) => {
    setAmounts((prev) => ({ ...prev, [gameId]: value }));
  };

  const step = (gameId, delta) => {
    const cur = Number(amountFor(gameId) || 0);
    const next = Math.max(1, cur + delta);
    setAmount(gameId, next);
  };

  const handleDeposit = async (gameId) => {
    const amt = Number(amountFor(gameId));
    if (!amt || amt < 1) return toast.error("Minimum deposit is $1");
    setLoadingGame(gameId);
    // Fire the celebration immediately — user feels the win before the redirect
    setCelebrate(true);
    try {
      // JIT registration first
      try {
        await axios.post(`${API}/ext/platform/register`, { game_id: gameId });
        fetchPlatformAccounts();
      } catch (regErr) {
        setCelebrate(false);
        toast.error(regErr.response?.data?.detail || "Deposit held: registration failed");
        setLoadingGame("");
        return;
      }
      const { data } = await axios.post(`${API}/checkout/create`, {
        amount: amt,
        game_id: gameId,
        account_name: "deposit",
        origin_url: window.location.origin,
        payment_method: "stripe",
      });
      // Hold the celebration for ~1.4s so the user actually sees it before redirect
      setTimeout(() => { window.location.href = data.url; }, 1400);
    } catch (err) {
      setCelebrate(false);
      toast.error(err.response?.data?.detail || "Failed to create checkout");
    } finally {
      setLoadingGame("");
    }
  };

  // VIP tier bonus percentage (for badge display)
  const bonusPct = (() => {
    const tier = (user?.vip_tier || "Bronze").toLowerCase();
    return { bronze: 0, silver: 5, gold: 10, platinum: 15, diamond: 25 }[tier] ?? 0;
  })();

  return (
    <div className="tab-content games-tab">
      <div className="section-header">
        <h2>Play &amp; Deposit</h2>
        <p>Pick a game, set your amount, deposit, then sign in with the credentials shown to play.</p>
      </div>

      {celebrate && <DepositCelebration onDone={() => setCelebrate(false)} />}

      <div className="games-grid">
        {games.map((game) => {
          const regState = platformAccounts?.[game.id];
          const registered = regState?.status === "registered";
          const amt = amountFor(game.id);
          const isLoading = loadingGame === game.id;
          return (
            <div
              key={game.id}
              className="play-deposit-card"
              data-accent={game.accent_color}
              data-testid={`game-card-${game.id}`}
            >
              <CardGenie pose={game.id?.charCodeAt(0) % 2 === 0 ? "lamp" : "peek"} />
              {bonusPct > 0 && (
                <div className="bonus-badge" data-testid={`bonus-badge-${game.id}`}>
                  +{bonusPct}% VIP BONUS
                </div>
              )}

              <div className="pd-header">
                <div className="game-logo" style={{
                  background: `linear-gradient(135deg, ${game.accent_color || "#ff1493"} 0%, #9b59b6 100%)`,
                }}>
                  <img
                    src={game.logo_url}
                    alt={game.name}
                    onError={(e) => {
                      // Hide broken image; CSS ::before shows gamepad icon
                      e.target.style.display = "none";
                      e.target.parentElement.classList.add("logo-fallback");
                    }}
                  />
                  <Gamepad2 className="logo-fallback-icon" size={36} strokeWidth={1.8} />
                </div>
                <div className="pd-title">
                  <h3>{game.name}</h3>
                  <span
                    className={`pd-status ${registered ? "is-ok" : "is-pending"}`}
                    data-testid={`platform-status-${game.id}`}
                  >
                    {registered ? "✓ Registered" : "Auto-register on deposit"}
                  </span>
                </div>
              </div>

              <div className="pd-amount-row">
                <button
                  type="button"
                  className="pd-step"
                  onClick={() => step(game.id, -5)}
                  data-testid={`amount-minus-${game.id}`}
                  aria-label="Decrease amount"
                >–</button>
                <div className="pd-amount">
                  <span className="pd-currency">$</span>
                  <input
                    type="number"
                    min="1"
                    value={amt}
                    onChange={(e) => setAmount(game.id, e.target.value)}
                    data-testid={`amount-input-${game.id}`}
                  />
                </div>
                <button
                  type="button"
                  className="pd-step"
                  onClick={() => step(game.id, +5)}
                  data-testid={`amount-plus-${game.id}`}
                  aria-label="Increase amount"
                >+</button>
              </div>

              <div className="pd-actions">
                <a
                  href={game.game_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="pd-btn pd-play"
                  data-testid={`play-${game.id}`}
                >
                  <Gamepad2 size={16} />
                  <span>PLAY GAME</span>
                </a>
                <button
                  type="button"
                  className="pd-btn pd-deposit"
                  onClick={() => handleDeposit(game.id)}
                  disabled={isLoading}
                  data-testid={`deposit-${game.id}`}
                >
                  {isLoading ? (
                    <><RefreshCw size={16} className="spin" /><span>Processing…</span></>
                  ) : (
                    <><DollarSign size={16} /><span>Deposit</span></>
                  )}
                </button>
              </div>

              {user?.game_username && (
                <div
                  className="pd-credentials"
                  data-testid={`game-credentials-${game.id}`}
                >
                  <div className="pd-cred-row">
                    <label>User</label>
                    <span
                      className="pd-cred-value"
                      data-testid={`game-user-${game.id}`}
                    >{user.game_username}</span>
                    <button
                      type="button"
                      onClick={() => copyText(user.game_username, `user-${game.id}`)}
                      data-testid={`copy-user-${game.id}`}
                      className="pd-copy"
                      aria-label="Copy username"
                    >
                      {copiedField === `user-${game.id}` ? <Check size={12} /> : <Copy size={12} />}
                    </button>
                  </div>
                  <div className="pd-cred-row">
                    <label>Password</label>
                    <span
                      className="pd-cred-value"
                      data-testid={`game-pass-${game.id}`}
                    >{user.game_password}</span>
                    <button
                      type="button"
                      onClick={() => copyText(user.game_password, `pass-${game.id}`)}
                      data-testid={`copy-pass-${game.id}`}
                      className="pd-copy"
                      aria-label="Copy password"
                    >
                      {copiedField === `pass-${game.id}` ? <Check size={12} /> : <Copy size={12} />}
                    </button>
                  </div>
                  {registered && regState?.platform_uid && regState.platform_uid !== user.game_username && (
                    <div className="pd-platform-uid">
                      Platform ID: <code>{regState.platform_uid}</code>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// Deposit Tab
const DepositTab = ({ games, onSuccess }) => {
  const [selectedGame, setSelectedGame] = useState("");
  const [amount, setAmount] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("stripe");
  const [cryptoInfo, setCryptoInfo] = useState(null);
  const [cardInfo, setCardInfo] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copiedLightning, setCopiedLightning] = useState(false);

  const suggestions = [10, 20, 50, 100, 200, 500];

  const fetchPaymentInfo = useCallback(async () => {
    try {
      const [crypto, card] = await Promise.all([
        axios.get(`${API}/payment/crypto-info`),
        axios.get(`${API}/payment/card-info`)
      ]);
      setCryptoInfo(crypto.data);
      setCardInfo(card.data);
    } catch {
      // Payment info fetch failed silently
    }
  }, []);

  useEffect(() => {
    fetchPaymentInfo();
    if (games.length > 0 && !selectedGame) setSelectedGame(games[0].id);
  }, [games, selectedGame, fetchPaymentInfo]);

  const handleStripePayment = async () => {
    if (!selectedGame) {
      toast.error("Please select a game");
      return;
    }
    if (!amount || parseFloat(amount) < 1) {
      toast.error("Minimum deposit is $1");
      return;
    }
    setIsLoading(true);
    try {
      // JIT platform registration gate — ensures the user is registered on
      // the selected game platform BEFORE money moves. Deposit is held on error.
      try {
        await axios.post(`${API}/ext/platform/register`, { game_id: selectedGame });
      } catch (regErr) {
        toast.error(regErr.response?.data?.detail || "Deposit held: platform registration failed");
        setIsLoading(false);
        return;
      }
      const { data } = await axios.post(`${API}/checkout/create`, {
        amount: parseFloat(amount),
        game_id: selectedGame,
        account_name: "deposit",
        origin_url: window.location.origin,
        payment_method: "stripe"
      });
      window.location.href = data.url;
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to create checkout");
    } finally { setIsLoading(false); }
  };

  const copyToClipboard = (text, isLightning = false) => {
    navigator.clipboard.writeText(text);
    if (isLightning) {
      setCopiedLightning(true);
      setTimeout(() => setCopiedLightning(false), 2000);
    } else {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
    toast.success("Copied!");
  };

  return (
    <div className="tab-content deposit-tab">
      <div className="section-header">
        <h2>Deposit Funds</h2>
        <p className="sweeps-notice">
          🎩 Purchase <strong>Tokens</strong> + Get <strong>100% Bonus Game Credits</strong> free! • Example: $10 = 1,000 tokens + 1,000 bonus credits
        </p>
      </div>

      <div className="deposit-form">
        <div className="form-section">
          <label>Select Game</label>
          <select value={selectedGame} onChange={(e) => setSelectedGame(e.target.value)} className="game-select">
            {games.map((game) => (
              <option key={game.id} value={game.id}>{game.name}</option>
            ))}
          </select>
        </div>

        <div className="form-section">
          <label>Enter Amount</label>
          <div className="amount-input-box">
            <span className="currency">$</span>
            <input
              data-testid="deposit-amount"
              type="number"
              min="1"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="Enter amount"
            />
          </div>
          <div className="quick-amounts">
            {suggestions.map((val) => (
              <button key={val} className={`quick-btn ${parseFloat(amount) === val ? "selected" : ""}`} onClick={() => setAmount(val.toString())}>
                ${val}
              </button>
            ))}
          </div>
        </div>

        <div className="form-section">
          <label>Payment Method</label>
          <div className="payment-methods">
            {[
              { id: "stripe", label: "Card", icon: <CreditCard size={20} /> },
              { id: "crypto", label: "Crypto", icon: <span className="btc-icon">₿</span> },
              { id: "cards", label: "Cash Cards", icon: <DollarSign size={20} /> }
            ].map((method) => (
              <button
                key={method.id}
                data-testid={`method-${method.id}`}
                className={`method-btn ${paymentMethod === method.id ? "active" : ""}`}
                onClick={() => setPaymentMethod(method.id)}
              >
                {method.icon}
                <span>{method.label}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="payment-details">
          {paymentMethod === "stripe" && (
            <div className="payment-box">
              <p>Secure checkout powered by Stripe</p>
              <button className="btn-primary btn-pay" onClick={handleStripePayment} disabled={isLoading || !amount}>
                {isLoading ? <span className="btn-loader"></span> : `Pay $${amount || "0"}`}
              </button>
            </div>
          )}

          {paymentMethod === "crypto" && cryptoInfo && (
            <div className="payment-box crypto-box">
              <h3 style={{fontSize: '18px', marginBottom: '20px', color: 'var(--neon-cyan)'}}>Bitcoin (BTC)</h3>
              <div className="qr-code">
                <img src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${cryptoInfo.btc_address}`} alt="BTC QR" />
              </div>
              <div className="wallet-address">
                <span style={{fontSize: '10px'}}>{cryptoInfo.btc_address}</span>
                <button className="copy-btn" onClick={() => copyToClipboard(cryptoInfo.btc_address, false)}>
                  {copied ? <Check size={16} /> : <Copy size={16} />}
                </button>
              </div>
              
              <h3 style={{fontSize: '18px', margin: '30px 0 20px', color: 'var(--neon-gold)'}}>Lightning Network ⚡</h3>
              <div className="wallet-address">
                <span style={{fontSize: '9px', wordBreak: 'break-all'}}>{cryptoInfo.lightning_address}</span>
                <button className="copy-btn" onClick={() => copyToClipboard(cryptoInfo.lightning_address, true)}>
                  {copiedLightning ? <Check size={16} /> : <Copy size={16} />}
                </button>
              </div>
              
              <p className="note" style={{marginTop: '25px'}}>Send ${amount || "0"} worth of BTC via either method</p>
              <p className="note">Contact support with TX ID after payment</p>
            </div>
          )}

          {paymentMethod === "cards" && cardInfo && (
            <div className="payment-box manual-box">
              <div className="pay-tag">{cardInfo.tag}</div>
              <button className="copy-btn-full" onClick={() => copyToClipboard(cardInfo.tag)}>
                <Copy size={16} /> Copy Tag
              </button>
              <p className="note">Send ${amount || "0"} via Cash App or Chime to the tag above</p>
              <p className="note">Include your email in the note/memo</p>
              <p className="note">Contact support after payment for credit activation</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// Redeem Tab - matches Withdraw layout
const RedeemTab = ({ games }) => {
  const { user, refreshUser } = useAuth();
  const [selectedGame, setSelectedGame] = useState("");
  const [amount, setAmount] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [payoutType, setPayoutType] = useState("btc"); // btc | giftcard
  const [giftCardBrand, setGiftCardBrand] = useState("amazon");
  const [giftCardEmail, setGiftCardEmail] = useState("");
  const [btcAddress, setBtcAddress] = useState("");
  const [successInfo, setSuccessInfo] = useState(null);  // { type, brand?, amount, email? }

  useEffect(() => {
    if (games.length > 0 && !selectedGame) setSelectedGame(games[0].id);
  }, [games, selectedGame]);

  const handleRedeem = async () => {
    if (!amount || parseFloat(amount) <= 0) {
      toast.error("Please enter a valid amount");
      return;
    }
    if (parseFloat(amount) > (user?.game_credits || 0)) {
      toast.error("Insufficient game credits");
      return;
    }
    setIsLoading(true);
    try {
      if (payoutType === "btc") {
        if (!btcAddress || btcAddress.length < 20) {
          toast.error("Enter a valid Bitcoin address");
          setIsLoading(false); return;
        }
        await axios.post(`${API}/redemption/request`, {
          game_credits: parseFloat(amount),
          btc_address: btcAddress,
          game_id: selectedGame,
        });
        toast.success("✨ Bitcoin redemption requested! Held for admin approval.");
        setSuccessInfo({ type: "btc", amount: parseFloat(amount) });
      } else {
        // Real gift card request — hits the admin queue, debits credits atomically.
        const email = (giftCardEmail || user?.email || "").trim();
        if (!email || !email.includes("@")) {
          toast.error("Enter a valid recipient email");
          setIsLoading(false); return;
        }
        await axios.post(`${API}/giftcard/request`, {
          brand: giftCardBrand,
          amount_credits: parseInt(amount, 10),
          recipient_email: email,
          game_id: selectedGame,
        });
        toast.success(`✨ ${giftCardBrand.toUpperCase()} gift card reserved! Code will hit ${email} within 24h.`);
        setSuccessInfo({ type: "giftcard", brand: giftCardBrand, amount: parseInt(amount, 10), email });
      }
      setAmount("");
      setBtcAddress("");
      if (refreshUser) refreshUser();
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 402 && detail?.required_tier) {
        toast.error(detail.message || "KYC required");
      } else if (err.response?.status === 451) {
        toast.error(detail || "Blocked by compliance");
      } else if (err.response?.status === 503) {
        toast.error("Bitcoin payouts are temporarily off — pick a gift card instead");
        setPayoutType("giftcard");
      } else {
        toast.error(detail || "Redemption failed. Please contact support.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const giftCards = [
    { id: "amazon",   label: "Amazon",    icon: "🛒" },
    { id: "visa",     label: "Visa",      icon: "💳" },
    { id: "xbox",     label: "Xbox",      icon: "🎮" },
    { id: "roblox",   label: "Roblox",    icon: "🎲" },
    { id: "doordash", label: "DoorDash",  icon: "🍔" },
    { id: "spotify",  label: "Spotify",   icon: "🎧" },
  ];

  return (
    <div className="tab-content withdraw-tab" data-testid="redeem-tab">
      <div className="section-header">
        <h2>Collect Your Winnings</h2>
        <p>Choose how you want your prize delivered</p>
      </div>

      <div className="withdraw-container">
        <div className="withdraw-form">
          {/* Payout type selector */}
          <div className="form-section">
            <label>Payout Method</label>
            <div className="payout-selector">
              <div
                className={`payout-tile ${payoutType === "btc" ? "active" : ""}`}
                onClick={() => setPayoutType("btc")}
                data-testid="payout-tile-btc"
              >
                <span className="pt-icon">₿</span>
                <span className="pt-label">Bitcoin</span>
              </div>
              <div
                className={`payout-tile ${payoutType === "giftcard" ? "active" : ""}`}
                onClick={() => setPayoutType("giftcard")}
                data-testid="payout-tile-giftcard"
              >
                <span className="pt-icon">🎁</span>
                <span className="pt-label">Gift Card</span>
              </div>
            </div>
          </div>

          {/* Gift card brand picker */}
          {payoutType === "giftcard" && (
            <>
              <div className="form-section">
                <label>Gift Card Brand</label>
                <div className="payout-selector" data-testid="giftcard-brand-picker">
                  {giftCards.map(g => (
                    <div
                      key={g.id}
                      className={`payout-tile ${giftCardBrand === g.id ? "active" : ""}`}
                      onClick={() => setGiftCardBrand(g.id)}
                      data-testid={`giftcard-${g.id}`}
                    >
                      <span className="pt-icon">{g.icon}</span>
                      <span className="pt-label">{g.label}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="form-section">
                <label>Recipient Email</label>
                <input
                  type="email"
                  placeholder={user?.email || "you@example.com"}
                  value={giftCardEmail}
                  onChange={(e) => setGiftCardEmail(e.target.value)}
                  data-testid="giftcard-email-input"
                />
                <small>Code will be emailed here once an admin fulfills the request.</small>
              </div>
            </>
          )}

          {/* BTC address input */}
          {payoutType === "btc" && (
            <div className="form-section">
              <label>Your Bitcoin Address</label>
              <input
                type="text"
                placeholder="bc1q..."
                value={btcAddress}
                onChange={(e) => setBtcAddress(e.target.value)}
                data-testid="btc-address-input"
              />
            </div>
          )}

          {/* Game platform dropdown — only relevant for BTC (credits source) */}
          {payoutType === "btc" && (
            <div className="form-section">
              <label>Select Game Platform</label>
              <select data-testid="redeem-game-select" value={selectedGame} onChange={(e) => setSelectedGame(e.target.value)}>
                {games.map((game) => <option key={game.id} value={game.id}>{game.name}</option>)}
              </select>
            </div>
          )}

          <div className="form-section">
            <label>Credits to Redeem</label>
            <div className="input-with-icon">
              <DollarSign size={20} />
              <input
                data-testid="redeem-amount"
                type="number"
                min="1"
                step="0.01"
                placeholder="Enter credit amount"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>
            <small>Available Game Credits: {user?.game_credits?.toLocaleString() || "0"}</small>
          </div>

          {payoutType === "btc" ? (
            <div className="withdraw-info">
              <p>How Bitcoin Redemption Works:</p>
              <ul>
                <li><span>Step 1:</span> <span>Enter your Bitcoin address and amount</span></li>
                <li><span>Step 2:</span> <span>Request is held for admin review (compliance checks)</span></li>
                <li><span>Step 3:</span> <span style={{color: '#10B981'}}>BTC sent to your wallet after approval</span></li>
              </ul>
            </div>
          ) : (
            <div className="withdraw-info">
              <p>How Gift Card Redemption Works:</p>
              <ul>
                <li><span>Step 1:</span> <span>Pick your brand and amount ($5–$500 per card)</span></li>
                <li><span>Step 2:</span> <span>We hold the request for admin review (usually under 24h)</span></li>
                <li><span>Step 3:</span> <span style={{color: '#10B981'}}>Gift card code emailed to <strong>{giftCardEmail || user?.email}</strong></span></li>
              </ul>
              <p style={{fontSize: '13px', marginTop: '12px', color: '#94A3B8'}}>
                Safer than crypto, no wallet needed. Your credits are refunded if the request is rejected.
              </p>
            </div>
          )}

          <button data-testid="redeem-submit" className="btn-primary btn-withdraw" disabled={isLoading} onClick={handleRedeem}>
            {isLoading ? <span className="btn-loader"></span> : `Redeem ${amount || "0"} Credits`}
          </button>

          {successInfo && (
            <div className="redeem-success" data-testid="redeem-success">
              <div className="rs-icon">
                <Sparkles size={22} />
              </div>
              <div className="rs-text">
                <strong>Request reserved ✨</strong>
                {successInfo.type === "giftcard" ? (
                  <span>${successInfo.amount} {successInfo.brand.toUpperCase()} card queued — code will be emailed to {successInfo.email} within 24h.</span>
                ) : (
                  <span>${successInfo.amount} BTC redemption held for compliance review. You'll be notified.</span>
                )}
              </div>
              <button
                className="rs-dismiss"
                onClick={() => setSuccessInfo(null)}
                data-testid="redeem-success-dismiss"
                aria-label="Dismiss"
              >
                <X size={16} />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// Withdraw Tab - Bitcoin Withdrawal
const WithdrawTab = ({ games, user, onSuccess }) => {
  const [selectedGame, setSelectedGame] = useState("");
  const [amount, setAmount] = useState("");
  const [btcAddress, setBtcAddress] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [kycRequired, setKycRequired] = useState(null);  // {tier, message}
  const [kycMethod, setKycMethod] = useState(null);       // 'persona' | 'manual_upload'
  const [personaUrl, setPersonaUrl] = useState("");
  const [kycFile, setKycFile] = useState(null);
  const [kycDocType, setKycDocType] = useState("id_front");

  useEffect(() => {
    if (games && games.length > 0 && !selectedGame) setSelectedGame(games[0].id);
  }, [games, selectedGame, setSelectedGame]);

  const initiateKyc = async (tier) => {
    try {
      const r = await axios.post(`${API}/ext/compliance/kyc/initiate`, { tier });
      setKycMethod(r.data.method);
      if (r.data.method === "persona" && r.data.hosted_inquiry_url) {
        setPersonaUrl(r.data.hosted_inquiry_url);
      }
      toast.info(r.data.message || "KYC started — complete the verification to continue.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "KYC initiation failed");
    }
  };

  const uploadKycDoc = async () => {
    if (!kycFile || !kycRequired) return;
    const fd = new FormData();
    fd.append("tier", kycRequired.tier);
    fd.append("doc_type", kycDocType);
    fd.append("file", kycFile);
    try {
      await axios.post(`${API}/ext/compliance/kyc/upload`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Document uploaded. Admin will review within 24 hours.");
      setKycFile(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    }
  };

  const handleWithdraw = async (e) => {
    e.preventDefault();
    
    if (!btcAddress || !amount || parseFloat(amount) <= 0) {
      toast.error("Please fill all fields with valid amounts");
      return;
    }

    if (parseFloat(amount) > (user?.credits || 0)) {
      toast.error("Insufficient credits");
      return;
    }

    setIsLoading(true);
    try {
      await axios.post(`${API}/withdraw/request`, {
        game_id: selectedGame,
        amount_usd: parseFloat(amount),
        btc_address: btcAddress
      });
      
      toast.success(parseFloat(amount) >= 500 
        ? "Withdrawal submitted! Large amounts require admin approval (1-24 hrs)."
        : "Withdrawal processing! Bitcoin will be sent shortly."
      );
      
      setAmount("");
      setBtcAddress("");
      if (onSuccess) onSuccess();
    } catch (err) {
      const detail = err.response?.data?.detail;
      // 402 KYC required — detail is a dict
      if (err.response?.status === 402 && detail?.required_tier) {
        setKycRequired({ tier: detail.required_tier, message: detail.message });
        toast.info(detail.message);
      } else if (err.response?.status === 451) {
        toast.error(detail || "Blocked by compliance screening");
      } else {
        toast.error(detail || "Withdrawal failed");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="tab-content withdraw-tab">
      <div className="section-header">
        <h2>💰 Cash Out</h2>
        <p>Withdraw your winnings to Bitcoin</p>
      </div>

      <div className="withdraw-container">
        <form className="withdraw-form" onSubmit={handleWithdraw}>
          <div className="form-section">
            <label>Select Game</label>
            <select value={selectedGame} onChange={(e) => setSelectedGame(e.target.value)} required>
              {games && games.map((game) => (
                <option key={game.id} value={game.id}>{game.name}</option>
              ))}
            </select>
          </div>

          <div className="form-section">
            <label>Withdrawal Amount (USD)</label>
            <div className="input-with-icon">
              <DollarSign size={20} />
              <input
                type="number"
                min="1"
                step="0.01"
                placeholder="Enter amount"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
              />
            </div>
            <small>Available Credits: ${user?.credits?.toFixed(2) || "0.00"}</small>
          </div>

          <div className="form-section">
            <label>Bitcoin Address</label>
            <input
              type="text"
              placeholder="bc1q... or lnbc... (Lightning)"
              value={btcAddress}
              onChange={(e) => setBtcAddress(e.target.value)}
              required
            />
            <small>Enter your BTC or Lightning Network address</small>
          </div>

          <div className="withdraw-info">
            <p>Processing Times:</p>
            <ul>
              <li><span>Under $500:</span> <span style={{color: '#00ff00'}}>Instant ⚡</span></li>
              <li><span>$500 and above:</span> <span style={{color: '#ffd700'}}>1-24 hours ⏳</span></li>
            </ul>
            <p style={{fontSize: '13px', marginTop: '15px', color: '#aaa'}}>
              Large withdrawals require manual approval for security.
            </p>
          </div>

          <button type="submit" className="btn-primary btn-withdraw" disabled={isLoading}>
            {isLoading ? <span className="btn-loader"></span> : `Withdraw $${amount || "0"}`}
          </button>
        </form>
      </div>

      {kycRequired && (
        <div data-testid="kyc-required-modal" style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999, padding: 20,
        }}>
          <div style={{
            maxWidth: 520, width: "100%", background: "#1a0b2e",
            border: "2px solid #ff1493", borderRadius: 16, padding: 28, color: "#fff",
          }}>
            <h2 style={{ margin: "0 0 8px", color: "#ffb44c", fontSize: 20 }}>Identity verification required</h2>
            <p style={{ color: "#cfc3e8", fontSize: 13, margin: "0 0 16px", lineHeight: 1.6 }}>
              {kycRequired.message} Federal law (31 CFR 1010) and our sweepstakes terms require us to
              verify your identity for this amount. Your documents are encrypted and only viewed by
              our compliance officer.
            </p>
            {!kycMethod && (
              <button
                onClick={() => initiateKyc(kycRequired.tier)}
                data-testid="kyc-start-btn"
                style={{
                  padding: "10px 22px", borderRadius: 8, border: "none",
                  background: "linear-gradient(135deg, #ff1493, #9b59b6)", color: "#fff",
                  fontWeight: 700, cursor: "pointer", fontSize: 14,
                }}
              >Start {kycRequired.tier} verification</button>
            )}
            {kycMethod === "persona" && personaUrl && (
              <a
                href={personaUrl}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="kyc-persona-link"
                style={{
                  display: "inline-block", padding: "10px 22px", borderRadius: 8,
                  background: "linear-gradient(135deg, #ff1493, #9b59b6)", color: "#fff",
                  fontWeight: 700, textDecoration: "none", fontSize: 14,
                }}
              >Continue via Persona →</a>
            )}
            {kycMethod === "manual_upload" && (
              <div style={{ marginTop: 8 }}>
                <p style={{ fontSize: 12, color: "#a593c2", marginBottom: 10 }}>
                  Upload a clear photo of a government-issued photo ID. Accepted: driver's license, passport, state ID.
                </p>
                <select
                  value={kycDocType}
                  onChange={e => setKycDocType(e.target.value)}
                  data-testid="kyc-doc-type"
                  style={{ padding: 8, borderRadius: 6, background: "#2d1b3d", color: "#fff", border: "1px solid #ff149344", marginBottom: 10 }}
                >
                  <option value="id_front">ID (front)</option>
                  <option value="id_back">ID (back)</option>
                  <option value="selfie">Selfie</option>
                  <option value="proof_of_address">Proof of address</option>
                </select>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp,application/pdf"
                  onChange={e => setKycFile(e.target.files?.[0] || null)}
                  data-testid="kyc-file-input"
                  style={{ display: "block", marginBottom: 10, color: "#cfc3e8" }}
                />
                <button
                  onClick={uploadKycDoc}
                  disabled={!kycFile}
                  data-testid="kyc-upload-btn"
                  style={{
                    padding: "10px 22px", borderRadius: 8, border: "none",
                    background: kycFile ? "#3aff9c" : "rgba(255,255,255,0.1)",
                    color: kycFile ? "#0a0a0f" : "#888", fontWeight: 700,
                    cursor: kycFile ? "pointer" : "not-allowed", fontSize: 14,
                  }}
                >Upload document</button>
              </div>
            )}
            <button
              onClick={() => { setKycRequired(null); setKycMethod(null); setPersonaUrl(""); }}
              data-testid="kyc-close-btn"
              style={{
                marginTop: 16, display: "block", marginLeft: "auto",
                padding: "6px 14px", borderRadius: 6, border: "1px solid rgba(255,255,255,0.2)",
                background: "transparent", color: "#cfc3e8", cursor: "pointer", fontSize: 12,
              }}
            >Close</button>
          </div>
        </div>
      )}
    </div>
  );
};

// Transactions Tab
const TransactionsTab = () => {
  const [transactions, setTransactions] = useState([]);

  const fetchTransactions = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/user/transactions`);
      setTransactions(data);
    } catch { toast.error("Failed to load transactions"); }
  }, []);

  useEffect(() => { fetchTransactions(); }, [fetchTransactions]);

  return (
    <div className="tab-content transactions-tab">
      <div className="section-header">
        <h2>Transaction History</h2>
        <p>View all your deposits and withdrawals</p>
      </div>

      {transactions.length === 0 ? (
        <div className="empty-state">
          <History size={48} />
          <p>No transactions yet</p>
        </div>
      ) : (
        <div className="transactions-list">
          {transactions.map((tx) => (
            <div key={tx.id} className={`transaction-row ${tx.status}`}>
              <div className="tx-icon">
                {tx.payment_method === "stripe" && <CreditCard size={20} />}
                {tx.payment_method === "crypto" && <span>₿</span>}
                {tx.payment_method === "cashapp" && <span>$</span>}
                {tx.payment_method === "chime" && <span>C</span>}
              </div>
              <div className="tx-details">
                <span className="tx-game">{tx.game_name}</span>
                <span className="tx-date">{new Date(tx.created_at).toLocaleString()}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Settings Tab
const SettingsTab = ({ user, onSuccess }) => {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [name, setName] = useState(user?.name || "");
  const [isLoading, setIsLoading] = useState(false);

  const handlePasswordChange = async (e) => {
    e.preventDefault();
    
    if (newPassword !== confirmPassword) {
      toast.error("New passwords don't match");
      return;
    }

    if (newPassword.length < 6) {
      toast.error("Password must be at least 6 characters");
      return;
    }

    setIsLoading(true);
    try {
      await axios.post(`${API}/user/password/change`, {
        current_password: currentPassword,
        new_password: newPassword
      });
      
      toast.success("Password changed successfully!");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Password change failed");
    } finally {
      setIsLoading(false);
    }
  };

  const handleProfileUpdate = async (e) => {
    e.preventDefault();
    
    setIsLoading(true);
    try {
      await axios.put(`${API}/user/profile`, { name });
      toast.success("Profile updated!");
      if (onSuccess) onSuccess();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Profile update failed");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="tab-content settings-tab">
      <div className="section-header">
        <h2>⚙️ Settings</h2>
        <p>Manage your account</p>
      </div>

      <div className="settings-container">
        {/* Profile Section */}
        <div className="settings-card">
          <h3>Profile Information</h3>
          <form onSubmit={handleProfileUpdate}>
            <div className="form-section">
              <label>Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            
            <div className="form-section">
              <label>Email</label>
              <input
                type="email"
                value={user?.email || ""}
                disabled
                style={{opacity: 0.6}}
              />
              <small>Email cannot be changed</small>
            </div>

            <button type="submit" className="btn-primary" disabled={isLoading}>
              {isLoading ? <span className="btn-loader"></span> : "Update Profile"}
            </button>
          </form>
        </div>

        {/* Password Section */}
        <div className="settings-card">
          <h3>Change Password</h3>
          <form onSubmit={handlePasswordChange}>
            <div className="form-section">
              <label>Current Password</label>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </div>

            <div className="form-section">
              <label>New Password</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={6}
              />
            </div>

            <div className="form-section">
              <label>Confirm New Password</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                minLength={6}
              />
            </div>

            <button type="submit" className="btn-primary" disabled={isLoading}>
              {isLoading ? <span className="btn-loader"></span> : "Change Password"}
            </button>
          </form>
        </div>

        {/* Account Info */}
        <div className="settings-card">
          <h3>Account Information</h3>
          <div className="info-row">
            <span>Account Status:</span>
            <span className="status-badge active">Active</span>
          </div>
          <div className="info-row">
            <span>Member Since:</span>
            <span>{new Date(user?.created_at).toLocaleDateString()}</span>
          </div>
          <div className="info-row">
            <span>Current Credits:</span>
            <span className="credits-amount">${user?.credits?.toFixed(2) || "0.00"}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

// Support Tab
const SupportTab = ({ user }) => {
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [priority, setPriority] = useState("normal");
  const [tickets, setTickets] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchTickets = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/user/support/tickets`);
      setTickets(data);
    } catch {
      // Failed to load tickets silently
    }
  }, []);

  useEffect(() => {
    fetchTickets();
  }, [fetchTickets]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    setIsLoading(true);
    try {
      await axios.post(`${API}/user/support/ticket`, {
        subject,
        message,
        priority
      });
      
      toast.success("Support ticket created! We'll respond soon.");
      setSubject("");
      setMessage("");
      setPriority("normal");
      fetchTickets();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to create ticket");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="tab-content support-tab">
      <div className="section-header">
        <h2>🛡️ Support</h2>
        <p>We're here to help!</p>
      </div>

      <div className="support-container">
        {/* Create Ticket Form */}
        <div className="support-card">
          <h3>Create Support Ticket</h3>
          <form onSubmit={handleSubmit}>
            <div className="form-section">
              <label>Subject</label>
              <input
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="What do you need help with?"
                required
              />
            </div>

            <div className="form-section">
              <label>Priority</label>
              <select value={priority} onChange={(e) => setPriority(e.target.value)}>
                <option value="low">Low - General Question</option>
                <option value="normal">Normal - Need Assistance</option>
                <option value="high">High - Urgent Issue</option>
              </select>
            </div>

            <div className="form-section">
              <label>Message</label>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Describe your issue in detail..."
                rows={5}
                required
              />
            </div>

            <button type="submit" className="btn-primary" disabled={isLoading}>
              {isLoading ? <span className="btn-loader"></span> : "Submit Ticket"}
            </button>
          </form>
        </div>

        {/* My Tickets */}
        <div className="support-card">
          <h3>My Tickets</h3>
          {tickets.length === 0 ? (
            <p className="empty-state">No tickets yet. Create one above if you need help!</p>
          ) : (
            <div className="tickets-list">
              {tickets.map((ticket) => (
                <div key={ticket.ticket_id} className="ticket-item">
                  <div className="ticket-header">
                    <span className="ticket-subject">{ticket.subject}</span>
                    <span className={`ticket-status ${ticket.status}`}>{ticket.status}</span>
                  </div>
                  <div className="ticket-meta">
                    <span className={`ticket-priority priority-${ticket.priority}`}>
                      {ticket.priority}
                    </span>
                    <span className="ticket-date">
                      {new Date(ticket.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Contact Info */}
        <div className="support-card contact-card">
          <h3>Other Ways to Reach Us</h3>
          <p><strong>Email:</strong> support@wah-lah.com</p>
          <p><strong>Hours:</strong> 24/7 Support</p>
          <p><strong>Response Time:</strong> Usually within 2-4 hours</p>
        </div>
      </div>
    </div>
  );
};

const PaymentSuccess = () => {
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState("checking");
  const [paymentData, setPaymentData] = useState(null);
  const { refreshUser } = useAuth();
  const sessionId = searchParams.get("session_id");

  const pollStatus = useCallback(async (attempts) => {
    if (attempts >= 5) { setStatus("timeout"); return; }
    try {
      const { data } = await axios.get(`${API}/checkout/status/${sessionId}`);
      setPaymentData(data);
      if (data.payment_status === "paid") {
        setStatus("success");
        refreshUser();
      } else if (data.status === "expired") {
        setStatus("failed");
      } else {
        setTimeout(() => pollStatus(attempts + 1), 2000);
      }
    } catch { setStatus("error"); }
  }, [sessionId, refreshUser]);

  useEffect(() => {
    if (sessionId) pollStatus(0);
  }, [sessionId, pollStatus]);

  return (
    <div className="result-page">
      <CandyBackground />
      <div className="result-card">
        {status === "checking" && (
          <>
            <div className="result-loader"><Sparkles size={48} /></div>
            <h2>Processing Payment...</h2>
          </>
        )}
        {status === "success" && (
          <>
            <div className="result-icon success"><Check size={48} /></div>
            <h2>Payment Successful!</h2>
            <p>Credits have been added to your account</p>
            <Link to="/" className="btn-primary">Back to Dashboard</Link>
          </>
        )}
        {status === "failed" && (
          <>
            <div className="result-icon error">✗</div>
            <h2>Payment Failed</h2>
            <Link to="/" className="btn-secondary">Try Again</Link>
          </>
        )}
      </div>
    </div>
  );
};

const PaymentCancel = () => (
  <div className="result-page">
    <CandyBackground />
    <div className="result-card">
      <div className="result-icon warning">!</div>
      <h2>Payment Cancelled</h2>
      <Link to="/" className="btn-secondary">Back to Dashboard</Link>
    </div>
  </div>
);

// Admin Panel (simplified - keeping existing logic)
const AdminPanel = () => {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [stats, setStats] = useState({});
  const [users, setUsers] = useState([]);
  const [games, setGames] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [showGameModal, setShowGameModal] = useState(false);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [showUserModal, setShowUserModal] = useState(false);
  const [editingGame, setEditingGame] = useState(null);
  const [selectedUser, setSelectedUser] = useState(null);
  const navigate = useNavigate();

  const fetchData = useCallback(async () => {
    try {
      const [statsRes, usersRes, gamesRes, txRes] = await Promise.all([
        axios.get(`${API}/admin/stats`),
        axios.get(`${API}/admin/users`),
        axios.get(`${API}/games/all`),
        axios.get(`${API}/admin/transactions`)
      ]);
      setStats(statsRes.data);
      setUsers(usersRes.data);
      setGames(gamesRes.data);
      setTransactions(txRes.data);
    } catch { toast.error("Failed to load data"); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSaveGame = async (gameData) => {
    try {
      if (editingGame) {
        await axios.put(`${API}/games/${editingGame.id}`, gameData);
      } else {
        await axios.post(`${API}/games`, gameData);
      }
      toast.success("Game saved");
      fetchData();
      setShowGameModal(false);
      setEditingGame(null);
    } catch { toast.error("Failed to save game"); }
  };

  const handleDeleteGame = async (gameId) => {
    if (window.confirm("Delete this game?")) {
      try {
        await axios.delete(`${API}/games/${gameId}`);
        toast.success("Game deleted");
        fetchData();
      } catch { toast.error("Failed to delete"); }
    }
  };

  const handleManualPayment = async (paymentData) => {
    try {
      await axios.post(`${API}/admin/payments/manual`, paymentData);
      toast.success("Credits added");
      fetchData();
      setShowPaymentModal(false);
      setSelectedUser(null);
    } catch { toast.error("Failed to add credits"); }
  };

  const handleUpdateUser = async (userData) => {
    try {
      await axios.put(`${API}/admin/users/${selectedUser.id}`, userData);
      toast.success("User updated");
      fetchData();
      setShowUserModal(false);
      setSelectedUser(null);
    } catch { toast.error("Failed to update user"); }
  };

  const tabs = [
    { id: "dashboard", label: "Dashboard", icon: <BarChart3 size={18} /> },
    { id: "launch", label: "Launch Checklist", icon: <Rocket size={18} /> },
    { id: "giftcards", label: "Gift Cards", icon: <Gift size={18} /> },
    { id: "nerve", label: "Nerve Center", icon: <Activity size={18} /> },
    { id: "games", label: "Games", icon: <Gamepad2 size={18} /> },
    { id: "users", label: "Users", icon: <Users size={18} /> },
    { id: "transactions", label: "Transactions", icon: <CreditCard size={18} /> },
    { id: "extensions", label: "Ops / Pool / Alerts", icon: <Shield size={18} /> },
  ];

  return (
    <div className="admin-page">
      <aside className="admin-sidebar">
        <div className="sidebar-brand">
          <Sparkles size={24} />
          <span>Admin</span>
        </div>
        <nav className="sidebar-nav">
          {tabs.map((tab) => (
            <button key={tab.id} data-testid={`admin-tab-${tab.id}`} className={`nav-item ${activeTab === tab.id ? "active" : ""}`} onClick={() => setActiveTab(tab.id)}>
              {tab.icon}<span>{tab.label}</span>
            </button>
          ))}
        </nav>
        <button className="nav-item logout" onClick={() => navigate("/")}>
          <ChevronRight size={18} style={{ transform: 'rotate(180deg)' }} /><span>Back</span>
        </button>
      </aside>

      <main className="admin-main">
        {activeTab === "dashboard" && (
          <div className="admin-dashboard">
            <h2>Dashboard</h2>
            <LaunchChecklist />
            <div className="stats-grid">
              <div className="stat-card"><Users size={32} /><div className="stat-value">{stats.total_users || 0}</div><div className="stat-label">Users</div></div>
              <div className="stat-card"><CreditCard size={32} /><div className="stat-value">{stats.completed_transactions || 0}</div><div className="stat-label">Payments</div></div>
              <div className="stat-card highlight"><Wallet size={32} /><div className="stat-value">${(stats.total_revenue || 0).toFixed(2)}</div><div className="stat-label">Revenue</div></div>
            </div>
          </div>
        )}

        {activeTab === "launch" && (
          <div className="admin-section">
            <div className="section-header">
              <h2>Pilot Launch Checklist</h2>
              <p>Pre-flight gates before opening the doors to live traffic.</p>
            </div>
            <LaunchChecklist />
          </div>
        )}

        {activeTab === "giftcards" && (
          <div className="admin-section">
            <div className="section-header">
              <h2>Gift Card Queue</h2>
              <p>Fulfill pending gift-card redemptions manually. Paste code → Fulfill. User gets emailed.</p>
            </div>
            <AdminGiftCards />
          </div>
        )}

        {activeTab === "games" && (
          <div className="admin-section">
            <div className="section-header">
              <h2>Games</h2>
              <button className="btn-primary" onClick={() => { setEditingGame(null); setShowGameModal(true); }}>+ Add Game</button>
            </div>
            <div className="data-table">
              <table>
                <thead><tr><th>Logo</th><th>Name</th><th>URL</th><th>Status</th><th>Actions</th></tr></thead>
                <tbody>
                  {games.map((game) => (
                    <tr key={game.id}>
                      <td><img src={game.logo_url} alt="" className="table-logo" onError={(e) => { e.target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(game.name)}&background=1a1a2e&color=F59E0B&size=40&bold=true`; }} /></td>
                      <td>{game.name}</td>
                      <td><a href={game.game_url} target="_blank" rel="noreferrer">{game.game_url}</a></td>
                      <td><span className={`badge ${game.is_active ? "active" : "inactive"}`}>{game.is_active ? "Active" : "Inactive"}</span></td>
                      <td>
                        <button className="btn-sm" onClick={() => { setEditingGame(game); setShowGameModal(true); }}>Edit</button>
                        <button className="btn-sm danger" onClick={() => handleDeleteGame(game.id)}>Delete</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === "users" && (
          <div className="admin-section">
            <h2>Users</h2>
            <div className="data-table">
              <table>
                <thead><tr><th>Name</th><th>Email</th><th>Credits</th><th>Age Verified</th><th>Actions</th></tr></thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td>{u.name}</td>
                      <td>{u.email}</td>
                      <td>${(u.credits || 0).toFixed(2)}</td>
                      <td><span className={`badge ${u.age_verified ? "active" : "inactive"}`}>{u.age_verified ? "Yes" : "No"}</span></td>
                      <td>
                        <button className="btn-sm" onClick={() => { setSelectedUser(u); setShowUserModal(true); }}>Edit</button>
                        <button className="btn-sm primary" onClick={() => { setSelectedUser(u); setShowPaymentModal(true); }}>Add Credits</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === "transactions" && (
          <div className="admin-section">
            <h2>Transactions</h2>
            <div className="data-table">
              <table>
                <thead><tr><th>Date</th><th>User</th><th>Game</th><th>Amount</th><th>Method</th><th>Status</th></tr></thead>
                <tbody>
                  {transactions.map((tx) => (
                    <tr key={tx.id}>
                      <td>{new Date(tx.created_at).toLocaleString()}</td>
                      <td>{tx.user_email}</td>
                      <td>{tx.game_name}</td>
                      <td>${tx.amount.toFixed(2)}</td>
                      <td>{tx.payment_method}</td>
                      <td><span className={`badge ${tx.status}`}>{tx.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === "nerve" && (
          <div style={{ margin: "-20px -20px" }}><NerveCenter /></div>
        )}

        {activeTab === "extensions" && (
          <div className="admin-section">
            <AdminExtensions embedded />
          </div>
        )}
      </main>

      {showGameModal && <GameModal game={editingGame} onSave={handleSaveGame} onClose={() => { setShowGameModal(false); setEditingGame(null); }} />}
      {showPaymentModal && selectedUser && <ManualPaymentModal user={selectedUser} games={games} onSave={handleManualPayment} onClose={() => { setShowPaymentModal(false); setSelectedUser(null); }} />}
      {showUserModal && selectedUser && <UserEditModal user={selectedUser} games={games} onSave={handleUpdateUser} onClose={() => { setShowUserModal(false); setSelectedUser(null); }} />}
    </div>
  );
};

// Modals
const GameModal = ({ game, onSave, onClose }) => {
  const [formData, setFormData] = useState({
    name: game?.name || "",
    logo_url: game?.logo_url || "",
    game_url: game?.game_url || "",
    description: game?.description || "",
    is_active: game?.is_active ?? true,
    accent_color: game?.accent_color || "#ff00ff"
  });

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>&times;</button>
        <h2>{game ? "Edit Game" : "Add Game"}</h2>
        <form onSubmit={(e) => { e.preventDefault(); onSave(formData); }}>
          <div className="form-group"><label>Name</label><input value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} required /></div>
          <div className="form-group"><label>Logo URL</label><input value={formData.logo_url} onChange={(e) => setFormData({ ...formData, logo_url: e.target.value })} required /></div>
          <div className="form-group"><label>Download URL</label><input value={formData.game_url} onChange={(e) => setFormData({ ...formData, game_url: e.target.value })} required /></div>
          <div className="form-row">
            <label className="checkbox-label"><input type="checkbox" checked={formData.is_active} onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })} /><span className="checkbox-custom"></span>Active</label>
          </div>
          <button type="submit" className="btn-primary">Save</button>
        </form>
      </div>
    </div>
  );
};

const UserEditModal = ({ user, games, onSave, onClose }) => {
  const [gameAccounts, setGameAccounts] = useState(user.game_accounts || {});
  const [gamePassword, setGamePassword] = useState(user.game_password || "");

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content user-modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>&times;</button>
        <h2>Edit: {user.name}</h2>
        <p className="modal-subtitle">{user.email}</p>
        
        <div className="form-section">
          <label>Game Password (all games)</label>
          <input value={gamePassword} onChange={(e) => setGamePassword(e.target.value)} placeholder="Universal password" />
        </div>

        <div className="form-section">
          <label>Game Accounts</label>
          <div className="game-accounts-list">
            {games.map((game) => (
              <div key={game.id} className="game-account-row">
                <span>{game.name}</span>
                <input
                  placeholder="Account name"
                  value={gameAccounts[game.id]?.account_name || ""}
                  onChange={(e) => setGameAccounts({...gameAccounts, [game.id]: { game_name: game.name, account_name: e.target.value }})}
                />
              </div>
            ))}
          </div>
        </div>

        <button className="btn-primary" onClick={() => onSave({ game_accounts: gameAccounts, game_password: gamePassword })}>Save</button>
      </div>
    </div>
  );
};

const ManualPaymentModal = ({ user, games, onSave, onClose }) => {
  const [formData, setFormData] = useState({
    user_id: user.id,
    amount: 10,
    credits: 10,
    game_id: games[0]?.id || "",
    account_name: "manual",
    payment_method: "cashapp",
    notes: ""
  });

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>&times;</button>
        <h2>Add Credits: {user.name}</h2>
        <form onSubmit={(e) => { e.preventDefault(); onSave({...formData, credits: formData.amount}); }}>
          <div className="quick-amounts">
            {[10, 20, 50, 100, 200].map((val) => (
              <button type="button" key={val} className={`quick-btn ${formData.amount === val ? "selected" : ""}`} onClick={() => setFormData({ ...formData, amount: val, credits: val })}>
                ${val}
              </button>
            ))}
          </div>
          <div className="form-group"><label>Amount</label><input type="number" value={formData.amount} onChange={(e) => setFormData({ ...formData, amount: parseFloat(e.target.value), credits: parseFloat(e.target.value) })} /></div>
          <div className="form-group">
            <label>Game</label>
            <select value={formData.game_id} onChange={(e) => setFormData({ ...formData, game_id: e.target.value })}>
              {games.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label>Payment Method</label>
            <select value={formData.payment_method} onChange={(e) => setFormData({ ...formData, payment_method: e.target.value })}>
              <option value="cashapp">Cash App</option>
              <option value="chime">Chime</option>
              <option value="crypto">Crypto</option>
            </select>
          </div>
          <button type="submit" className="btn-primary">Add Credits</button>
        </form>
      </div>
    </div>
  );
};

function App() {
  return (
    <AuthProvider>
      <div className="App">
        <BrowserRouter>
          <Routes>
            <Route path="/welcome" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
            <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/payment/success" element={<ProtectedRoute><PaymentSuccess /></ProtectedRoute>} />
            <Route path="/payment/cancel" element={<ProtectedRoute><PaymentCancel /></ProtectedRoute>} />
            <Route path="/admin" element={<ProtectedRoute adminOnly><AdminPanel /></ProtectedRoute>} />
            <Route path="/admin/nerve-center" element={<ProtectedRoute adminOnly><NerveCenter /></ProtectedRoute>} />
            <Route path="/boss" element={<ProtectedRoute adminOnly><BossMode /></ProtectedRoute>} />
            <Route path="/admin/extensions" element={<Navigate to="/admin" replace />} />
            <Route path="/master-control" element={<ProtectedRoute adminOnly><MasterControlHub /></ProtectedRoute>} />
            <Route path="/master-control/:platformId" element={<ProtectedRoute adminOnly><MasterControl /></ProtectedRoute>} />
          </Routes>
        </BrowserRouter>
        <Toaster position="top-center" richColors />
      </div>
    </AuthProvider>
  );
}

export default App;
