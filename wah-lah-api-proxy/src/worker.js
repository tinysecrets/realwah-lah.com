export default {
  async fetch(request) {
    const url = new URL(request.url);

    const targetUrl =
      `https://realwah-lah-com.onrender.com${url.pathname}${url.search}`;

    const headers = new Headers(request.headers);

    headers.set("Host", "realwah-lah-com.onrender.com");
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

    const response = await fetch(targetUrl, init);

    const responseHeaders = new Headers(response.headers);
    responseHeaders.set("X-Proxy", "wah-lah-api-proxy");

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  },
};
