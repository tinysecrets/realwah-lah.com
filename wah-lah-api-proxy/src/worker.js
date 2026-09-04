const DEFAULT_TARGET = "https://realwah-lah-com-8v2l.onrender.com";

export default {
  async fetch(request, env) {
    const targetHost = (env && env.PROD_TARGET) || DEFAULT_TARGET;

    const url = new URL(request.url);
    const targetUrl = `${targetHost}${url.pathname}${url.search}`;

    const headers = new Headers(request.headers);
    headers.set("Host", targetHost.replace(/^https?:\/\//, ""));
    headers.set("X-Forwarded-Host", url.hostname);
    headers.set("X-Forwarded-Proto", "https");

    const init = {
      method: request.method,
      headers,
      redirect: "manual",
    };

    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
    }

    try {
      const response = await fetch(targetUrl, init);

      const responseHeaders = new Headers(response.headers);
      responseHeaders.set("X-Proxy", "wah-lah-api-proxy");

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    } catch (err) {
      return new Response(
        JSON.stringify({ error: "Backend temporarily unavailable", detail: err.message }),
        { status: 502, headers: { "Content-Type": "application/json" } }
      );
    }
  },
};