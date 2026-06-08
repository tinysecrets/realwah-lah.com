import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight, Zap, Shield, DollarSign, Gift, Gamepad2, CreditCard, Bitcoin,
  Clock, ChevronDown, Sparkles, Users, Lock
} from 'lucide-react';
import './LandingPage.css';

/* ---------------------------------------------------------------------------
 * Custom branded SVG icons — each game gets real art, no more generic Lucide
 * stickers on colored squares. Each icon uses the game's thematic palette.
 * ------------------------------------------------------------------------ */
const GameIcons = {
  FireKirin: () => (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <defs>
        <radialGradient id="fk-fire" cx="50%" cy="60%" r="60%">
          <stop offset="0%" stopColor="#FFE45C" />
          <stop offset="45%" stopColor="#D43B86" />
          <stop offset="100%" stopColor="#8B0000" />
        </radialGradient>
      </defs>
      {/* flame */}
      <path d="M32 4c3 8 10 12 10 22a12 12 0 1 1-24 0c0-6 4-8 5-12 2 4 4 5 4 10 0-6 2-12 5-20z" fill="url(#fk-fire)" />
      {/* koi tail waves */}
      <path d="M14 48c6-2 10 2 18 2s12-4 18-2c-4 5-10 8-18 8s-14-3-18-8z" fill="#FFB84D" opacity="0.9" />
      <path d="M18 54c4-1 8 2 14 2s10-3 14-2c-3 3-8 5-14 5s-11-2-14-5z" fill="#D43B86" />
      <circle cx="40" cy="22" r="1.5" fill="#0A0505" />
    </svg>
  ),
  Juwa: () => (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <defs>
        <linearGradient id="jw-cherry" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#FF5477" />
          <stop offset="100%" stopColor="#A30B2F" />
        </linearGradient>
      </defs>
      {/* stem */}
      <path d="M32 8c-2 8 6 12 2 20M32 8c2 8-6 12-2 20" stroke="#4CAF50" strokeWidth="2.5" strokeLinecap="round" fill="none" />
      {/* leaf */}
      <path d="M34 10c4-2 8 0 9 4-4 1-7-1-9-4z" fill="#6BBF59" />
      {/* cherries */}
      <circle cx="22" cy="42" r="12" fill="url(#jw-cherry)" />
      <circle cx="42" cy="44" r="12" fill="url(#jw-cherry)" />
      <ellipse cx="18" cy="38" rx="3" ry="2" fill="#FFB3C1" opacity="0.8" />
      <ellipse cx="38" cy="40" rx="3" ry="2" fill="#FFB3C1" opacity="0.8" />
    </svg>
  ),
  OrionStars: () => (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <defs>
        <radialGradient id="os-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#B8E1FF" />
          <stop offset="100%" stopColor="#0066CC" />
        </radialGradient>
      </defs>
      {/* Orion belt 3 stars */}
      <circle cx="20" cy="24" r="3" fill="url(#os-glow)" />
      <circle cx="32" cy="30" r="4" fill="url(#os-glow)" />
      <circle cx="44" cy="36" r="3" fill="url(#os-glow)" />
      {/* connecting lines */}
      <path d="M20 24L32 30L44 36" stroke="#5AB8FF" strokeWidth="1" strokeDasharray="2 2" opacity="0.6" />
      {/* shoulders */}
      <circle cx="14" cy="12" r="2" fill="#B8E1FF" />
      <circle cx="50" cy="12" r="2.5" fill="#B8E1FF" />
      {/* feet */}
      <circle cx="16" cy="52" r="2" fill="#B8E1FF" />
      <circle cx="48" cy="52" r="2" fill="#B8E1FF" />
      <path d="M14 12L20 24M50 12L44 36M20 24L16 52M44 36L48 52" stroke="#5AB8FF" strokeWidth="0.8" opacity="0.5" />
      {/* sparkle */}
      <path d="M32 30l1 3-1 3-1-3z M32 30l3 1 3-1-3-1z" fill="#FFF" opacity="0.8" />
    </svg>
  ),
  UltraPanda: () => (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      {/* bamboo behind */}
      <rect x="8" y="14" width="4" height="36" rx="1.5" fill="#4CAF50" />
      <line x1="8" y1="24" x2="12" y2="24" stroke="#2E7D32" strokeWidth="1" />
      <line x1="8" y1="36" x2="12" y2="36" stroke="#2E7D32" strokeWidth="1" />
      {/* panda head */}
      <circle cx="36" cy="34" r="18" fill="#FAFAFA" />
      {/* ears */}
      <circle cx="22" cy="22" r="6" fill="#111" />
      <circle cx="50" cy="22" r="6" fill="#111" />
      {/* eyes */}
      <ellipse cx="29" cy="32" rx="4" ry="5" fill="#111" />
      <ellipse cx="43" cy="32" rx="4" ry="5" fill="#111" />
      <circle cx="29" cy="31" r="1.5" fill="#FAFAFA" />
      <circle cx="43" cy="31" r="1.5" fill="#FAFAFA" />
      {/* nose */}
      <ellipse cx="36" cy="40" rx="2.5" ry="1.8" fill="#111" />
      <path d="M36 42v2" stroke="#111" strokeWidth="1.2" />
    </svg>
  ),
  PandaMaster: () => (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <defs>
        <linearGradient id="pm-jade" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#A7E8BD" />
          <stop offset="100%" stopColor="#1B7F4D" />
        </linearGradient>
      </defs>
      {/* jade ring */}
      <circle cx="32" cy="32" r="22" stroke="url(#pm-jade)" strokeWidth="5" fill="none" />
      <circle cx="32" cy="32" r="22" stroke="#FFD700" strokeWidth="0.8" fill="none" opacity="0.6" />
      {/* mini panda face in center */}
      <circle cx="32" cy="32" r="10" fill="#FAFAFA" />
      <circle cx="24" cy="26" r="3" fill="#111" />
      <circle cx="40" cy="26" r="3" fill="#111" />
      <ellipse cx="28" cy="32" rx="2" ry="2.5" fill="#111" />
      <ellipse cx="36" cy="32" rx="2" ry="2.5" fill="#111" />
      <ellipse cx="32" cy="37" rx="1.5" ry="1" fill="#111" />
    </svg>
  ),
  GameVault: () => (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <defs>
        <linearGradient id="gv-gold" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#FFE26A" />
          <stop offset="100%" stopColor="#B8860B" />
        </linearGradient>
      </defs>
      {/* vault door circle */}
      <circle cx="32" cy="32" r="24" fill="url(#gv-gold)" />
      <circle cx="32" cy="32" r="24" stroke="#8B6508" strokeWidth="1.5" fill="none" />
      <circle cx="32" cy="32" r="18" stroke="#8B6508" strokeWidth="1" fill="none" />
      {/* spokes of the dial */}
      {[0, 45, 90, 135, 180, 225, 270, 315].map(a => (
        <line key={a}
          x1={32 + Math.cos(a * Math.PI / 180) * 12}
          y1={32 + Math.sin(a * Math.PI / 180) * 12}
          x2={32 + Math.cos(a * Math.PI / 180) * 20}
          y2={32 + Math.sin(a * Math.PI / 180) * 20}
          stroke="#8B6508" strokeWidth="1.5" strokeLinecap="round" />
      ))}
      {/* center dial */}
      <circle cx="32" cy="32" r="4" fill="#8B6508" />
      <circle cx="32" cy="32" r="1.5" fill="#FFE26A" />
    </svg>
  ),
  vBlink: () => (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <defs>
        <linearGradient id="vb-gem" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#E8B6FF" />
          <stop offset="50%" stopColor="#8A2BE2" />
          <stop offset="100%" stopColor="#3A0080" />
        </linearGradient>
      </defs>
      {/* diamond gem */}
      <path d="M32 8l16 14-16 34L16 22z" fill="url(#vb-gem)" />
      <path d="M32 8l16 14H16z" fill="#B87DFF" opacity="0.7" />
      <path d="M32 8L24 22l8 34M32 8l8 14-8 34M16 22h32" stroke="#FFF" strokeWidth="0.8" opacity="0.6" />
      {/* sparkles */}
      <path d="M52 14l1 3 3 1-3 1-1 3-1-3-3-1 3-1z" fill="#FFD700" />
      <path d="M12 40l.6 2 2 .6-2 .6-.6 2-.6-2-2-.6 2-.6z" fill="#FFD700" />
    </svg>
  ),
};

