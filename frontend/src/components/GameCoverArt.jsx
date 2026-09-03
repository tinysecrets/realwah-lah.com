/* ---------------------------------------------------------------------------
 * GameCoverArt — original, premium illustrated covers for each platform.
 *
 * These are original artwork (not vendor/trademarked assets): each cover uses
 * the game's thematic palette + motifs and is drawn entirely in SVG so it
 * stays crisp at any size and matches the site's dark-casino language.
 * ------------------------------------------------------------------------ */

const FireKirin = () => (
  <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Fire Kirin art">
    <defs>
      <radialGradient id="fk-bg" cx="50%" cy="40%" r="80%">
        <stop offset="0%" stopColor="#7a1f3d" />
        <stop offset="55%" stopColor="#3b0a20" />
        <stop offset="100%" stopColor="#15040c" />
      </radialGradient>
      <radialGradient id="fk-fire" cx="50%" cy="70%" r="70%">
        <stop offset="0%" stopColor="#FFE45C" />
        <stop offset="45%" stopColor="#FF7A2E" />
        <stop offset="100%" stopColor="#8B0000" />
      </radialGradient>
      <radialGradient id="fk-glow" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="#FFB84D" stopOpacity="0.55" />
        <stop offset="100%" stopColor="#FFB84D" stopOpacity="0" />
      </radialGradient>
    </defs>
    <rect width="400" height="300" fill="url(#fk-bg)" />
    <circle cx="120" cy="190" r="150" fill="url(#fk-glow)" />
    <circle cx="300" cy="80" r="110" fill="url(#fk-glow)" opacity="0.6" />
    <g opacity="0.5" fill="#FFB84D">
      {[...Array(10)].map((_, i) => <circle key={i} cx={30 + i * 38} cy={50 + ((i * 53) % 60)} r={i % 3 === 0 ? 2 : 1} />)}
    </g>
    <g transform="translate(200 150) scale(2.3)">
      <path d="M0 -20 c2 7 8 10 8 18 a10 10 0 1 1 -20 0 c0 -5 3 -6 4 -9 1.5 3 3 4 3 8 0 -5 2 -10 5 -17z" fill="url(#fk-fire)" />
      <circle cx="6" cy="8" r="1" fill="#15040c" />
    </g>
    <path d="M40 260 c60 -20 120 16 190 6 s100 -26 150 -8" stroke="#FF7A2E" strokeWidth="3" fill="none" opacity="0.7" strokeLinecap="round" />
    <path d="M30 268 c70 -24 150 20 230 4 s90 -20 120 2" stroke="#D43B86" strokeWidth="2" fill="none" opacity="0.5" strokeLinecap="round" />
  </svg>
);

const Juwa = () => (
  <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Juwa art">
    <defs>
      <linearGradient id="jw-bg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#2a0a18" />
        <stop offset="55%" stopColor="#4a0f22" />
        <stop offset="100%" stopColor="#140510" />
      </linearGradient>
      <radialGradient id="jw-cherry" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="#FF6B8A" />
        <stop offset="60%" stopColor="#E01950" />
        <stop offset="100%" stopColor="#8E0B2F" />
      </radialGradient>
      <radialGradient id="jw-glow" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="#FF5477" stopOpacity="0.5" />
        <stop offset="100%" stopColor="#FF5477" stopOpacity="0" />
      </radialGradient>
    </defs>
    <rect width="400" height="300" fill="url(#jw-bg)" />
    <circle cx="200" cy="170" r="150" fill="url(#jw-glow)" />
    <g opacity="0.4" fill="#FFB3C1">
      {[...Array(9)].map((_, i) => <circle key={i} cx={40 + i * 42} cy={40 + ((i * 71) % 70)} r={i % 2 ? 1.4 : 0.8} />)}
    </g>
    <g transform="translate(200 175)">
      <path d="M0 -20 c-8 10 2 26 -6 40" stroke="#4CAF50" strokeWidth="3" strokeLinecap="round" fill="none" />
      <path d="M0 -20 c8 10 -2 26 6 40" stroke="#4CAF50" strokeWidth="3" strokeLinecap="round" fill="none" />
      <path d="M8 -22 c14 -6 26 2 28 12 -12 4 -24 -2 -28 -12z" fill="#6BBF59" />
      <g>
        <circle cx="-32" cy="52" r="34" fill="url(#jw-cherry)" />
        <circle cx="32" cy="58" r="34" fill="url(#jw-cherry)" />
        <ellipse cx="-38" cy="46" rx="7" ry="5" fill="#FFB3C1" opacity="0.7" />
        <ellipse cx="26" cy="52" rx="7" ry="5" fill="#FFB3C1" opacity="0.7" />
      </g>
    </g>
  </svg>
);

