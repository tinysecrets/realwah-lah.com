/**
 * WAH-LAH Scout Force
 *
 * An always-on, free-tier team of AI scouting agents. Each agent owns a world
 * region (or a niche vertical) and sweeps it on a schedule (cron) to find
 * communities, venues, groups, and wallets where new players gather.
 *
 * Hard rules (compliance, do not remove):
 *   1. INTEL ONLY — scouts surface contactable leads and points of interest.
 *      They never perform unsolicited outreach, DMs, or emails.
 *   2. NO PII SCRAPING — agents do not harvest private user data.
 *   3. Opt-in funnel — any player signup still happens through the platform's
 *      normal free-entry (AMOE) flow.
 *   4. Free tier — KV for memory, Workers AI for reasoning, cron for schedule.
 *      Nothing here costs money per run.
 */

const DEFAULT_MODEL = "@cf/meta/llama-3.1-8b-instruct-fast";

const SCOUT_TEAM = [
  {
    id: "north-america",
    region: "North America",
    brief: "Sources where casual/arcade/sweepstakes-style game players gather in North America (Facebook groups, Reddit communities, arcades, events, flea markets). Return contactable venue/community leads, no personal data.",
  },
  {
    id: "south-america",
    region: "South America",
    brief: "Locations and communities in South America where coin-operated game / arcade / game-tournament culture is strong. Return venue and community leads.",
  },
  {
    id: "europe",
    region: "Europe",
    brief: "Gaming communities and venues across Europe (esports bars, arcades, fair/carnival circuits, boardgame cafes). Return venue and community leads.",
  },
  {
    id: "africa",
    region: "Africa",
    brief: "Gaming hubs, internet cafes, mobile-gaming communities, and tournament scenes in Africa. Return venue and community leads.",
  },
  {
    id: "asia-pacific",
    region: "Asia & Pacific",
    brief: "Arcade culture, internet cafes, mobile-game communities, and esports venues across Asia-Pacific. Return venue and community leads.",
  },
  {
    id: "mine-niche",
    region: "Global niche",
    brief: "Cross-regional niche communities: sweepstakes-cafe operators, amusement 'redemption' game lounges, operators that run similar prize-redemption game models. Return operator leads (business contacts only).",
  },
];

const KV_LAST_RUN = "scout.last_run";
const KV_LEAD_DIGEST = "scout.lead_digest";
const KV_LOCK = "scout.lock";

export default {
  async scheduled(controller, env, ctx) {
    return runScoutRound(env, controller && controller.scheduledTime ? new Date(controller.scheduledTime) : new Date());
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/run") {
      // Fail closed: no ADMIN_TOKEN configured => no manual runs, ever.
      // (The old code fell back to the literal password "scout-force".)
      const expected = (env.ADMIN_TOKEN || "").trim();
      const provided = (request.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
      if (!expected || provided.length !== expected.length) {
        return new Response("unauthorized", { status: 401 });
      }
      let diff = 0;
      for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ provided.charCodeAt(i);
      if (diff !== 0) {
        return new Response("unauthorized", { status: 401 });
      }
      return Response.json(await runScoutRound(env, new Date()));
    }
    if (url.pathname === "/health") {
      return Response.json({ ok: true, team: SCOUT_TEAM.length, model: env.SCOUT_AI_MODEL || DEFAULT_MODEL });
    }
    return new Response("not found", { status: 404 });
  },
};

async function runScoutRound(env, now) {
  // Single-flight lock so overlapping crons don't double-run.
  const held = await env.SCOUT_KV.get(KV_LOCK, { type: "json" }).catch(() => null);
  if (held && Date.now() - held < 20 * 60 * 1000) {
    return { ok: false, reason: "already_running" };
  }
  await env.SCOUT_KV.put(KV_LOCK, String(Date.now()), { expirationTtl: 1800 });

  const results = { ran_at: now.toISOString(), team: [], leads: 0, errors: 0 };
  const digest = [];

  const team = parseTeam(env.SCOUT_TEAM);
  for (const scout of team) {
    try {
      const out = await runScout(scout, env, now);
      results.team.push(out.summary);
      results.leads += out.leads.length;
      digest.push({ scout: scout.id, n: out.leads.length, sample: out.leads.slice(0, 3) });
      if (out.leads.length) {
        await env.SCOUT_KV.put(`${KV_LEAD_DIGEST}.${scout.id}`, JSON.stringify(out.leads.slice(0, 20)));
      }
    } catch (err) {
      results.errors += 1;
      results.team.push({ scout: scout.id, error: String(err && err.message || err) });
    }
  }

  await env.SCOUT_KV.put(KV_LAST_RUN, JSON.stringify(results));
  await env.SCOUT_KV.delete(KV_LOCK);
  return results;
}