const GAME_PLATFORMS = [
  { id: 1, name: 'Fire Kirin',   desc: 'Underwater fishing arena',     accent: '#D43B86', Icon: GameIcons.FireKirin },
  { id: 2, name: 'Juwa',         desc: 'Slot-room cherry classics',    accent: '#FF2D6E', Icon: GameIcons.Juwa },
  { id: 3, name: 'Orion Stars',  desc: 'Galactic constellation reels', accent: '#5AB8FF', Icon: GameIcons.OrionStars },
  { id: 4, name: 'Ultra Panda',  desc: 'Bamboo arcade rush',           accent: '#6BBF59', Icon: GameIcons.UltraPanda },
  { id: 5, name: 'Panda Master', desc: 'Jade-ring skill matches',      accent: '#1B7F4D', Icon: GameIcons.PandaMaster },
  { id: 6, name: 'Game Vault',   desc: 'Trophy-room gold classics',    accent: '#FFD700', Icon: GameIcons.GameVault },
  { id: 7, name: 'vBlink',       desc: 'Crystal match madness',        accent: '#B87DFF', Icon: GameIcons.vBlink },
];

const StatCounter = ({ end, label, prefix = '', suffix = '' }) => {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let start = 0;
    const duration = 1800;
    const step = end / (duration / 16);
    const timer = setInterval(() => {
      start += step;
      if (start >= end) { setCount(end); clearInterval(timer); }
      else setCount(Math.floor(start));
    }, 16);
    return () => clearInterval(timer);
  }, [end]);
  return (
    <div className="lp-stat" data-testid="stat-counter">
      <span className="lp-stat-num">{prefix}{count.toLocaleString()}{suffix}</span>
      <span className="lp-stat-label">{label}</span>
    </div>
  );
};