const OrionStars = () => (
  <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Orion Stars art">
    <defs>
      <radialGradient id="os-bg" cx="40%" cy="30%" r="100%">
        <stop offset="0%" stopColor="#6366F1" />
        <stop offset="55%" stopColor="#312E81" />
        <stop offset="100%" stopColor="#0B061A" />
      </radialGradient>
      <radialGradient id="os-glow" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="#F0ABFC" stopOpacity="0.55" />
        <stop offset="100%" stopColor="#F0ABFC" stopOpacity="0" />
      </radialGradient>
      <radialGradient id="os-spark" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="#B8E1FF" />
        <stop offset="100%" stopColor="#0066CC" />
      </radialGradient>
    </defs>
    <rect width="400" height="300" fill="url(#os-bg)" />
    <circle cx="70" cy="220" r="180" fill="url(#os-glow)" />
    <circle cx="330" cy="40" r="120" fill="url(#os-glow)" opacity="0.7" />
    <g fill="#ECFEFF" opacity="0.8">
      {[...Array(14)].map((_, i) => <circle key={i} cx={20 + i * 30} cy={30 + ((i * 47) % 80)} r={1 + (i % 2)} />)}
    </g>
    <g transform="translate(200 160) scale(1.9)">
      <path d="M0 -34 l6 10 34 4 -24 18 6 32 -22 -14 -22 14 6 -32 -24 -18 34 -4z" fill="url(#os-spark)" opacity="0.95" />
      <circle r="5" fill="#FFFFFF" />
    </g>
    <g stroke="#FDE68A" strokeOpacity="0.5" strokeWidth="1" fill="none" strokeDasharray="2 3" transform="translate(60 60) scale(0.8)">
      <line x1="70" y1="70" x2="110" y2="118" /><line x1="110" y1="118" x2="128" y2="130" />
      <line x1="128" y1="130" x2="146" y2="142" /><line x1="146" y1="142" x2="190" y2="186" />
      <line x1="110" y1="118" x2="90" y2="150" /><line x1="146" y1="142" x2="168" y2="108" />
    </g>
  </svg>
);

const UltraPanda = () => (
  <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Ultra Panda art">
    <defs>
      <linearGradient id="up-bg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#0d2b1a" />
        <stop offset="55%" stopColor="#14402a" />
        <stop offset="100%" stopColor="#06160d" />
      </linearGradient>
      <radialGradient id="up-glow" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="#6BBF59" stopOpacity="0.5" />
        <stop offset="100%" stopColor="#6BBF59" stopOpacity="0" />
      </radialGradient>
    </defs>
    <rect width="400" height="300" fill="url(#up-bg)" />
    <circle cx="200" cy="160" r="150" fill="url(#up-glow)" />
    <g stroke="#2E7D32" strokeWidth="5" opacity="0.7">
      <rect x="40" y="40" width="14" height="220" rx="7" fill="#0b2d19" stroke="none" />
      <rect x="346" y="60" width="14" height="200" rx="7" fill="#0b2d19" stroke="none" />
      <line x1="47" y1="80" x2="47" y2="120" />
      <line x1="353" y1="110" x2="353" y2="150" />
      <line x1="47" y1="200" x2="47" y2="230" />
    </g>
    <g transform="translate(200 165) scale(2.1)">
      <circle cx="0" cy="0" r="30" fill="#FAFAFA" />
      <circle cx="-26" cy="-24" r="10" fill="#111" />
      <circle cx="26" cy="-24" r="10" fill="#111" />
      <ellipse cx="-14" cy="-8" rx="7" ry="9" fill="#111" />
      <ellipse cx="14" cy="-8" rx="7" ry="9" fill="#111" />
      <circle cx="-14" cy="-11" r="2.5" fill="#FAFAFA" />
      <circle cx="14" cy="-11" r="2.5" fill="#FAFAFA" />
      <ellipse cx="0" cy="6" rx="4" ry="3" fill="#111" />
      <path d="M0 9 v3" stroke="#111" strokeWidth="2" />
    </g>
  </svg>
);

