/**
 * wah-lah-api-proxy — api.wah-lah.com → Render backend.
 *
 * Security posture:
 *  - Only /api/* paths are proxied (this host serves the API, nothing else).
 *  - Only expected methods are forwarded.
 *  - Backend errors are sanitized: callers get a generic 502, never the
 *    raw exception text (which can leak hostnames, SDK versions, paths).
 *  - Baseline security headers are stamped on every response.
 */
const DEFAULT_TARGET = "https://realwah-lah-com-8v2l.onrender.com";

const ALLOWED_METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]);

// Hop-by-hop / internal headers that must never be forwarded upstream.
const STRIP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "cf-connecting-ip", // Cloudflare re-adds the authentic value upstream
]);

function json(status, obj) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...securityHeaders() },
  });
}

function securityHeaders() {
  return {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Path allowlist: API only. (A tiny /health alias keeps uptime checks simple.)
    if (url.pathname !== "/health" && !url.pathname.startsWith("/api/") && url.pathname !== "/api") {
      return json(404, { error: "Not found" });
    }
    if (!ALLOWED_METHODS.has(request.method)) {
      return json(405, { error: "Method not allowed" });
    }

    const targetHost = ((env && env.PROD_TARGET) || DEFAULT_TARGET).replace(/\/+$/, "");
    if (!/^https:\/\//i.test(targetHost)) {
      // Never proxy to a non-TLS backend.
      return json(502, { error: "Backend temporarily unavailable" });
    }
    const targetUrl = `${targetHost}${url.pathname}${url.search}`;

    const headers = new Headers();
    request.headers.forEach((value, key) => {
      if (!STRIP_HEADERS.has(key.toLowerCase())) headers.set(key, value);
    });
    headers.set("Host", targetHost.replace(/^https?:\/\//i, ""));
    headers.set("X-Forwarded-Host", url.hostname);
    headers.set("X-Forwarded-Proto", "https");

    const init = { method: request.method, headers, redirect: "manual" };
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
    }

    try {
      const response = await fetch(targetUrl, init);
      const responseHeaders = new Headers(response.headers);
      responseHeaders.set("X-Proxy", "wah-lah-api-proxy");
      for (const [k, v] of Object.entries(securityHeaders())) {
        if (!responseHeaders.has(k)) responseHeaders.set(k, v);
      }
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    } catch (err) {
      // Deliberately generic — the real error stays in `wrangler tail`.
      console.error("proxy upstream failure:", err && err.message);
      return json(502, { error: "Backend temporarily unavailable" });
    }
  },
};