const GoldDivider = () => (
  <div className="lp-divider" aria-hidden>
    <svg viewBox="0 0 280 18" preserveAspectRatio="xMidYMid meet">
      <defs>
        <linearGradient id="div-gold" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%"   stopColor="#8B6508" stopOpacity="0" />
          <stop offset="40%"  stopColor="#FFA500" />
          <stop offset="60%"  stopColor="#FFE88A" />
          <stop offset="100%" stopColor="#8B6508" stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1="0" y1="9" x2="110" y2="9" stroke="url(#div-gold)" strokeWidth="1" />
      <line x1="170" y1="9" x2="280" y2="9" stroke="url(#div-gold)" strokeWidth="1" />
      <path d="M140 3 L146 9 L140 15 L134 9 Z" fill="url(#div-gold)" />
      <circle cx="140" cy="9" r="2" fill="#FFE88A" />
      <path d="M120 9 q6 -4 14 0 q-6 4 -14 0z" fill="url(#div-gold)" opacity=".7" />
      <path d="M160 9 q-6 -4 -14 0 q6 4 14 0z" fill="url(#div-gold)" opacity=".7" />
    </svg>
  </div>
);

const LandingPage = () => {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 50);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <div className="lp" data-testid="landing-page">
      {/* ------------------ NAV ------------------ */}
      <nav className={`lp-nav ${scrolled ? 'lp-nav-scrolled' : ''}`} data-testid="landing-nav">
        <div className="lp-nav-inner">
          <Link to="/" className="lp-logo" data-testid="landing-logo">
            <Sparkles className="lp-logo-icon" />
            <div className="lp-logo-stack">
              <span className="lp-logo-text">WAH-LAH</span>
              <span className="lp-logo-sub">· the magic reveal ·</span>
            </div>
          </Link>
          <div className="lp-nav-links">
            <a href="#games" className="lp-nav-link" data-testid="nav-games">Games</a>
            <a href="#how" className="lp-nav-link" data-testid="nav-how">How It Works</a>
            <a href="#payments" className="lp-nav-link" data-testid="nav-payments">Payments</a>
            <Link to="/login" className="lp-nav-signin" data-testid="nav-signin">Sign In</Link>
            <Link to="/register" className="lp-nav-cta" data-testid="nav-register">Play Free</Link>
          </div>
        </div>
      </nav>

      {/* ------------------ HERO — "The Reveal" ------------------ */}
      <section className="lp-hero" data-testid="hero-section">
        {/* atmospheric stage */}
        <div className="lp-stage-backdrop" aria-hidden />
        <div className="lp-stage-curtain lp-stage-curtain-left" aria-hidden>
          <div className="lp-curtain-fabric" />
          <div className="lp-curtain-tassel" aria-hidden />
        </div>
        <div className="lp-stage-curtain lp-stage-curtain-right" aria-hidden>
          <div className="lp-curtain-fabric" />
          <div className="lp-curtain-tassel" aria-hidden />
        </div>
        <div className="lp-spotlight" aria-hidden />
        <div className="lp-grain" aria-hidden />

        {/* gold leaf corner ornaments */}
        <svg className="lp-ornament lp-ornament-tl" viewBox="0 0 120 120" aria-hidden>
          <defs>
            <linearGradient id="orn-gold" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#FFE88A" />
              <stop offset="50%" stopColor="#FFA500" />
              <stop offset="100%" stopColor="#8B6508" />
            </linearGradient>
          </defs>
          <path d="M5 5 L40 5 M5 5 L5 40 M10 10 Q30 12 40 18 M10 10 Q12 30 18 40"
            stroke="url(#orn-gold)" strokeWidth="1.2" fill="none" />
          <path d="M20 20 q10 -6 20 0 q-4 10 -12 14 q-6 -6 -8 -14z"
            fill="url(#orn-gold)" opacity="0.85" />
          <circle cx="5" cy="5" r="2" fill="url(#orn-gold)" />
        </svg>
        <svg className="lp-ornament lp-ornament-tr" viewBox="0 0 120 120" aria-hidden>
          <path d="M115 5 L80 5 M115 5 L115 40 M110 10 Q90 12 80 18 M110 10 Q108 30 102 40"
            stroke="url(#orn-gold)" strokeWidth="1.2" fill="none" />
          <path d="M100 20 q-10 -6 -20 0 q4 10 12 14 q6 -6 8 -14z"
            fill="url(#orn-gold)" opacity="0.85" />
          <circle cx="115" cy="5" r="2" fill="url(#orn-gold)" />
        </svg>
        <svg className="lp-ornament lp-ornament-bl" viewBox="0 0 120 120" aria-hidden>
          <path d="M5 115 L40 115 M5 115 L5 80 M10 110 Q30 108 40 102 M10 110 Q12 90 18 80"
            stroke="url(#orn-gold)" strokeWidth="1.2" fill="none" />
          <circle cx="5" cy="115" r="2" fill="url(#orn-gold)" />
        </svg>
        <svg className="lp-ornament lp-ornament-br" viewBox="0 0 120 120" aria-hidden>
          <path d="M115 115 L80 115 M115 115 L115 80 M110 110 Q90 108 80 102 M110 110 Q108 90 102 80"
            stroke="url(#orn-gold)" strokeWidth="1.2" fill="none" />
          <circle cx="115" cy="115" r="2" fill="url(#orn-gold)" />
        </svg>

        <div className="lp-hero-content">
          <div className="lp-hero-left">
            <div className="lp-hero-badge" data-testid="hero-badge">
              <Gift size={14} />
              <span>100 FREE credits daily · No purchase necessary</span>
            </div>
            <h1 className="lp-hero-title">
              <span className="lp-kicker">Ladies &amp; gentlemen,</span>
              Watch your favourite games<br/>
              turn into <span className="lp-hero-gold">real Bitcoin.</span>
            </h1>
            <p className="lp-hero-desc">
              One lobby. Seven premium sweepstakes platforms. Deposit with card, Cash App or crypto — redeem winnings straight to your Bitcoin wallet. It's the <em>wah-lah</em> moment, on demand.
            </p>
            <div className="lp-hero-btns">
              <Link to="/register" className="lp-btn-primary" data-testid="hero-register-btn">
                Start Playing Free <ArrowRight size={20} />
              </Link>
              <Link to="/login" className="lp-btn-ghost" data-testid="hero-login-btn">
                Sign In
              </Link>
            </div>
            <div className="lp-hero-pills">
              <div className="lp-pill"><Zap size={14} /> Instant Deposits</div>
              <div className="lp-pill"><Shield size={14} /> Legal &amp; Compliant</div>
              <div className="lp-pill"><Bitcoin size={14} /> BTC Payouts</div>
            </div>
          </div>

          {/* The Reveal — genie + lamp + smoke, ONE integrated scene */}
          <div className="lp-hero-reveal" aria-hidden>
            <div className="lp-reveal-smoke lp-reveal-smoke-a" />
            <div className="lp-reveal-smoke lp-reveal-smoke-b" />
            <div className="lp-reveal-smoke lp-reveal-smoke-c" />
            <div className="lp-reveal-glow" />
            <img
              src="/mascots/genie_hero.png"
              alt=""
              className="lp-reveal-genie"
              data-testid="hero-mascot"
            />
            <img
              src="/mascots/genie_lamp_static.png"
              alt=""
              className="lp-reveal-lamp"
            />
            {/* gold particles — pure CSS, no sticker edges */}
            <div className="lp-particles">
              {Array.from({ length: 14 }).map((_, i) => (
                <span key={i} className={`lp-particle lp-particle-${i % 7}`} />
              ))}
            </div>
          </div>
        </div>

        <a href="#stats" className="lp-hero-scroll" aria-label="Scroll down">
          <ChevronDown size={20} className="lp-bounce" />
        </a>
      </section>

      {/* ------------------ STATS ------------------ */}
      <section className="lp-stats" id="stats" data-testid="stats-section">
        <StatCounter end={2500} label="Active Players" />
        <StatCounter end={7} label="Game Platforms" />
        <StatCounter end={100} label="Free Daily Credits" />
        <StatCounter end={50000} label="Credits Awarded" />
      </section>

      {/* ------------------ GAMES ------------------ */}
      <section className="lp-games" id="games" data-testid="games-section">
        <div className="lp-section-head">
          <span className="lp-section-tag">The Bill</span>
          <h2 className="lp-section-title">Seven Acts. One Stage.</h2>
          <p className="lp-section-desc">Every game, every night. Hand-picked sweepstakes platforms, wired through one account.</p>
        </div>
        <div className="lp-games-grid">
          {GAME_PLATFORMS.map((game, idx) => {
            const Icon = game.Icon;
            return (
              <div
                key={game.id}
                className="lp-game-card"
                style={{ animationDelay: `${idx * 0.08}s`, '--accent': game.accent }}
                data-testid={`game-card-${game.id}`}
              >
                <div className="lp-game-halo" aria-hidden />
                <div className="lp-game-art">
                  <Icon />
                </div>
                <h3 className="lp-game-name">{game.name}</h3>
                <p className="lp-game-desc">{game.desc}</p>
                <div className="lp-game-status">
                  <span className="lp-game-dot" />
                  On the bill now
                </div>
              </div>
            );
          })}
        </div>
        <div className="lp-games-cta">
          <Link to="/register" className="lp-btn-primary" data-testid="games-register-btn">
            Create Account &amp; Play <ArrowRight size={18} />
          </Link>
        </div>
      </section>

      <GoldDivider />

      {/* ------------------ HOW IT WORKS ------------------ */}
      <section className="lp-how" id="how" data-testid="how-section">
        <div className="lp-section-head">
          <span className="lp-section-tag">Behind the Curtain</span>
          <h2 className="lp-section-title">How WAH-LAH Works</h2>
          <p className="lp-section-desc">Four moves. No sleight of hand.</p>
        </div>
        <div className="lp-steps">
          {[
            { num: '01', title: 'Claim Free Credits', desc: 'Pick up 100 free credits every 24 hours — no purchase necessary. Required by law. Encouraged by us.', Icon: Gift },
            { num: '02', title: 'Purchase Tokens',    desc: 'Top up with card, crypto, or Cash App. Every purchase ships with matched bonus Game Credits.', Icon: CreditCard },
            { num: '03', title: 'Play the Bill',      desc: 'Seven premium platforms — Fire Kirin, Juwa, Orion Stars and more — one login.', Icon: Gamepad2 },
            { num: '04', title: 'Cash Out in BTC',    desc: 'Redeem winnings straight to your Bitcoin or Lightning wallet. Fast, clean, final.', Icon: Bitcoin },
          ].map((step, idx) => (
            <div key={idx} className="lp-step" style={{ animationDelay: `${idx * 0.12}s` }} data-testid={`step-${idx + 1}`}>
              <div className="lp-step-num">{step.num}</div>
              <div className="lp-step-icon"><step.Icon size={24} /></div>
              <h3 className="lp-step-title">{step.title}</h3>
              <p className="lp-step-desc">{step.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <GoldDivider />

      {/* ------------------ PAYMENTS ------------------ */}
      <section className="lp-payments" id="payments" data-testid="payments-section">
        <div className="lp-payments-inner">
          <div className="lp-payments-text">
            <span className="lp-section-tag">The Till</span>
            <h2 className="lp-section-title">Deposit your way.</h2>
            <p className="lp-section-desc">
              Credit-card quick, crypto discreet, Cash App instant. Every rail lands credits in seconds.
            </p>
            <div className="lp-payment-methods">
              <div className="lp-payment-card" data-testid="payment-stripe">
                <div className="lp-payment-icon"><CreditCard size={22} /></div>
                <div>
                  <h4>Card Payment</h4>
                  <p>Visa, Mastercard · Stripe secured</p>
                </div>
              </div>
              <div className="lp-payment-card" data-testid="payment-crypto">
                <div className="lp-payment-icon lp-payment-icon-btc"><Bitcoin size={22} /></div>
                <div>
                  <h4>Bitcoin &amp; Lightning</h4>
                  <p>On-chain or Lightning Network</p>
                </div>
              </div>
              <div className="lp-payment-card" data-testid="payment-cashapp">
                <div className="lp-payment-icon lp-payment-icon-cash"><DollarSign size={22} /></div>
                <div>
                  <h4>Cash App &amp; Chime</h4>
                  <p>Instant US transfers</p>
                </div>
              </div>
            </div>
          </div>
          <div className="lp-payments-stage" aria-hidden>
            <div className="lp-payments-glow" />
            <img src="/mascots/genie_pointing.png" alt="" className="lp-payments-mascot" data-testid="payments-mascot" />
          </div>
        </div>
      </section>

      <GoldDivider />

      {/* ------------------ TRUST ------------------ */}
      <section className="lp-trust" data-testid="trust-section">
        <div className="lp-section-head">
          <span className="lp-section-tag">Why WAH-LAH?</span>
          <h2 className="lp-section-title">Built for players. Run like a theatre.</h2>
        </div>
        <div className="lp-trust-grid">
          {[
            { Icon: Shield,  title: 'Legal & Compliant', desc: 'AMOE-backed daily credits keep every state legal. Geoblock + KYC gates run on every redemption.' },
            { Icon: Zap,     title: 'Instant Credits',        desc: 'Payment confirmed, credits delivered. No queues, no waiting-rooms.' },
            { Icon: Bitcoin, title: 'Bitcoin Payouts',        desc: 'Winnings out-the-door in BTC or Lightning — straight to your wallet.' },
            { Icon: Lock,    title: 'Secure Platform',        desc: 'JWT cookies, bcrypt hashes, brute-force lockout, encrypted secrets at rest.' },
            { Icon: Users,   title: 'Growing Community',      desc: 'Thousands of players across 7 premium platforms. One account unlocks the whole bill.' },
            { Icon: Clock,   title: '24/7 Availability',      desc: 'Play when you want. Claim credits daily. Support always on call.' },
          ].map((item, idx) => (
            <div key={item.title} className="lp-trust-card" style={{ animationDelay: `${idx * 0.08}s` }} data-testid={`trust-card-${idx}`}>
              <div className="lp-trust-icon"><item.Icon size={22} /></div>
              <h3>{item.title}</h3>
              <p>{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ------------------ CTA — final reveal ------------------ */}
      <section className="lp-cta" data-testid="cta-section">
        <div className="lp-cta-stage" aria-hidden>
          <div className="lp-cta-spot" />
          <img src="/mascots/genie_small_peek.png" alt="" className="lp-cta-peek" />
        </div>
        <div className="lp-cta-inner">
          <h2>Ready for the reveal?</h2>
          <p>Create your free account, claim 100 credits on the spot, and meet the Genie on stage.</p>
          <Link to="/register" className="lp-btn-primary lp-btn-lg" data-testid="cta-register-btn">
            Get Started Free <ArrowRight size={22} />
          </Link>
          <span className="lp-cta-note">Must be 21+ to play. Terms apply.</span>
        </div>
      </section>

      {/* ------------------ FOOTER ------------------ */}
      <footer className="lp-footer" data-testid="landing-footer">
        <div className="lp-footer-inner">
          <div className="lp-footer-brand">
            <Sparkles size={24} className="lp-footer-icon" />
            <span className="lp-footer-name">WAH-LAH</span>
            <p className="lp-footer-tagline">The magic reveal · Premium sweepstakes</p>
          </div>
          <div className="lp-footer-links">
            <div className="lp-footer-col">
              <h4>Platform</h4>
              <Link to="/register">Create Account</Link>
              <Link to="/login">Sign In</Link>
              <a href="#games">Games</a>
            </div>
            <div className="lp-footer-col">
              <h4>Legal</h4>
              <a href="/api/legal/terms" target="_blank" rel="noreferrer">Terms of Service</a>
              <a href="/api/legal/privacy" target="_blank" rel="noreferrer">Privacy Policy</a>
              <a href="/api/legal/responsible-gaming" target="_blank" rel="noreferrer">Responsible Gaming</a>
            </div>
            <div className="lp-footer-col">
              <h4>Support</h4>
              <Link to="/login">Help Center</Link>
              <span>support@wah-lah.com</span>
            </div>
          </div>
        </div>
        <div className="lp-footer-bottom">
          <p>© WAH-LAH. Must be 21+ to participate. No purchase necessary. Void where prohibited.</p>
          <p>National Problem Gambling Helpline: 1-800-GAMBLER</p>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