const PandaMaster = () => (
  <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Panda Master art">
    <defs>
      <linearGradient id="pm-bg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#0b2d1e" />
        <stop offset="55%" stopColor="#0f4028" />
        <stop offset="100%" stopColor="#05150c" />
      </linearGradient>
      <linearGradient id="pm-jade" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#A7E8BD" />
        <stop offset="100%" stopColor="#1B7F4D" />
      </linearGradient>
      <radialGradient id="pm-glow" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="#1B7F4D" stopOpacity="0.5" />
        <stop offset="100%" stopColor="#1B7F4D" stopOpacity="0" />
      </radialGradient>
    </defs>
    <rect width="400" height="300" fill="url(#pm-bg)" />
    <circle cx="200" cy="155" r="150" fill="url(#pm-glow)" />
    <g transform="translate(200 155)">
      <circle cx="0" cy="0" r="66" stroke="url(#pm-jade)" strokeWidth="4.5" fill="none" />
      <circle cx="0" cy="0" r="66" stroke="#FFD700" strokeWidth="1" fill="none" opacity="0.55" />
      <circle cx="0" cy="-40" r="7" fill="#A7E8BD" />
      <circle cx="0" cy="40" r="5" fill="#1B7F4D" opacity="0.7" />
      <g transform="translate(0 6) scale(0.55)">
        <circle cx="0" cy="0" r="30" fill="#FAFAFA" />
        <circle cx="-26" cy="-24" r="10" fill="#111" />
        <circle cx="26" cy="-24" r="10" fill="#111" />
        <ellipse cx="-14" cy="-8" rx="7" ry="9" fill="#111" />
        <ellipse cx="14" cy="-8" rx="7" ry="9" fill="#111" />
        <ellipse cx="0" cy="6" rx="4" ry="3" fill="#111" />
      </g>
    </g>
  </svg>
);

const GameVault = () => (
  <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Game Vault art">
    <defs>
      <radialGradient id="gv-bg" cx="50%" cy="40%" r="90%">
        <stop offset="0%" stopColor="#3a2a08" />
        <stop offset="55%" stopColor="#221703" />
        <stop offset="100%" stopColor="#0d0800" />
      </radialGradient>
      <linearGradient id="gv-gold" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#FFE26A" />
        <stop offset="100%" stopColor="#B8860B" />
      </linearGradient>
      <radialGradient id="gv-glow" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="#FFD700" stopOpacity="0.5" />
        <stop offset="100%" stopColor="#FFD700" stopOpacity="0" />
      </radialGradient>
    </defs>
    <rect width="400" height="300" fill="url(#gv-bg)" />
    <circle cx="200" cy="155" r="150" fill="url(#gv-glow)" />
    <g transform="translate(200 155) scale(1.5)">
      <circle cx="0" cy="0" r="24" fill="url(#gv-gold)" />
      <circle cx="0" cy="0" r="24" stroke="#8B6508" strokeWidth="2" fill="none" />
      <circle cx="0" cy="0" r="18" stroke="#8B6508" strokeWidth="1" fill="none" />
      {[0, 45, 90, 135, 180, 225, 270, 315].map(a => (
        <line key={a} x1={Math.cos(a * Math.PI / 180) * 12} y1={Math.sin(a * Math.PI / 180) * 12}
          x2={Math.cos(a * Math.PI / 180) * 20} y2={Math.sin(a * Math.PI / 180) * 20}
          stroke="#8B6508" strokeWidth="1.6" strokeLinecap="round" />
      ))}
      <circle cx="0" cy="0" r="4" fill="#8B6508" />
      <path d="M-22 -30 a30 30 0 0 1 44 0 l-6 0 a24 24 0 0 0 -32 0z" fill="#B8860B" opacity="0.6" />
    </g>
    <g opacity="0.5" fill="#FFE26A">
      {[...Array(8)].map((_, i) => <rect key={i} x={20 + i * 50} y={30 + ((i * 47) % 40)} width="4" height="4" rx="1" />)}
    </g>
  </svg>
);

