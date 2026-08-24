// Cloudflare Worker entrypoint. API_ORIGIN is injected as a Worker secret/variable.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/api/")) {
      if (!env.API_ORIGIN) {
        return Response.json(
          {
            detail:
              "Backend API is not configured. Set the Cloudflare Worker secret API_ORIGIN."
          },
          { status: 503 }
        );
      }

      let apiOrigin;
      try {
        apiOrigin = new URL(env.API_ORIGIN);
      } catch {
        return Response.json(
          { detail: "Invalid Cloudflare Worker API_ORIGIN configuration." },
          { status: 500 }
        );
      }

      if (!["http:", "https:"].includes(apiOrigin.protocol)) {
        return Response.json(
          { detail: "API_ORIGIN must use http or https." },
          { status: 500 }
        );
      }

      const target = new URL(url.pathname + url.search, apiOrigin);
      return fetch(new Request(target.toString(), request));
    }

    return env.ASSETS.fetch(request);
  }
};