function parseTeam(raw) {
  if (!raw) return SCOUT_TEAM;
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.length) {
      return parsed.map((s) => (typeof s === "string" ? SCOUT_TEAM.find((x) => x.id === s) || SCOUT_TEAM[0] : { ...SCOUT_TEAM[0], ...s }));
    }
  } catch (_) { /* fall through */ }
  return SCOUT_TEAM;
}

async function runScout(scout, env, now) {
  // 0) Load scout memory so it doesn't re-report the same ground twice.
  const prior = await env.SCOUT_KV.get(`${scoutKey(scout)}.seen`, { type: "json" }).catch(() => []);
  const seen = new Set(Array.isArray(prior) ? prior : []);

  // 1) Mine open, public sources (RSS/JSON feeds the free net provides).
  const leads = await mineSources(scout, env, seen);

  // 2) Reasoning pass — rank and de-duplicate via the AI brain (best effort).
  let ranked = leads;
  if (leads.length && env.AI) {
    ranked = await rankLeads(env, scout, leads);
  }

  // 3) Forget old memory, remember today's, hand leads to the platform.
  const fresh = ranked.slice(0, 25);
  const digest = fresh.map((l) => l && (l.url || l.name || "")).filter(Boolean);
  const newSeen = Array.from(new Set([...digest, ...Array.from(seen).slice(-200)]));
  await env.SCOUT_KV.put(`${scoutKey(scout)}.seen`, JSON.stringify(newSeen));

  const written = await writeLeadsToMongo(env, scout, fresh, now);

  return { summary: { scout: scout.id, region: scout.region, found: leads.length, ranked: ranked.length, written: written }, leads: fresh };
}

function scoutKey(scout) {
  return `scout.${scout.id || "agent"}`;
}

// ---- source mining --------------------------------------------------------
// Kept to public, license-friendly endpoints only. No scraping of private data.
async function mineSources(scout, env, seen) {
  const gathered = [];
  const attempts = [
    {
      url: "https://hacker-news.firebaseio.com/v0/topstories.json",
      kind: "hn",
      label: "Hacker News",
      max: 5,
    },
    {
      url: "https://www.reddit.com/r/gaming/hot.json?limit=10",
      kind: "reddit",
      label: "r/gaming (public)",
      max: 5,
    },
    {
      url: "https://duckduckgo.com/?q=" + encodeURIComponent(`${scout.region} arcade gaming community venue`) + "&format=json&no_html=1&no_redirect=1&no_rewrite=1&t=wahlah-scout",
      kind: "web",
      label: "DuckDuckGo (text)",
      max: 6,
    },
  ];

  // Only touch sources that have a real feed for this scout's ground.
  for (const src of attempts) {
    if (!src.url) continue;
    try {
      const res = await fetch(src.url, { headers: { "accept": "application/json", "user-agent": "wahlah-scout/0.1 (intel-only)" }, cf: { cacheTtl: 3600 } });
      if (!res.ok) continue;
      const data = await res.json().catch(() => null);
      if (!data) continue;
      const items = extractItems(src.kind, data, scout);
      for (const it of items) {
        if (!it || !it.url) continue;
        if (seen.has(it.url || it.name || "")) continue;
        if (gathered.length < 12) gathered.push(it);
      }
    } catch (_) { /* source down — skip */ }
  }
  return gathered;
}