const VBlink = () => (
  <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice" role="img" aria-label="vBlink art">
    <defs>
      <linearGradient id="vb-bg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#26083a" />
        <stop offset="55%" stopColor="#1a0530" />
        <stop offset="100%" stopColor="#0a0218" />
      </linearGradient>
      <linearGradient id="vb-gem" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#E8B6FF" />
        <stop offset="50%" stopColor="#8A2BE2" />
        <stop offset="100%" stopColor="#3A0080" />
      </linearGradient>
      <radialGradient id="vb-glow" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="#8A2BE2" stopOpacity="0.55" />
        <stop offset="100%" stopColor="#8A2BE2" stopOpacity="0" />
      </radialGradient>
    </defs>
    <rect width="400" height="300" fill="url(#vb-bg)" />
    <circle cx="200" cy="160" r="150" fill="url(#vb-glow)" />
    <g transform="translate(200 165) scale(1.9)">
      <path d="M0 -22 l16 14 -16 32 -16 -32z" fill="url(#vb-gem)" />
      <path d="M0 -22 l16 14 H-16z" fill="#B87DFF" opacity="0.7" />
      <path d="M0 -22 L-8 14 l8 32 M0 -22 l8 14 -8 32 M-16 14 h32" stroke="#FFF" strokeWidth="0.7" opacity="0.6" />
    </g>
    <g opacity="0.7" fill="#FFD700">
      <path d="M80 60 l3 8 8 3 -8 3 -3 8 -3 -8 -8 -3 8 -3z" />
      <path d="M320 220 l2.5 7 7 2.5 -7 2.5 -2.5 7 -2.5 -7 -7 -2.5 7 -2.5z" />
      <path d="M320 60 l2 6 6 2 -6 2 -2 6 -2 -6 -6 -2 6 -2z" />
    </g>
  </svg>
);

export const GAME_COVER_ART = {
  FireKirin,
  Juwa,
  OrionStars,
  UltraPanda,
  PandaMaster,
  GameVault,
  VBlink,
};

// Map a normalized game name/logo key to its original cover art.
const NAME_KEYS = {
  'fire kirin': 'FireKirin', 'firekirin': 'FireKirin',
  'juwa': 'Juwa',
  'orion stars': 'OrionStars', 'orionstars': 'OrionStars', 'orion': 'OrionStars',
  'ultra panda': 'UltraPanda', 'ultrapanda': 'UltraPanda',
  'panda master': 'PandaMaster', 'pandamaster': 'PandaMaster',
  'game vault': 'GameVault', 'gamevault': 'GameVault', 'vault': 'GameVault',
  'vblink': 'VBlink', 'v blink': 'VBlink',
};

export function coverForName(name = '') {
  const key = String(name).toLowerCase().trim();
  const art = NAME_KEYS[key];
  return art ? GAME_COVER_ART[art] : null;
}

export default GAME_COVER_ART;