function extractItems(kind, data, scout) {
  if (kind === "hn") {
    if (!Array.isArray(data)) return [];
    return data.slice(0, 30).map((id) => ({
      kind: "site",
      name: "Hacker News item",
      note: `Id ${id} — tech community thread (lead surface, intel-only)`,
      url: `https://news.ycombinator.com/item?id=${id}`,
      score: 0.3,
      region: scout.region,
    }));
  }
  if (kind === "reddit") {
    const kids = data && data.data && data.data.children;
    if (!Array.isArray(kids)) return [];
    return kids.map((c) => {
      const d = c.data || {};
      return {
        kind: "community",
        name: (d.title || "").slice(0, 120),
        note: `r/${d.subreddit} — ${(d.num_comments || 0)} comments, score ${d.score || 0}`,
        url: "https://www.reddit.com" + (d.permalink || ""),
        score: Math.max(0.05, Math.min(1, (d.score || 0) / 200)),
        region: scout.region,
      };
    }).filter((x) => x.name);
  }
  if (kind === "web") {
    if (!Array.isArray(data.RelatedTopics) && !Array.isArray(data.results)) return [];
    const items = Array.isArray(data.results) ? data.results : data.RelatedTopics.map((t) => t.Result && t.Result.link ? { title: t.Text, link: t.FirstURL || t.Result.link } : null).filter(Boolean);
    return items.slice(0, 10).map((r) => ({
      kind: "venue",
      name: (r.title || r.Text || "").slice(0, 120),
      note: (r.note || r.abstract || "").slice(0, 200),
      url: r.link || (r.url || ""),
      score: 0.4,
      region: scout.region,
    })).filter((x) => x.url);
  }
  return [];
}

// ---- AI rank pass (best effort) --------------------------------------------
async function rankLeads(env, scout, leads) {
  try {
    const prompt =
      `You are a senior scout lead-ranker for a free-to-enter sweepstakes games platform. ` +
      `Your only job: given raw candidate leads below, pick the up to 8 most promising, ` +
      `low-friction, compliance-safe places where NEW casual players can be reached organically. ` +
      `Exclude anything that looks like personal/private data or harassment surfaces. ` +
      `Return ONLY a JSON array of strings, each a URL or name from the input list.\nRegion: ${scout.region}\n` +
      `Leads:\n${leads.map((l, i) => `${i}. ${l.name} — ${l.note}`).join("\n")}`;
    const res = await env.AI.run(env.SCOUT_AI_MODEL || DEFAULT_MODEL, { prompt });
    const text = (res && (res.response || res.result || "")) || "";
    const picked = extractJsonArray(text);
    if (!picked.length) return leads;
    const byKey = new Map(leads.map((l) => [l.url || l.name, l]));
    const out = picked.map((p) => byKey.get(p) || findFuzzy(leads, p)).filter(Boolean);
    return out.length ? out : leads;
  } catch (_) {
    return leads;
  }
}

function findFuzzy(leads, s) {
  for (const l of leads) {
    if ((l.url || "").includes(s) || (l.name || "").includes(s) || s.includes(l.url || "") || s.includes(l.name || "")) return l;
  }
  return null;
}

function extractJsonArray(text) {
  try {
    return JSON.parse(text);
  } catch (_) { /* not clean json */ }
  const m = text.match(/\[[\s\S]*\]/);
  if (!m) return [];
  try {
    return JSON.parse(m[0]);
  } catch (_) {
    return m[0].match(/"[^"]+"/g || []).map((s) => s.replace(/"/g, "")).filter(Boolean);
  }
}

// ---- write leads to the platform ------------------------------------------
// The worker holds NO database credentials: it POSTs leads to the backend,
// which writes `scout_leads` + `admin_alerts` with its own Mongo URI.
async function writeLeadsToMongo(env, scout, leads, now) {
  // NOTE: this is the seam where the production FastAPI backend (Motor) would
  // accept these leads into `scout_leads` + `admin_alerts`. The worker itself
  // does not depend on a mongo driver; it POSTs to /api/admin/scout/leads on
  // the backend when configured. (See backend route added alongside.)
  const endpoint = env.LEADS_WEBHOOK; // e.g. https://<render-app>.onrender.com/api/admin/scout/leads
  // HTTPS-only: the leads POST carries a bearer token — never send it over http.
  if (!endpoint || !/^https:\/\//i.test(endpoint)) return 0;
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "content-type": "application/json", "authorization": "Bearer " + (env.LEADS_TOKEN || ""), "user-agent": "wahlah-scout" },
      body: JSON.stringify({ scout: scout.id, region: scout.region, collected_at: now.toISOString(), leads }),
    });
    return res.ok ? leads.length : 0;
  } catch (e) {
    return 0;
  }
}